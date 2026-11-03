"""Off-grid state in the mock, modelled from a real capture.

The mock answered a 1723 read with a bare `{'opt': 0, 'result': 0}` — no
`offgridSet`, `offgridSoc` or `offgridState` at all. A real aGate returns all
three, so a client reading off-grid status against a mock saw nothing, and an
off-grid write could not be observed to take effect.

The sequence asserted here is measured, not invented: 16 request/reply pairs from
a capture of the official app driving the reference aGate
(IBG_VER V12R02B30D06_260304) covering a full cycle each way.
"""

from __future__ import annotations

import pytest

from franklinwh_direct_connect_api import catalog
from franklinwh_direct_connect_api.client import DirectConnectClient
from franklinwh_direct_connect_api.emulator import Emulator


@pytest.fixture
def client():
    emu = Emulator("127.0.0.1", 0).start()
    try:
        with DirectConnectClient("127.0.0.1", emu.port, timeout=3.0) as c:
            c.login()
            yield c
    finally:
        emu.stop()


def _write(c, on: bool, soc: int = 5):
    return c.transport.request(
        1723, c.equip_no, {"opt": 1, "offgridSet": 1 if on else 0, "offgridSoc": soc}
    ).data_area


def test_a_read_returns_all_three_fields(client):
    """The defect: these were absent entirely."""
    r = client.offgrid()
    for key in ("offgridSet", "offgridSoc", "offgridState"):
        assert key in r, f"{key} missing from the 1724 reply"


def test_the_full_cycle_matches_the_captured_hardware_sequence(client):
    """Grid-connected -> off-grid -> back, with the transition the device shows.

    Measured: the WRITE REPLY carries offgridState 0 whichever direction the
    change goes, and only the FOLLOWING read settles to 1 or 2. A mock that
    settled immediately would let a client miss the transition entirely.
    """
    assert client.offgrid()["offgridState"] == 2          # grid-connected

    w = _write(client, True)
    assert w["offgridSet"] == 1
    assert w["offgridState"] == 0, "the write reply must report transitioning"

    assert client.offgrid()["offgridState"] == 1          # settled off-grid

    w = _write(client, False)
    assert w["offgridState"] == 0, "transitioning again, in both directions"

    assert client.offgrid()["offgridState"] == 2          # back grid-connected


def test_the_write_persists_across_reads(client):
    """Without persistence the switch has no state to show."""
    _write(client, True)
    for _ in range(3):
        assert client.offgrid()["offgridSet"] == 1


def test_offgrid_soc_round_trips(client):
    w = _write(client, True, soc=23)
    assert w["offgridSoc"] == 23
    assert client.offgrid()["offgridSoc"] == 23


def test_the_write_reply_echoes_opt_1(client):
    """Hardware echoes the request's opt on a write reply — 1409, 1723 and 1727
    all do. A constant would be wrong for 1727, which sends and gets back 3."""
    assert _write(client, True)["opt"] == 1
    assert client.offgrid()["opt"] == 0


def test_the_state_enum_is_documented():
    assert catalog.OFFGRID_STATE == {
        0: "Transitioning", 1: "Off-grid", 2: "Grid-connected"}
