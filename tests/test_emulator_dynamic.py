"""Dynamic per-seed emulator / SyntheticSite tests (in-process, no hardware)."""

from __future__ import annotations

import pytest

from franklinwh_direct_connect_api.client import LocalClient
from franklinwh_direct_connect_api.emulator import Emulator
from franklinwh_direct_connect_api.synthetic import MODE_IDS, SyntheticSite


def _ts_for_local_hour(site: SyntheticSite, hour: float, day: int = 20) -> float:
    """A unix ts whose *local* hour for ``site`` equals ``hour``."""
    base = day * 86400.0
    return base + hour * 3600.0 - site.tz_offset_hours * 3600.0


# -- SyntheticSite: identity -------------------------------------------------
def test_distinct_seeds_have_distinct_serials():
    a, b = SyntheticSite(1), SyntheticSite(2)
    assert a.serial != b.serial
    assert a.serial.startswith("MOCK") and b.serial.startswith("MOCK")
    assert len(a.serial) == 20 and len(b.serial) == 20


def test_serial_override_and_determinism():
    assert SyntheticSite(1).serial == SyntheticSite(1).serial      # deterministic
    assert SyntheticSite(5, serial="CUSTOM123").serial == "CUSTOM123"


# -- SyntheticSite: day/night divergence -------------------------------------
def test_noon_vs_midnight_snapshot():
    site = SyntheticSite(1)
    noon = site.snapshot(_ts_for_local_hour(site, 12.0))
    midnight = site.snapshot(_ts_for_local_hour(site, 0.0))

    # Noon: sun producing, Self-Consumption mode.
    assert noon["p_sun"] > 0
    assert noon["name"] == "Self-Consumption"
    assert noon["mode"] == MODE_IDS["Self-Consumption"]

    # Midnight: no sun, Emergency Backup mode.
    assert midnight["p_sun"] == pytest.approx(0.0, abs=1.0)
    assert midnight["name"] == "Emergency Backup"

    assert noon["soc"] != midnight["soc"]


def test_energy_balance_and_run_status():
    site = SyntheticSite(3)
    for hour in (0, 5, 8, 12, 15, 18, 21, 23):
        s = site.snapshot(_ts_for_local_hour(site, float(hour)))
        # Ranges.
        assert 5.0 <= s["soc"] <= 98.0
        assert s["p_load"] >= 0.0
        assert s["p_sun"] >= 0.0
        assert s["p_gen"] == 0.0
        # Exact energy balance: load = sun + grid + battery + gen.
        assert s["p_load"] == pytest.approx(
            s["p_sun"] + s["p_uti"] + s["p_fhp"] + s["p_gen"], abs=0.5
        )
        # run_status matches the sign of p_fhp (charging<0 / discharging>0).
        if s["run_status"] == 1:
            assert s["p_fhp"] < 0
        elif s["run_status"] == 2:
            assert s["p_fhp"] > 0


def test_mode_list_and_manifest_shape():
    site = SyntheticSite(1)
    ml = site.mode_list(_ts_for_local_hour(site, 12.0))
    assert ml["current_id"] == MODE_IDS["Self-Consumption"]
    names = {e["name"] for e in ml["list"]}
    assert names == {"Self-Consumption", "Time-of-Use", "Emergency Backup"}
    for e in ml["list"]:
        assert {"id", "name", "reserved_soc", "scheduling_type", "electricity_type"} <= set(e)

    manifest = site.login_manifest()
    assert manifest["IBG_SN"] == site.serial
    assert manifest["FHP_SN"] == [site.fhp_serial]
    assert "protocolVer" in manifest


# -- Emulator wired to a SyntheticSite ---------------------------------------
@pytest.fixture
def dyn_emulator():
    emu = Emulator("127.0.0.1", 0, seed=1).start()
    yield emu
    emu.stop()


def test_emulator_dynamic_serves_client(dyn_emulator):
    assert dyn_emulator.site is not None
    with LocalClient("127.0.0.1", dyn_emulator.port, timeout=3.0) as c:
        manifest = c.login()
        assert manifest["IBG_SN"] == dyn_emulator.site.serial
        flow = c.power_flow()
        for k in ("soc", "p_sun", "p_fhp", "p_uti", "p_load", "run_status", "mode", "name"):
            assert k in flow
        ml = c.mode_list()
        assert "current_id" in ml
        assert len(ml["list"]) == 3


def test_static_emulator_keeps_canned_path():
    # No seed + dynamic default: a bundled pcap is present, so the canned path is used
    # and the default serial is preserved (regression guard for existing tests).
    from franklinwh_direct_connect_api.emulator import DEFAULT_EQUIP
    emu = Emulator("127.0.0.1", 0)
    if emu.canned:                      # only meaningful when the fixture pcap exists
        assert emu.site is None
        assert emu.equip_no == DEFAULT_EQUIP


