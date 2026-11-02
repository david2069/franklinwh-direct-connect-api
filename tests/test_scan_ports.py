"""`scan_ports` / `expand_ports` — one result per (host, port).

`scan()` takes a `ports` tuple, but it is a FILTER over two hardcoded constants, not
a list of ports to scan: `check()` tests `PORT_SENDMQTT in ports` and then probes the
literal 9000. Pass anything else and neither branch fires, nothing is probed, and the
host is reported as not a candidate -- no error, no warning
(DEF-SCAN-IGNORES-CUSTOM-PORTS).

`HostResult` also keys by host and carries booleans, so two listeners on one address
collapse to one row with the port recorded nowhere.

These are additive: `scan`, `HostResult` and `expand_targets` are untouched, so no
caller has to change on upgrade.
"""

from __future__ import annotations

import pytest

from franklinwh_direct_connect_api import discover
from franklinwh_direct_connect_api.discover import PortResult, expand_ports, scan_ports
from franklinwh_direct_connect_api.emulator import Emulator


# -- expand_ports ------------------------------------------------------------
@pytest.mark.parametrize("spec,want", [
    ("9000", [9000]),
    ("9000,9002", [9000, 9002]),
    ("9020-9024", [9020, 9021, 9022, 9023, 9024]),
    ("9000,9020-9022", [9000, 9020, 9021, 9022]),
    (" 9000 , 9002 ", [9000, 9002]),
    ("9002,9000", [9000, 9002]),          # sorted
    ("9000,9000", [9000]),                # de-duplicated
    ("9000-9000", [9000]),                # degenerate range is still a range
])
def test_expand_ports_accepts(spec, want):
    assert expand_ports(spec) == want


@pytest.mark.parametrize("spec,msg", [
    ("0", "out of range"),
    ("65536", "out of range"),
    ("-1", "out of range"),
    ("9030-9020", "reversed"),
    ("abc", "expected a number"),
    ("9000,abc", "expected a number"),
])
def test_expand_ports_rejects(spec, msg):
    """Loudly, with a message naming the problem -- a silent empty list would
    scan nothing and look like 'no gateways found'."""
    with pytest.raises(ValueError, match=msg):
        expand_ports(spec)


def test_expand_ports_is_separate_from_expand_targets():
    """A port where a host belongs is the easy mistake; both sides reject it."""
    with pytest.raises(ValueError, match="looks like a port number"):
        discover.expand_targets("9000")


# -- PortResult --------------------------------------------------------------
def test_port_result_carries_the_port_in_its_summary():
    """HostResult.summary() hardcodes '9000/sendMqtt' because HostResult can only
    ever describe port 9000. PortResult must name the port it actually scanned."""
    r = PortResult("192.0.2.5", 9021, open=True, confirmed=True,
                   manifest={"IBG_SN": "FAKESERIAL0000000001"})
    assert "9021" in r.summary()
    assert "CONFIRMED" in r.summary()
    assert r.serial == "FAKESERIAL0000000001"

    closed = PortResult("192.0.2.5", 9022)
    assert "9022" in closed.summary() and "closed" in closed.summary()
    assert closed.serial is None

    open_not_gateway = PortResult("192.0.2.5", 9023, open=True)
    assert "not a gateway" in open_not_gateway.summary()


# -- scan_ports against real listeners ---------------------------------------
def test_two_listeners_on_one_host_are_two_rows():
    """The case `scan()` structurally cannot represent.

    Both emulators are on 127.0.0.1, so a host-keyed result would collapse them
    into one row and lose the port entirely.
    """
    a = Emulator("127.0.0.1", 0).start()
    b = Emulator("127.0.0.1", 0).start()
    try:
        res = scan_ports(["127.0.0.1"], [a.port, b.port], timeout=1.0)
        assert len(res) == 2, [r.summary() for r in res]
        assert {r.port for r in res} == {a.port, b.port}
        assert all(r.confirmed for r in res)
        assert all(r.serial for r in res)
    finally:
        a.stop()
        b.stop()


def test_a_closed_port_is_omitted_and_an_open_one_is_confirmed_by_login():
    """`confirmed` means a real 1101 handshake answered -- that is what separates
    a gateway from anything else listening."""
    emu = Emulator("127.0.0.1", 0).start()
    try:
        closed = 1            # privileged and certainly not an emulator
        res = scan_ports(["127.0.0.1"], [emu.port, closed], timeout=1.0)
        assert [r.port for r in res] == [emu.port]
        assert res[0].confirmed and res[0].serial == emu.equip_no
    finally:
        emu.stop()


def test_probe_false_reports_open_without_confirming():
    emu = Emulator("127.0.0.1", 0).start()
    try:
        res = scan_ports(["127.0.0.1"], [emu.port], timeout=1.0, probe=False)
        assert len(res) == 1 and res[0].open
        assert not res[0].confirmed and res[0].manifest is None
    finally:
        emu.stop()


def test_results_are_sorted_and_empty_input_is_empty():
    assert scan_ports([], [9000]) == []
    assert scan_ports(["127.0.0.1"], []) == []


def test_the_old_scan_still_cannot_see_a_non_default_port():
    """Pins the defect this feature works around, so the contrast stays visible.

    If `scan()` is ever fixed to honour `ports`, this fails and should be removed
    -- it is not asserting that the old behaviour is correct, only that it is
    still what `scan()` does.
    """
    emu = Emulator("127.0.0.1", 0).start()
    try:
        assert discover.port_open("127.0.0.1", emu.port, 1.0), "emulator not up"
        old = discover.scan(["127.0.0.1"], ports=(emu.port,), timeout=1.0)
        assert old == [], f"scan() unexpectedly honoured a custom port: {old}"

        new = scan_ports(["127.0.0.1"], [emu.port], timeout=1.0)
        assert len(new) == 1 and new[0].confirmed
    finally:
        emu.stop()
