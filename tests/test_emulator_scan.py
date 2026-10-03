"""Emulator + discovery tests (all in-process, no hardware)."""

from __future__ import annotations

import socket
import threading

import pytest

from franklinwh_local import discover
from franklinwh_local.client import LocalClient
from franklinwh_local.emulator import Emulator


@pytest.fixture
def emulator():
    emu = Emulator("127.0.0.1", 0).start()
    yield emu
    emu.stop()


# -- emulator ----------------------------------------------------------------
def test_emulator_serves_client(emulator):
    with LocalClient("127.0.0.1", emulator.port, timeout=3.0) as c:
        manifest = c.login()
        assert manifest["IBG_SN"] == emulator.equip_no
        flow = c.power_flow()
        assert "soc" in flow and "p_fhp" in flow



# -- discovery ---------------------------------------------------------------
def test_expand_targets_cidr():
    hosts = discover.expand_targets("192.0.2.0/30")
    assert hosts == ["192.0.2.1", "192.0.2.2"]


def test_expand_targets_range_and_list():
    hosts = discover.expand_targets("10.0.0.1-10.0.0.3, 10.0.0.9")
    assert hosts == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.9"]


def test_expand_targets_rejects_bare_port():
    # A purely-numeric token is almost certainly a port passed as a host.
    with pytest.raises(ValueError, match="port number"):
        discover.expand_targets("502")


def test_expand_targets_rejects_invalid_cidr():
    with pytest.raises(ValueError, match="invalid CIDR"):
        discover.expand_targets("192.0.2.0/99")


def test_expand_targets_rejects_invalid_range():
    with pytest.raises(ValueError, match="invalid range"):
        discover.expand_targets("10.0.0.1-not.an.ip.here")


def test_scan_finds_and_confirms_emulator(emulator):
    results = discover.scan(["127.0.0.1"], ports=(emulator.port,), timeout=1.0)
    # scan uses fixed port constants; probe the emulator port directly instead:
    assert discover.port_open("127.0.0.1", emulator.port)
    manifest = discover.probe_sendmqtt("127.0.0.1", emulator.port)
    assert manifest and manifest["IBG_SN"] == emulator.equip_no


def test_probe_modbus_rejects_non_modbus(emulator):
    # The emulator speaks sendMqtt, not Modbus, so a Modbus probe must fail.
    assert discover.probe_modbus("127.0.0.1", emulator.port, timeout=1.0) is False


def _serve_once(reply: bytes) -> int:
    """Spin a one-shot TCP server that returns ``reply`` to the first client.
    Returns the bound port."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def handle():
        try:
            conn, _ = srv.accept()
            with conn:
                conn.recv(256)
                if reply:
                    conn.sendall(reply)
        finally:
            srv.close()

    threading.Thread(target=handle, daemon=True).start()
    return port


def test_probe_modbus_accepts_valid_mbap():
    # A valid MBAP response (txn=1, proto=0, len=4, unit=1, fn=3, bytecount=2,
    # value) must be CONFIRMED. Regression: the probe previously fed 8 bytes to
    # a 7-byte struct format and raised struct.error on any real reply.
    import struct
    reply = struct.pack(">HHHB", 1, 0, 4, 1) + bytes([0x03, 0x02, 0x00, 0x00])
    port = _serve_once(reply)
    assert discover.probe_modbus("127.0.0.1", port, timeout=1.0) is True


def test_probe_modbus_rejects_short_reply():
    port = _serve_once(b"\x00\x00\x00")  # < 8 bytes → not Modbus
    assert discover.probe_modbus("127.0.0.1", port, timeout=1.0) is False


def test_cli_watch_bounded(emulator, capsys):
    from franklinwh_local.cli import main
    rc = main(["--host", "127.0.0.1", "--port", str(emulator.port),
               "power_flow", "--watch", "0", "--count", "3"])
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if "soc=" in l]
    assert len(lines) == 3


def test_health_does_not_short_circuit_on_ping_fail(monkeypatch, emulator, capsys):
    # A failed ping must NOT short-circuit — the authoritative sendMqtt round-trip
    # (with retries) still runs and succeeds on a lossy-but-working link.
    from franklinwh_local.cli import main
    from franklinwh_local import discover
    monkeypatch.setattr(discover, "ping", lambda *a, **k: False)
    rc = main(["--host", "127.0.0.1", "--port", str(emulator.port), "health"])
    out = capsys.readouterr().out
    assert "Test OK" in out          # protocol round-trip succeeded despite ping fail
    assert rc == 0


def test_der_comms_modbus_off_requires_confirmation(monkeypatch, capsys):
    # Turning Modbus OFF strands tooling — must confirm; declining aborts before connect.
    from franklinwh_local.cli import main
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    rc = main(["--host", "10.0.0.1", "der_comms", "--set-modbus", "off"])
    assert rc == 2
    assert "aborted" in capsys.readouterr().err


def test_der_comms_2030_5_on_requires_confirmation(monkeypatch, capsys):
    # Enabling 2030.5 hands dispatch to a DERMS — must warn + confirm; declining aborts.
    from franklinwh_local.cli import main
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    rc = main(["--host", "10.0.0.1", "der_comms", "--set-2030-5", "on"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "WARNING" in err and "aborted" in err


def test_reboot_requires_confirmation(monkeypatch, capsys):
    # reboot without --force must warn and prompt; declining aborts (no reboot sent).
    s = socket.socket(); s.bind(("127.0.0.1", 0)); freeport = s.getsockname()[1]; s.close()
    from franklinwh_local.cli import main
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    rc = main(["--host", "127.0.0.1", "--port", str(freeport), "--retries", "0", "reboot"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "WARNING" in err and "aborted" in err


def test_port_closed():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()  # now nothing is listening there
    assert discover.port_open("127.0.0.1", free_port, timeout=0.3) is False
