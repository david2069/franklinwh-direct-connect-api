"""Payload-matrix prober tests — in-process against the emulator, no hardware.

The point of the matrix is that a cmdType may only answer when addressed with a
per-battery selector ({"fhpSn": SN, "type": 2}) rather than the usual
{"opt": 0}. The emulator's `extra` hook lets us model exactly that.
"""

from __future__ import annotations

import pytest

from franklinwh_local import catalog, probe
from franklinwh_local.client import LocalClient
from franklinwh_local.emulator import Emulator

CELL_CODE = 1507          # an unused gap code, stands in for the real BMS read
PACK_SN = "FAKEAPOWERP6KMFY7ALA"


def _bms_reply(data: dict) -> dict | None:
    """Answer only when addressed per-battery — mirrors cloud get_bms_info."""
    if data.get("fhpSn") != PACK_SN or data.get("type") not in (2, 3):
        return None                      # wrong shape -> silence, like real hardware
    cells = {f"vol{i}": 3336 + (i % 2) for i in range(1, 17)}
    return {"opt": 0, "result": 0, "reason": 0, "fhpSn": PACK_SN, **cells}


@pytest.fixture
def emulator():
    emu = Emulator("127.0.0.1", 0, extra={CELL_CODE: _bms_reply}).start()
    yield emu
    emu.stop()


@pytest.fixture
def client(emulator):
    with LocalClient("127.0.0.1", emulator.port, timeout=1.0, retries=0) as c:
        c.login()
        yield c


# -- unit: detectors ---------------------------------------------------------
def test_cell_series_detected_from_suffixed_keys():
    data = {f"vol{i}": 3337 for i in range(1, 17)}
    assert probe.find_cell_series(data) == ["vol*"]


def test_cell_series_detected_from_a_list():
    assert probe.find_cell_series({"cellVolt": [3.337] * 16}) == ["cellVolt"]


def test_cell_series_ignores_out_of_band_numbers():
    """Power/energy arrays must not be mistaken for cell voltages."""
    assert probe.find_cell_series({f"p{i}": i * 100 for i in range(1, 17)}) == []


def test_cell_series_ignores_short_series():
    assert probe.find_cell_series({f"vol{i}": 3337 for i in range(1, 4)}) == []


# -- unit: code selection ----------------------------------------------------
def test_gap_codes_are_derived_from_the_catalog():
    """Regression: the old scratch script hardcoded a 17-entry known-set."""
    gaps = probe.gap_codes()
    assert all(c % 2 for c in gaps)
    assert not (set(gaps) & set(catalog.CATALOG))
    for code in catalog.CATALOG:
        assert code not in gaps
    assert probe.gap_codes(1101, 1121, include_known=True) == list(range(1101, 1122, 2))


def test_default_payload_matrix_shape():
    shapes = probe.default_payloads(["SN"])
    assert shapes[0] == {"opt": 0}
    assert {"fhpSn": "SN", "type": 2} in shapes
    assert {"fhpSn": "SN", "type": 3} in shapes


# -- integration: the matrix finds what a plain sweep cannot -----------------
def test_plain_opt0_sweep_misses_a_selector_gated_read(client):
    """This is why probe_gaps.py could not have found the BMS read."""
    results = probe.probe_codes(client, [CELL_CODE], [{"opt": 0}])
    assert results[0].status == "timeout"
    assert results[0].data is None


def test_payload_matrix_finds_the_selector_gated_read(client):
    results = probe.probe_codes(client, [CELL_CODE], probe.default_payloads([PACK_SN]))
    hit = results[0]
    assert hit.status == "hit"
    assert hit.payload == {"fhpSn": PACK_SN, "type": 2}
    assert hit.cell_series == ["vol*"]
    assert not hit.known                       # not in the catalog -> a new code
    assert "CELL-LIKE" in hit.summary()
    assert "<-- NEW" in hit.summary()


def test_known_code_answers_the_plain_read(client):
    results = probe.probe_codes(client, [1301], [{"opt": 0}])
    assert results[0].status == "hit"
    assert results[0].known
    assert "soc" in results[0].keys


def test_envelope_only_reply_is_not_counted_as_a_hit(client):
    """A reply carrying only opt/result/reason is 'empty', never a find."""
    results = probe.probe_codes(client, [1509], [{"opt": 0}])
    assert results[0].status == "empty"
    assert results[0].keys == []
    assert "accepted, no data" in results[0].summary()