def test_emulator_multi_apower():
    """`--units N` presents N distinct aPowers: device_check reports devNum=N with
    N serials, and each unit's cells/states differ (SoC stepped, DCDC follows state)."""
    import time
    from franklinwh_direct_connect_api import emulator
    from franklinwh_direct_connect_api.client import LocalClient
    emu = emulator.Emulator("127.0.0.1", 19071, seed=7, units=3).start()
    try:
        with LocalClient("127.0.0.1", 19071) as c:
            c.login()
            dc = c.device_check()
            assert dc["devNum"] == 3
            serials = [u["devSN"] for u in dc["devMap"]]
            assert len(set(serials)) == 3                 # distinct serials
            socs = [c.battery_cells(i)["batSoc"] for i in (1, 2, 3)]
            assert socs[0] > socs[1] > socs[2]            # perturbed per unit
            # DCDCStatus is a valid decoded state (our verified 4/6/7 map)
            assert c.power_electronics(1)["DCDCStatus"] in (4, 6, 7)
    finally:
        emu.stop()


# -- NEW: energy history (1303/1304) -----------------------------------------
def test_energy_history_shape_totals_and_tiers():
    from franklinwh_direct_connect_api import catalog
    site = SyntheticSite(3)
    now = 20 * 86400.0
    import datetime
    day = datetime.date.fromtimestamp(now).isoformat()
    eh = site.energy_history(day, now=now)

    assert eh["sno"] > 0 and eh["pointId"] == 96 and eh["pointMax"] == 96
    for key in ("rec_time", "p_uti", "p_gen", "p_fhp", "p_load"):
        assert len(eh[key]) == 96, key
    assert eh["rec_time"][0] == "00:15" and eh["rec_time"][-1] == "24:00"
    assert eh["kwh_sun"] > 0 and eh["kwh_load"] > 0
    # each channel's four tier values sum to its daily total (allow rounding)
    for ci, ch in enumerate(catalog.ENERGY_CHANNELS):
        tier_sum = sum(eh[t][ci] for t in catalog.TIERS)
        assert abs(tier_sum - eh[ch]) < 0.05, ch
    assert all(v == 0 for v in eh["sharp"])          # sharp is deprecated -> zero


def test_energy_history_outside_retention_is_empty():
    site = SyntheticSite(1)
    now = 200 * 86400.0
    assert site.energy_history("1970-01-01", now=now)["sno"] == 0     # too old
    import datetime
    future = (datetime.date.fromtimestamp(now) + datetime.timedelta(days=3)).isoformat()
    assert site.energy_history(future, now=now)["sno"] == 0            # future
    assert site.energy_history("not-a-date", now=now)["rec_time"] == []


# -- NEW: smart circuits (1409/1410) + write round-trip ----------------------
def test_smart_circuits_read_and_write_roundtrip():
    site = SyntheticSite(1)
    sc = site.smart_circuits()
    assert sc["Sw1Name"] and "Sw1Mode" in sc and "SwMerge" in sc
    assert sc["Sw1Mode"] == 1                                          # default on
    site.apply_smart_circuit_write({"opt": 1, "Sw1Mode": 0, "Sw1ProLoad": 1})
    assert site.smart_circuits()["Sw1Mode"] == 0                       # persisted


# -- NEW: mode set (1727) overrides the time-of-day schedule -----------------
def test_mode_write_overrides_schedule():
    site = SyntheticSite(1)
    site.set_mode_write({"opt": 3, "current_id": MODE_IDS["Emergency Backup"]})
    snap = site.snapshot(_ts_for_local_hour(site, 12.0))              # noon -> normally SC
    assert snap["name"] == "Emergency Backup"
    assert site.mode_config(0.0)["name"] == "Emergency Backup"


# -- NEW: full end-to-end write round-trip through the client ----------------
def test_emulator_write_roundtrip_e2e():
    emu = Emulator(host="127.0.0.1", port=0, seed=7)
    emu.start()
    try:
        with LocalClient("127.0.0.1", emu.port, timeout=3.0) as c:
            c.login()
            assert len(c.smart_circuits()) and c.smart_circuits()["Sw2Name"]
            # toggle a circuit off — set_smart_circuit self-verifies via read-back
            res = c.set_smart_circuit(2, on=False)
            assert res["ok"] is True and res["confirmed"] is True
            assert c.smart_circuits()["Sw2Mode"] == 0
            # energy history for today returns a populated day
            eh = c.energy_history()
            assert len(eh["rec_time"]) == 96 and eh["kwh_load"] > 0
    finally:
        emu.stop()
