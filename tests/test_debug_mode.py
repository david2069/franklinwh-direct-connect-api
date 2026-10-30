"""Debug Mode (1821) — the one command that promoted from unknown to known.

The bridge's issue #311 asked the library for `set_debug_mode(on)` "once proven, rather
than writing raw calls in the bridge". It is now proven, on ONE site and ONE firmware:
aGate X-01-AU, IBG V12R02B60D00, 2026-10-23 — `enable` 1 turned Debug Mode on and
`enable` 0 turned it off, both read back, with a measured behavioural signature (the
battery stopped).

The safety property is what these tests mostly protect: turning Debug Mode ON stops
normal battery operation, so the write verifies by read-back and never reports success on
an acknowledgement alone.
"""
import pytest

from franklinwh_direct_connect_api import WRITES, catalog
from franklinwh_direct_connect_api.client import DirectConnectClient
from franklinwh_direct_connect_api.emulator import Emulator


def test_1821_is_no_longer_unconfirmed():
    info = catalog.CATALOG[1821]
    assert info.name == "debug_mode" and catalog.response_for(1821) == 1822
    assert 1821 not in catalog.UNCONFIRMED
    # The other four are still undecoded and must not be swept along with it.
    assert catalog.UNCONFIRMED == frozenset({1207, 1209, 1823, 1825})


def test_the_catalogue_entry_carries_the_evidence_and_the_danger():
    d = catalog.CATALOG[1821].description
    assert "V12R02B60D00" in d and "2026-10-23" in d      # which firmware, which day
    assert "one site" in d.lower()                         # not a mapping
    assert "STOPS NORMAL BATTERY OPERATION" in d


def test_the_write_is_registered_with_its_consequence():
    w = WRITES["set_debug_mode"]
    assert w["cmd"] == 1821 and w["opt"] == 1 and w["fields"] == ["enable"]
    assert "STOPS NORMAL BATTERY OPERATION" in w["note"]
    # What it does NOT unlock matters as much as what it might.
    assert "Reserve-SoC writes" in w["note"] and "still do NOT apply" in w["note"]


def test_1823_and_1825_stay_leads_not_findings():
    """The app's Debug Mode screen suggests them; nobody has read them changing."""
    for cmd in (1823, 1825):
        d = catalog.CATALOG[cmd].description
        assert "UNCONFIRMED" in d
        assert "LEAD" in d
    assert "DO NOT WRITE" in catalog.CATALOG[1823].description


# -- behaviour, against the in-process emulator ------------------------------------------
def _emu_with_debug_state():
    """An emulator that stores an `enable` flag for 1821, so a write can be read back."""
    state = {"enable": 0}

    def handler(req):
        if req.get("opt") == 1:
            state["enable"] = int(req.get("enable", 0))
            return {"opt": 1, "result": 0}
        return {"opt": 0, "result": 0, "enable": state["enable"]}

    return Emulator(host="127.0.0.1", port=0, seed=5, extra={1821: handler}), state


def test_turning_it_on_and_off_verifies_by_read_back():
    emu, state = _emu_with_debug_state()
    emu.start()
    try:
        with DirectConnectClient("127.0.0.1", emu.port, timeout=3.0) as c:
            c.login()
            assert c.debug_mode()["enable"] == 0
            res = c.set_debug_mode(True)
            assert res["verified"] is True and res["enable"] == 1 and state["enable"] == 1
            res = c.set_debug_mode(False)
            assert res["verified"] is True and res["enable"] == 0
    finally:
        emu.stop()


def test_an_acknowledged_write_that_does_not_stick_is_reported_unverified():
    """`result: 0` is not proof on this protocol — the aGate ACKs writes it discards.
    A caller must be able to tell 'Debug Mode is on' from 'the gateway said ok'."""
    def liar(req):
        # Accepts the write, never changes: exactly how 1405 and the circuit-schedule
        # write behave on real firmware.
        return {"opt": req.get("opt", 0), "result": 0, "enable": 0}

    emu = Emulator(host="127.0.0.1", port=0, seed=5, extra={1821: liar})
    emu.start()
    try:
        with DirectConnectClient("127.0.0.1", emu.port, timeout=3.0) as c:
            c.login()
            res = c.set_debug_mode(True)
            assert res["verified"] is False
            assert res["requested"] == 1 and res["enable"] == 0
    finally:
        emu.stop()


def test_a_rejected_write_raises():
    def refuse(req):
        return {"opt": 1, "result": 1, "reason": -2}

    emu = Emulator(host="127.0.0.1", port=0, seed=5, extra={1821: refuse})
    emu.start()
    try:
        from franklinwh_direct_connect_api.transport import TransportError
        with DirectConnectClient("127.0.0.1", emu.port, timeout=3.0) as c:
            c.login()
            with pytest.raises(TransportError):
                c.set_debug_mode(True)
    finally:
        emu.stop()


def test_the_cli_exposes_it_with_a_confirmation():
    import franklinwh_direct_connect_api.cli as cli
    sub = next(a for a in cli.build_parser()._actions if getattr(a, "choices", None))
    assert "debug_mode" in sub.choices
    src = __import__("inspect").getsource(cli._cmd_debug_mode)
    assert "--force" in cli.build_parser().format_help() or "force" in src
    assert "stops normal battery operation" in src.lower()


def test_the_1701_finding_is_recorded_with_its_conditions():
    """A grid cap STORED with Debug Mode on — but on newer firmware too, so the cause is
    not separated, and enforcement is untested. All three facts have to travel together
    or the entry becomes 'Debug Mode makes 1701 work', which nobody has shown."""
    d = catalog.CATALOG[1701].description
    assert "DEBUG MODE ON" in d and "V12R02B60D00" in d and "2026-10-23" in d
    assert "one site" in d                             # not a mapping
    assert "NOT separated" in d                        # Debug Mode vs firmware
    assert "enforcement is untested" in d.lower()
    # The catalogue has a hard length limit (it renders in the bridge's Device tab), so
    # the detail — gridImportLimit, the exact frames — lives in the protocol doc.
    assert "docs/PROTOCOL.md" in d
    proto = (__import__("pathlib").Path(__file__).resolve().parents[1]
             / "docs/PROTOCOL.md").read_text()
    assert "gridImportLimit" in proto
