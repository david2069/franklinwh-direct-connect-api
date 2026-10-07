"""
Client/transport tests using a loopback fake broker (no hardware required).

A background thread accepts one connection, decodes incoming request frames
with the same protocol code, and replies with canned response frames — so the
full encode -> socket -> decode -> reply path is exercised end to end.
"""

from __future__ import annotations

import socket
import threading

import pytest

from franklinwh_direct_connect_api import protocol
from franklinwh_direct_connect_api.client import LocalClient
from franklinwh_direct_connect_api.transport import LocalTransport, TransportError

EQUIP = "FAKEGATE90FJ09J6H4F2"


class FakeBroker:
    """Minimal in-process broker that answers login + power_flow."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.thread.start()

    def _serve(self):
        conn, _ = self.sock.accept()
        stream = protocol.FrameStream()
        with conn:
            while True:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    return
                if not chunk:
                    return
                for fr in stream.feed(chunk):
                    conn.sendall(self._reply(fr))

    def _reply(self, fr) -> bytes:
        if fr.cmd_type == 1101:
            da = {"opt": 0, "result": 0, "IBG_SN": EQUIP, "protocolVer": "V1.11.01"}
            return protocol.encode_frame(1102, EQUIP, da, snno=fr.snno)
        if fr.cmd_type == 1301:
            da = {"opt": 0, "result": 0, "mode": 85232, "name": "Self-Consumption",
                  "p_uti": 19, "p_fhp": 509, "p_load": 519, "soc": 66.5}
            return protocol.encode_frame(1302, EQUIP, da, snno=fr.snno)
        # generic echo
        return protocol.encode_frame(fr.cmd_type + 1, EQUIP, {"opt": 0, "result": 0},
                                     snno=fr.snno)


@pytest.fixture
def broker():
    b = FakeBroker()
    b.start()
    yield b
    b.sock.close()


def test_login_and_power_flow(broker):
    with LocalClient("127.0.0.1", broker.port, timeout=3.0) as c:
        manifest = c.login()
        assert manifest["IBG_SN"] == EQUIP
        assert c.equip_no == EQUIP
        flow = c.power_flow()
        assert flow["name"] == "Self-Consumption"
        assert flow["soc"] == 66.5


def test_generic_call(broker):
    with LocalClient("127.0.0.1", broker.port, timeout=3.0) as c:
        c.login()
        res = c.call(1117)
        assert res["result"] == 0


def test_firmware_returns_version_block(broker):
    with LocalClient("127.0.0.1", broker.port, timeout=3.0) as c:
        fw = c.firmware()
        assert fw["IBG_SN"] == EQUIP           # serials + versions from the login manifest
        assert fw["protocolVer"] == "V1.11.01"
        assert "result" not in fw              # envelope fields excluded


def test_set_der_comms_full_block_rmw():
    # Toggling one field sends the WHOLE 1205 block back, only that field changed,
    # and records prior state for revert. No self-verify (interface check is the CLI's job).
    from unittest.mock import MagicMock
    c = LocalClient("host"); c._equip = EQUIP; c.transport = MagicMock()
    prior = {"result": 0, "opt": 0, "enable": 0, "pin": "111115",
             "ip": "192.0.2.110", "port": 502, "sunsMdEn": 1}
    c.transport.request.side_effect = [
        MagicMock(data_area=prior),                       # read
        MagicMock(data_area={"result": 0, "opt": 1}),     # write ack
    ]
    reply = c.set_der_comms(sunspec_modbus=False)
    cmd, equip, data = c.transport.request.call_args_list[1].args
    assert cmd == 1205 and data["opt"] == 1
    assert data["sunsMdEn"] == 0        # requested change
    assert data["pin"] == "111115"      # rest of block preserved
    assert reply["prior_der_comms"]["sunsMdEn"] == 1


def test_set_der_comms_raises_on_rejection():
    c = _mock_client({"result": 1, "reason": -2, "opt": 1})
    with pytest.raises(TransportError):
        c.set_der_comms(sunspec_modbus=True)


def test_reboot_builds_full_block_1721(broker):
    # reboot must read the full block and write it back with reboot=1 (not a partial frame).
    from unittest.mock import MagicMock
    c = LocalClient("host"); c._equip = EQUIP; c.transport = MagicMock()
    c.transport.request.side_effect = [
        MagicMock(data_area={"result": 0, "opt": 0, "reboot": 0, "reset": 0, "update": 0}),
        MagicMock(data_area={"result": 0, "opt": 1}),
    ]
    reply = c.reboot()
    cmd, equip, data = c.transport.request.call_args_list[1].args   # the write
    assert cmd == 1721
    assert data == {"opt": 1, "reboot": 1, "reset": 0, "update": 0}
    assert reply["dropped"] is False


# -- control writes (request construction; no hardware) -----------------------
from unittest.mock import MagicMock  # noqa: E402


def _mock_client(reply=None):
    c = LocalClient("host")
    c._equip = EQUIP
    c.transport = MagicMock()
    c.transport.request.return_value.data_area = reply or {"result": 0, "opt": 3}
    return c


def test_set_mode_by_id_builds_1727_opt3():
    c = _mock_client()
    c.set_mode(29287)
    cmd, equip, data = c.transport.request.call_args.args
    assert cmd == 1727
    assert data == {"opt": 3, "current_id": 29287}


def test_set_mode_resolves_name_via_mode_list():
    c = LocalClient("host"); c._equip = EQUIP
    c.transport = MagicMock()

    def req(cmd, equip, data=None):
        m = MagicMock()
        m.data_area = ({"current_id": 1,
                        "list": [{"id": 29287, "name": "Ausgrid EA11 TOU"}]}
                       if cmd == 1725 else {"result": 0})
        return m

    c.transport.request.side_effect = req
    c.set_mode("ausgrid ea11 tou")  # case-insensitive name
    cmd, equip, data = c.transport.request.call_args.args
    assert cmd == 1727 and data["current_id"] == 29287


def test_set_mode_unknown_name_raises():
    c = LocalClient("host"); c._equip = EQUIP
    c.transport = MagicMock()
    c.transport.request.return_value.data_area = {"list": [{"id": 1, "name": "TOU"}]}
    with pytest.raises(ValueError, match="unknown mode"):
        c.set_mode("Nonexistent")


def test_set_offgrid_builds_1723_opt1():
    c = _mock_client({"result": 0})
    c.set_offgrid(True, soc=10)
    cmd, equip, data = c.transport.request.call_args.args
    assert cmd == 1723
    assert data == {"opt": 1, "offgridSet": 1, "offgridSoc": 10}
    c.set_offgrid(False)
    _, _, data2 = c.transport.request.call_args.args
    assert data2["offgridSet"] == 0


def test_set_smart_circuit_builds_1409_rmw_block():
    # Full-block RMW: reads 1409, flags only the target MsgType, sets Mode/ProLoad,
    # writes the whole block back with opt=1, then re-reads to self-verify.
    from unittest.mock import MagicMock
    c = LocalClient("host"); c._equip = EQUIP; c.transport = MagicMock()
    prior = {"result": 0, "opt": 0, "reason": 0,
             "Sw1Mode": 0, "Sw1ProLoad": 1, "Sw1MsgType": 1, "Sw1Name": "Pump",
             "Sw2Mode": 0, "Sw2ProLoad": 1, "Sw2MsgType": 1,
             "Sw3Mode": 0, "Sw3ProLoad": 1, "Sw3MsgType": 1}
    after = dict(prior, Sw2Mode=1)          # device applied the change
    c.transport.request.side_effect = [
        MagicMock(data_area=dict(prior)),                  # read (1409)
        MagicMock(data_area={"result": 0, "opt": 1}),      # write ack
        MagicMock(data_area=after),                        # read-back (1409)
    ]
    out = c.set_smart_circuit(2, True)
    cmd, equip, data = c.transport.request.call_args_list[1].args   # the write
    assert cmd == 1409 and data["opt"] == 1
    assert data["Sw2Mode"] == 1 and data["Sw2ProLoad"] == 0        # requested change
    assert data["Sw2MsgType"] == 1                                  # target flagged
    assert data["Sw1MsgType"] == 0 and data["Sw3MsgType"] == 0      # others cleared
    assert data["Sw1Name"] == "Pump"                               # rest of block preserved
    assert "result" not in data and "reason" not in data           # envelope stripped
    assert out["ok"] is True and out["confirmed"] is True
    assert out["before"] == 0 and out["after"] == 1 and out["requested"] == 1


def test_set_smart_circuit_ok_false_when_readback_disagrees():
    # result:0 but the read-back does NOT confirm → ok must be False (delayed-apply / mock).
    from unittest.mock import MagicMock
    c = LocalClient("host"); c._equip = EQUIP; c.transport = MagicMock()
    prior = {"result": 0, "opt": 0, "Sw1Mode": 0, "Sw1ProLoad": 1, "Sw1MsgType": 1}
    c.transport.request.side_effect = [
        MagicMock(data_area=dict(prior)),                  # read
        MagicMock(data_area={"result": 0, "opt": 0}),      # ack (mock ignores write)
        MagicMock(data_area=dict(prior)),                  # read-back unchanged
    ]
    out = c.set_smart_circuit(1, True)
    assert out["result"] == 0
    assert out["confirmed"] is False and out["ok"] is False
    assert "note" in out


def test_set_smart_circuit_rejects_bad_circuit():
    c = _mock_client()
    with pytest.raises(ValueError, match="circuit must be"):
        c.set_smart_circuit(4, True)


def test_set_mode_aliases_match_siblings():
    """tou / self / sc / backup aliases (shared with franklinwh-modbus/-cloud)."""
    c = LocalClient("host"); c._equip = EQUIP
    c.transport = MagicMock()

    def req(cmd, equip, data=None):
        m = MagicMock()
        m.data_area = ({"list": [{"id": 29287, "name": "Ausgrid EA11 TOU"},
                                 {"id": 85232, "name": "Self-Consumption"},
                                 {"id": 47522, "name": "Emergency Backup"}]}
                       if cmd == 1725 else {"result": 0})
        return m

    c.transport.request.side_effect = req
    for alias, expect in [("tou", 29287), ("TOU", 29287), ("self", 85232),
                          ("sc", 85232), ("SC", 85232), ("backup", 47522),
                          ("Backup", 47522), ("emergency", 47522)]:
        c.set_mode(alias)
        _, _, data = c.transport.request.call_args.args
        assert data["current_id"] == expect, f"{alias} -> {data}"


def test_new_named_reads(broker):
    """wifi_scan, smart_circuit_meter, event_block, generator all work via FakeBroker."""
    with LocalClient("127.0.0.1", broker.port, timeout=3.0) as c:
        c.login()
        for method in ("wifi_scan", "smart_circuit_meter", "event_block", "generator"):
            result = getattr(c, method)()
            assert result["result"] == 0, f"{method} returned unexpected: {result}"


def test_transport_retries_on_transient_error():
    # A transient failure (e.g. wifi drop / connection reset) should trigger a
    # reconnect + retry, not surface to the caller.
    t = LocalTransport("host", retries=1, retry_backoff=0)
    t._sock = object()  # pretend connected
    calls = {"n": 0}
    def flaky_send(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransportError("connection closed by peer")
    t.send_frame = flaky_send
    t.recv_frame = lambda **k: "FRAME"
    t._reconnect = lambda: setattr(t, "_sock", object())
    assert t.request(1301, "EQUIP", {"opt": 0}) == "FRAME"
    assert calls["n"] == 2  # failed once, retried once, succeeded


def test_transport_matches_error_frame_9999():
    from franklinwh_direct_connect_api.transport import ERROR_CMD
    from types import SimpleNamespace as NS
    m = LocalTransport._matches
    assert m(NS(cmd_type=ERROR_CMD), 1234) is True   # 9999 terminates any wait
    assert m(NS(cmd_type=1234), 1234) is True         # exact match
    assert m(NS(cmd_type=1235), 1234) is False        # wrong frame buffered
    assert m(NS(cmd_type=1235), None) is True         # any frame when want is None


def test_transport_login_retries_on_transient_error():
    # login is the entry point for every command, so it must retry too.
    t = LocalTransport("host", retries=1, retry_backoff=0)
    calls = {"n": 0}
    def flaky_login():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransportError("connection closed by peer")
        return "MANIFEST"
    t.connect = lambda: setattr(t, "_sock", object())
    t.close = lambda: setattr(t, "_sock", None)
    t._do_login = flaky_login
    assert t.login() == "MANIFEST"
    assert calls["n"] == 2
    assert t._logged_in is True


def test_transport_raises_after_retries_exhausted():
    t = LocalTransport("host", retries=2, retry_backoff=0)
    t._sock = object()
    def always_fail(*a, **k):
        raise TransportError("boom")
    t.send_frame = always_fail
    t._reconnect = lambda: setattr(t, "_sock", object())
    with pytest.raises(TransportError):
        t.request(1301, "EQUIP", {"opt": 0})


def test_grid_profile_fanout():
    """grid_profile() fans out to 1203 + 1211..1229 + 1251..1277 and aggregates results."""
    c = LocalClient("host"); c._equip = EQUIP
    c.transport = MagicMock()

    called_cmds: list[int] = []

    def req(cmd, equip, data=None):
        called_cmds.append(cmd)
        m = MagicMock()
        m.data_area = {"result": 0, "opt": 0}
        return m

    c.transport.request.side_effect = req
    result = c.grid_profile()

    assert "grid_policy" in result
    assert "compliance_sections" in result
    # All 10 summary sections (1211..1229) + 14 detailed sections (1251..1277) called.
    expected_compliance_cmds = list(range(1211, 1230, 2)) + list(range(1251, 1278, 2))
    for cmd in expected_compliance_cmds:
        assert cmd in called_cmds, f"grid_profile() did not call cmd {cmd}"
    assert 1203 in called_cmds


def test_set_mode_resolves_via_scheduling_type_not_substring():
    """Aliases resolve via scheduling_type even when the alias substring is absent
    from the tariff name — the exact case the old substring approach failed.

    Site: TOU tariff named 'ActewAGL Residential' (no 'tou' substring).
    Old code: 'tou' not in 'actewagl residential' -> ValueError.
    New code: scheduling_type==1 -> id 29287.
    """
    c = LocalClient("host"); c._equip = EQUIP
    c.transport = MagicMock()

    def req(cmd, equip, data=None):
        m = MagicMock()
        # Realistic live shape: scheduling_type present, tariff name opaque.
        m.data_area = ({"current_id": 47522,
                        "list": [
                            {"id": 47522, "name": "Emergency Backup",    "scheduling_type": 3},
                            {"id": 29287, "name": "ActewAGL Residential", "scheduling_type": 1},
                            {"id": 85232, "name": "Self-Consumption",    "scheduling_type": 2},
                        ]}
                       if cmd == 1725 else {"result": 0})
        return m

    c.transport.request.side_effect = req

    # All three aliases must resolve to the correct id via scheduling_type,
    # NOT via substring name match.
    for alias, expect in [
        ("tou", 29287),        # scheduling_type 1 — name has no 'tou' substring
        ("time_of_use", 29287),
        ("self", 85232),       # scheduling_type 2
        ("sc", 85232),
        ("backup", 47522),     # scheduling_type 3
        ("emergency", 47522),
    ]:
        c.set_mode(alias)
        _, _, data = c.transport.request.call_args.args
        assert data["current_id"] == expect, f"{alias} -> {data}"
