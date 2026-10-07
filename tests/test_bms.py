"""Battery Management view — pure rendering + CLI wiring (no hardware)."""

from __future__ import annotations

import pytest

from franklinwh_direct_connect_api import bms

CELLS = {
    "opt": 0, "result": 0, "reason": 0, "id": 1,
    "batVolt": [3316, 3317, 3317, 3317, 3317, 3317, 3316, 3316,
                3316, 3317, 3317, 3316, 3318, 3318, 3317, 3317],
    "batTemp": [20.5, 20.7, 20.8, 20.8, 20.6, 20.9, 20.7, 20.6,
                21.2, 21.1, 21.4, 21.3, 21.2, 21.2, 21.2, 20.9],
    "batTotalVolt": 53.0, "batSoc": 98.8, "batSoh": 94.9,
    "currGrp": -6.6, "alarmLevel": 0,
}
PE = {"gridVol1": 122.0, "gridVol2": 122.0, "inverterVolt1": 121.9,
      "inverterVolt2": 122.0, "positiveBusVolt": 200.0, "negativeBusVolt": 200.0,
      "batVol": 53.0, "middleBusVolt": 312.9, "gridFreq": 50.0,
      "loadCurr1": 1.3, "loadCurr2": 1.3, "buckboostCurr": 1.2,
      "runMode": 8, "inverterStatus": 8, "DCDCStatus": 7}
STATES = {"bmsState": 7, "peState": 8}
FW = {"fhp_sn": "FAKEAPOWERP6KMFY7ALA", "bms_ver": "V11R50B03D00"}
CHECK = {"devNum": 1}


# -- duration parsing --------------------------------------------------------
@pytest.mark.parametrize("text,secs", [
    ("90", 90), ("30s", 30), ("5m", 300), ("2h", 7200), ("1d", 86400),
    (" 45 s ", 45), ("1.5m", 90),
])
def test_parse_duration(text, secs):
    assert bms.parse_duration(text) == secs


@pytest.mark.parametrize("bad", ["", "abc", "-5", "0", "5x", "m"])
def test_parse_duration_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        bms.parse_duration(bad)


# -- cell statistics ---------------------------------------------------------
def test_cell_stats_derives_extreme_positions():
    """The cloud sends maxVolPos/minVolPos; locally they are argmax/argmin, so
    nothing is actually missing."""
    st = bms.cell_stats(CELLS["batVolt"], CELLS["batTemp"])
    assert st["v_max"] == 3318 and st["v_max_cell"] == 13
    assert st["v_min"] == 3316 and st["v_min_cell"] == 1
    assert st["spread"] == 2
    assert st["t_max_cell"] == 11 and st["t_min_cell"] == 1


def test_cell_stats_on_empty_arrays():
    assert bms.cell_stats([], []) == {}


# -- grid layout -------------------------------------------------------------
def test_grid_splits_into_rows_of_eight():
    lines = [l for l in bms.cell_grid(CELLS["batVolt"], CELLS["batTemp"]) if l.strip()]
    # 2 packs of (numbers, volts, temps)
    assert len(lines) == 6
    assert "#1" in lines[0] and "#8" in lines[0]
    assert "#9" in lines[3] and "#16" in lines[3]


def test_grid_marks_the_extremes():
    text = "\n".join(bms.cell_grid(CELLS["batVolt"], CELLS["batTemp"]))
    assert "↓3.316V" in text          # lowest cell
    assert "↑3.318V" in text          # highest cell
    assert "*21.4" in text            # hottest cell


def test_grid_handles_a_pack_that_is_not_16_cells():
    lines = bms.cell_grid([3300, 3301, 3302], [20.0, 20.1, 20.2])
    assert "#3" in lines[0] and "#4" not in lines[0]


def test_grid_survives_temps_shorter_than_volts():
    """Never assume the two arrays are the same length."""
    bms.cell_grid([3300, 3301, 3302], [20.0])      # must not raise


# -- full render -------------------------------------------------------------
def test_render_includes_the_key_sections():
    out = "\n".join(bms.render(CELLS, PE, STATES, FW, CHECK))
    for fragment in ("Battery Management", "Pack Health", "Cell Telemetry",
                     "Grid & Bus", "Hardware States"):
        assert fragment in out, fragment


def test_render_reports_charge_direction_from_sign():
    assert "(Charging)" in "\n".join(bms.render({**CELLS, "currGrp": -6.6}))
    assert "(Discharging)" in "\n".join(bms.render({**CELLS, "currGrp": 4.9}))
    assert "(Idle)" in "\n".join(bms.render({**CELLS, "currGrp": 0}))


def test_render_omits_sections_it_cannot_fill():
    """Absent rows must be omitted, not printed blank — the local channel is not a
    degraded cloud view (CLOUD_MAPPING section 3e)."""
    out = "\n".join(bms.render(CELLS))          # cells only, no pe/states/fw
    assert "Cell Telemetry" in out
    assert "Grid & Bus" not in out
    assert "Hardware States" not in out
    assert "Grid Frequency" not in out


def test_render_states_the_local_limitation():
    out = "\n".join(bms.render(CELLS, PE, STATES, FW, CHECK))
    assert "balancing" in out.lower()
    assert "1705" in out


def test_render_survives_an_empty_payload():
    """A failed/partial read must not crash the view."""
    bms.render({})


def test_render_flags_a_nonzero_alarm():
    assert "0 (none)" in "\n".join(bms.render({**CELLS, "alarmLevel": 0}))
    assert "(none)" not in "\n".join(bms.render({**CELLS, "alarmLevel": 3}))


# -- colour ------------------------------------------------------------------
def test_no_colour_output_has_no_escape_codes():
    assert "\033[" not in "\n".join(bms.render(CELLS, PE, STATES, FW, CHECK,
                                               colour=False))


def test_colour_output_has_escape_codes():
    assert "\033[" in "\n".join(bms.render(CELLS, PE, STATES, FW, CHECK, colour=True))


def test_colour_disabled_for_non_tty(monkeypatch):
    class NotATty:
        def isatty(self): return False
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert bms.use_colour(NotATty()) is False


def test_no_color_env_disables_colour(monkeypatch):
    class Tty:
        def isatty(self): return True
    monkeypatch.setenv("NO_COLOR", "1")
    assert bms.use_colour(Tty()) is False


# -- CLI wiring --------------------------------------------------------------
def test_battery_command_and_alias_exist():
    from franklinwh_direct_connect_api.cli import build_parser
    subs = {c for a in build_parser()._subparsers._group_actions for c in a.choices}
    assert "battery" in subs and "bms" in subs


def test_battery_flags_parse():
    from franklinwh_direct_connect_api.cli import build_parser
    args = build_parser().parse_args(
        ["battery", "--id", "2", "--watch", "3", "--for", "5m", "--count", "4"])
    assert args.id == 2 and args.watch == 3.0
    assert args.duration == "5m" and args.count == 4


def test_battery_rejects_a_bad_duration(capsys):
    from franklinwh_direct_connect_api.cli import main
    assert main(["-i", "10.0.0.1", "battery", "--for", "soon"]) == 2
    assert "bad duration" in capsys.readouterr().err


def test_battery_requires_a_host(capsys):
    from franklinwh_direct_connect_api.cli import main
    assert main(["battery"]) == 2
    assert "required" in capsys.readouterr().err
