"""The CLI command surface must stay in sync with the cmdType catalog.

Regression guard for BACKLOG DEF-CLI-CATALOG-DRIFT: `LIVE_COMMANDS` used to be
hand-maintained and had fallen 32 names behind `catalog.CATALOG`, so `catalog`
advertised names the CLI could not run.
"""

from __future__ import annotations

import pytest

from franklinwh_local import catalog
from franklinwh_local.cli import build_parser, live_commands, main


def _subcommands() -> set[str]:
    parser = build_parser()
    return {
        choice
        for action in parser._subparsers._group_actions
        for choice in action.choices
    }


def test_every_catalog_name_is_runnable():
    names = {info.name for info in catalog.CATALOG.values()}
    missing = names - _subcommands()
    assert not missing, f"catalog names with no subcommand: {sorted(missing)}"


def test_live_commands_are_derived_not_listed():
    """Adding a CATALOG row must produce a subcommand with no CLI edit."""
    assert len(live_commands()) >= len(catalog.CATALOG) - 4  # minus dedicated get/set parsers
    for name in live_commands():
        assert name in _subcommands()


def test_catalog_reads_carry_their_cmdtype():
    """Auto-wired reads dispatch via `catalog_cmd`; it must be populated."""
    parser = build_parser()
    for info in catalog.CATALOG.values():
        if info.name in {"mode", "mode_page", "offgrid", "der_comms"}:
            continue  # dedicated get-or-set parsers
        args = parser.parse_args([info.name])
        assert getattr(args, "catalog_cmd", None) == info.request, info.name


def test_unknown_command_is_actionable(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["powerflow"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "power_flow" in err          # near-match suggestion
    assert "catalog" in err             # pointer to discovery


def test_bare_cmdtype_suggests_call(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["1207"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "call 1207" in err
    assert "unknown_1207" in err


def test_offline_command_warns_about_ignored_host(capsys):
    main(["--host", "10.0.0.1", "catalog"])
    assert "ignored" in capsys.readouterr().err


def test_catalog_json_is_machine_readable(capsys):
    main(["catalog", "--json"])
    import json
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == len(catalog.CATALOG)
    by_name = {r["name"]: r for r in rows}
    assert by_name["device_info"]["cloud_api"] == "get_device_info()"
    assert by_name["battery_modules"]["cloud_api"].startswith("get_bms_info()")
    assert by_name["unknown_1207"]["unconfirmed"] is True
    assert "set_mode" in by_name["mode_page"]["writes"]


def test_catalog_grep_filters(capsys):
    main(["catalog", "--grep", "bms"])
    out = capsys.readouterr().out
    assert "battery_modules" in out
    assert "solar_pv" not in out


def test_cloud_annotations_moved_out_of_descriptions():
    """`[cloud: ...]` is a field now, not prose in the description."""
    for info in catalog.CATALOG.values():
        assert "[cloud:" not in info.description
    assert sum(1 for i in catalog.CATALOG.values() if i.cloud_api) >= 40


def test_per_device_reads_expose_an_id_flag():
    """1703/1705/1833/1835 need a device selector; the CLI must offer one."""
    parser = build_parser()
    for code in catalog.NEEDS_ID:
        name = catalog.CATALOG[code].name
        args = parser.parse_args([name, "--id", "2"])
        assert args.id == 2
        assert args.catalog_cmd == code


def test_id_defaults_to_one():
    args = build_parser().parse_args(["battery_cells"])
    assert args.id == 1


def test_battery_cells_is_mapped_to_the_cloud_bms_call():
    assert catalog.CATALOG[1705].name == "battery_cells"
    assert "get_bms_info" in catalog.CATALOG[1705].cloud_api


def test_energy_history_takes_a_date():
    parser = build_parser()
    args = parser.parse_args(["energy_history", "--date", "2026-09-10"])
    assert args.date == "2026-09-10"
    assert args.catalog_cmd == 1303


def test_energy_history_date_defaults_to_today():
    import datetime
    from franklinwh_local.cli import build_parser as bp
    args = bp().parse_args(["energy_history"])
    # main() fills the default; the parser leaves it None
    assert args.date is None
    assert datetime.date.today().isoformat()


def test_energy_history_is_mapped_to_the_cloud_reporting_call():
    """Corrects an earlier claim that the cloud had no reporting equivalent."""
    assert "get_power_by_day" in catalog.CATALOG[1303].cloud_api


def test_energy_channel_order_is_documented():
    assert catalog.ENERGY_CHANNELS == (
        "kwh_uti_in", "kwh_uti_out", "kwh_sun", "kwh_gen",
        "kwh_fhp_di", "kwh_fhp_chg", "kwh_load",
    )


def test_the_211_fan_out_is_mapped():
    """Cloud 211's sub-types map onto several local codes; all should be named."""
    assert catalog.CATALOG[1709].cloud_api == "get_power_info()"
    assert catalog.CATALOG[1833].cloud_api == "get_apower_info()"
    assert "bms_work" in catalog.CATALOG[1835].cloud_api


def test_1703_and_1705_both_map_to_the_type_2_bms_payload():
    """Together they reconstruct cloud get_bms_info() (211 type 2).

    Regression: 1703 was first mapped to get_power_info() (211 type 1) by
    comparing against the wrong sub-type. The DC-bus rails, inverter V/I and
    buckboostCurr it carries are all in the type 2 payload, not type 1.
    """
    assert catalog.CATALOG[1703].cloud_api == "get_bms_info() (211 type 2)"
    assert catalog.CATALOG[1705].cloud_api == "get_bms_info() (211 type 2/3)"


def test_per_device_reads_all_carry_a_cloud_mapping():
    for code in catalog.NEEDS_ID:
        assert catalog.CATALOG[code].cloud_api, f"{code} unmapped"


def test_reconciliation_coverage_is_what_the_docs_claim():
    """CLOUD_MAPPING.md section 0d quotes these counts; keep them honest."""
    total = len(catalog.CATALOG)
    mapped = sum(1 for i in catalog.CATALOG.values() if i.cloud_api)
    assert (total, mapped) == (70, 53), (
        f"catalog changed ({mapped}/{total}) — update CLOUD_MAPPING.md section 0d"
    )


def test_every_unmapped_code_is_genuinely_local_only():
    """Local-only list in section 0c; UNCONFIRMED codes are allowed among them."""
    unmapped = {i.name for i in catalog.CATALOG.values() if not i.cloud_api}
    expected = {
        "login", "device_scan", "device_check", "agate_serial", "time_location",
        "smart_circuit_schedule", "firmware_deliver", "firmware_upgrade",
        "install_profile", "battery_inhibit", "ibg_state", "event_block",
        "unknown_1207", "unknown_1209", "unknown_1821", "unknown_1823", "unknown_1825",
    }
    assert unmapped == expected