def test_rejected_reply_is_distinguished_from_accepted_but_empty():
    """Real hardware answers an unimplemented cmdType with result=1, reason=4."""
    emu = Emulator("127.0.0.1", 0,
                   extra={1511: lambda d: {"opt": 0, "result": 1, "reason": 4}}).start()
    try:
        with LocalClient("127.0.0.1", emu.port, timeout=1.0, retries=0) as c:
            c.login()
            res = probe.probe_codes(c, [1511], [{"opt": 0}])[0]
        assert res.status == "rejected"
        assert "result=1" in res.error
        assert "not implemented" in res.summary()
    finally:
        emu.stop()


def test_attempts_record_every_shape_tried(client):
    results = probe.probe_codes(client, [CELL_CODE], probe.default_payloads([PACK_SN]))
    statuses = [a["status"] for a in results[0].attempts]
    assert statuses[0] == "timeout"            # {"opt":0} rejected
    assert statuses[-1] == "hit"


def test_probe_is_read_only(client):
    """No probe payload may carry a write opt."""
    for shape in probe.default_payloads([PACK_SN]):
        assert shape.get("opt", 0) == 0


# -- CLI ---------------------------------------------------------------------
def test_cli_probe_reports_the_find(emulator, capsys):
    from franklinwh_local.cli import main

    rc = main(["-i", "127.0.0.1", "-p", str(emulator.port), "-t", "1",
               "--retries", "0", "probe",
               "--codes", str(CELL_CODE), "--serial", PACK_SN, "--no-serials"])
    assert rc == 0
    out = capsys.readouterr()
    assert "HIT" in out.out
    assert "CELL-TELEMETRY CANDIDATES" in out.err
    assert "fhpSn selector" in out.err


def test_cli_probe_json(emulator, capsys):
    import json

    from franklinwh_local.cli import main

    rc = main(["-i", "127.0.0.1", "-p", str(emulator.port), "-t", "1",
               "--retries", "0", "probe", "--codes", str(CELL_CODE),
               "--serial", PACK_SN, "--no-serials", "--json"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["cmdType"] == CELL_CODE
    assert rows[0]["cell_series"] == ["vol*"]
    assert rows[0]["payload"]["type"] == 2


def test_cli_probe_requires_a_host(capsys):
    from franklinwh_local.cli import main

    assert main(["probe", "--codes", "1507"]) == 2
    assert "required" in capsys.readouterr().err


# -- custom payloads / all-shapes -------------------------------------------
def test_expand_payloads_substitutes_the_serial_token():
    out = probe.expand_payloads(
        [{"opt": 0}, {"opt": 0, "fhpSn": probe.SERIAL_TOKEN}], ["A", "B"])
    assert out == [{"opt": 0},
                   {"opt": 0, "fhpSn": "A"},
                   {"opt": 0, "fhpSn": "B"}]


def test_expand_payloads_leaves_tokenless_templates_alone():
    assert probe.expand_payloads([{"type": 2}], ["A"]) == [{"type": 2}]


def test_stop_on_hit_skips_later_shapes(client):
    """Default mode returns early — which is why --all-shapes had to exist."""
    results = probe.probe_codes(client, [1301],
                                [{"opt": 0}, {"fhpSn": PACK_SN, "type": 2}])
    assert len(results[0].attempts) == 1


def test_all_shapes_tries_every_payload_and_keeps_the_richest(client):
    results = probe.probe_codes(
        client, [CELL_CODE],
        [{"opt": 0}, {"fhpSn": PACK_SN, "type": 2}, {"fhpSn": PACK_SN, "type": 3}],
        stop_on_hit=False)
    assert len(results[0].attempts) == 3
    assert results[0].status == "hit"
    assert results[0].cell_series == ["vol*"]


def test_cli_rejects_a_write_payload(emulator, capsys):
    from franklinwh_local.cli import main

    rc = main(["-i", "127.0.0.1", "-p", str(emulator.port), "-t", "1", "--retries", "0",
               "probe", "--codes", "1507", "--no-serials",
               "--payload", '{"opt":1,"reboot":1}'])
    assert rc == 2
    assert "refusing to send a non-read payload" in capsys.readouterr().err


def test_cli_rejects_malformed_payload_json(emulator, capsys):
    from franklinwh_local.cli import main

    rc = main(["-i", "127.0.0.1", "-p", str(emulator.port), "-t", "1", "--retries", "0",
               "probe", "--codes", "1507", "--no-serials", "--payload", "not json"])
    assert rc == 2
    assert "must be JSON" in capsys.readouterr().err


def test_cli_custom_payload_finds_the_gated_read(emulator, capsys):
    from franklinwh_local.cli import main

    rc = main(["-i", "127.0.0.1", "-p", str(emulator.port), "-t", "1", "--retries", "0",
               "probe", "--codes", str(CELL_CODE), "--serial", PACK_SN, "--no-serials",
               "--payload", '{"fhpSn":"%fhpSn%","type":2}'])
    assert rc == 0
    assert "CELL-LIKE" in capsys.readouterr().out


# -- per-device `id` selector (how 1705 was actually found) ------------------
ID_CODE = 1705
CELLS = [3326] * 16


def _id_gated_reply(data: dict) -> dict | None:
    """Answer with empty arrays unless the request names a device.

    This is exactly how the real aGate behaves on 1705: the key set is the same
    either way, so only the *values* reveal that you asked wrong.
    """
    if not data.get("id"):
        return {"opt": 0, "result": 1, "reason": -1, "id": 0,
                "batVolt": [], "batTemp": [], "batSoc": 0, "batSoh": 0}
    return {"opt": 0, "result": 0, "reason": 0, "id": data["id"],
            "batVolt": list(CELLS), "batTemp": [19.0] * 16,
            "batSoc": 78.7, "batSoh": 94.9}


def test_default_matrix_includes_id_selectors():
    shapes = probe.default_payloads([])
    assert {"opt": 0, "id": 1} in shapes
    assert shapes.index({"opt": 0, "id": 1}) < len(shapes)


def test_id_gated_read_is_found_by_the_default_matrix():
    emu = Emulator("127.0.0.1", 0, extra={ID_CODE: _id_gated_reply}).start()
    try:
        with LocalClient("127.0.0.1", emu.port, timeout=1.0, retries=0) as c:
            c.login()
            res = probe.probe_codes(c, [ID_CODE], probe.default_payloads([]),
                                    stop_on_hit=False)[0]
        assert res.status == "hit"
        assert res.payload == {"opt": 0, "id": 1}
        assert res.cell_series == ["batVolt"]
        assert res.data["batSoh"] == 94.9
    finally:
        emu.stop()


def test_plain_read_looks_like_data_but_is_an_empty_shell():
    """The trap: same keys, empty values. Must not be reported as the best hit."""
    emu = Emulator("127.0.0.1", 0, extra={ID_CODE: _id_gated_reply}).start()
    try:
        with LocalClient("127.0.0.1", emu.port, timeout=1.0, retries=0) as c:
            c.login()
            plain = probe.probe_codes(c, [ID_CODE], [{"opt": 0}])[0]
            both = probe.probe_codes(c, [ID_CODE],
                                     [{"opt": 0}, {"opt": 0, "id": 1}],
                                     stop_on_hit=False)[0]
        assert plain.cell_series == []          # empty arrays -> no detection
        assert both.payload == {"opt": 0, "id": 1}   # richest wins
        assert both.cell_series == ["batVolt"]
    finally:
        emu.stop()


# -- out-of-band codes drop the session -------------------------------------
def test_disconnect_is_distinguished_from_a_refusal():
    """The aGate CLOSES the connection for out-of-band codes, not refuses them."""
    assert probe._is_disconnect(BrokenPipeError(32, "Broken pipe"))
    assert probe._is_disconnect(Exception("connection closed by peer"))
    assert not probe._is_disconnect(TimeoutError("timed out"))
    assert not probe._is_disconnect(ValueError("bad frame"))


def test_sweep_reconnects_after_a_dropped_session():
    """Without this, one out-of-band code silently invalidates the whole sweep.

    Reproduces the real failure: probing below 1101 dropped the session and
    every subsequent code returned a bogus 'broken pipe' error.
    """
    class _Flaky:
        def __init__(self):
            self.calls = 0
            self.reconnects = 0

        def call(self, cmd, data=None):
            self.calls += 1
            if self.calls == 1:
                raise OSError("connection closed by peer")
            return {"opt": 0, "result": 0, "reason": 0, "value": cmd}

    client = _Flaky()

    def _reconnect():
        client.reconnects += 1
        return client

    results = probe.probe_codes(client, [1501, 1503], [{"opt": 0}],
                                reconnect=_reconnect)
    assert client.reconnects == 1
    assert results[1].status == "hit"          # second code works after reconnect


def test_sweep_without_reconnect_still_completes():
    class _Dead:
        def call(self, cmd, data=None):
            raise OSError("broken pipe")

    results = probe.probe_codes(_Dead(), [1501], [{"opt": 0}])
    assert results[0].status == "error"
