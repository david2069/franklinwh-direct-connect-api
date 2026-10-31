"""Wire log: redaction, shape preservation, truncation, and the size ceiling.

The whole value of this feature is that it can be left switched on, so the tests that
matter are the ones proving it cannot leak secrets and cannot fill a disk.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from franklinwh_direct_connect_api import wirelog
from franklinwh_direct_connect_api.client import DirectConnectClient
from franklinwh_direct_connect_api.emulator import Emulator
from franklinwh_direct_connect_api.wirelog import WireLog, redact, truncate


# -- redaction ---------------------------------------------------------------
def test_credentials_and_location_never_reach_the_log():
    """The payloads this protocol carries include a WiFi password and the site's GPS."""
    out = redact({"wifi_SSID": "HomeNet", "wifi_Pw": "hunter2",
                  "ap_Pw": "apsecret", "latitude": -33.8688, "longitude": 151.2093,
                  "postcode": "2069", "soc": 66.5})
    blob = json.dumps(out)
    for secret in ("hunter2", "apsecret", "HomeNet", "33.8688", "151.2093", "2069"):
        assert secret not in blob, f"{secret!r} leaked into the wire log"
    assert out["soc"] == 66.5                     # non-sensitive values survive intact


def test_redaction_preserves_container_shape():
    """A list stays a list, so the log can answer "one per aPower, or one value?".

    Collapsing `["SN"]` to `<redacted:1>` would make a one-element list
    indistinguishable from a one-character string -- which is exactly the question the
    1102 login manifest's field shapes turn on.
    """
    out = redact({"FHP_SN": ["A" * 20, "B" * 20], "BMS_SN": ["C" * 20], "IBG_SN": "D" * 20})
    assert isinstance(out["FHP_SN"], list) and len(out["FHP_SN"]) == 2
    assert isinstance(out["BMS_SN"], list) and len(out["BMS_SN"]) == 1
    assert isinstance(out["IBG_SN"], str)         # a scalar stays a scalar
    assert out["IBG_SN"] == "<redacted:20>"       # length kept: a truncated serial shows


def test_unknown_serial_fields_are_redacted_by_suffix():
    """A `*_SN` field this list has never heard of is still hidden -- fail safe."""
    out = redact({"WIDGET_SN": "SECRET-SERIAL", "widget_sn": "ALSO-SECRET"})
    assert "SECRET-SERIAL" not in json.dumps(out)
    assert "ALSO-SECRET" not in json.dumps(out)


def test_nested_payloads_are_redacted():
    out = redact({"devMap": [{"devSN": "SECRET1", "id": 1}, {"devSN": "SECRET2", "id": 2}]})
    blob = json.dumps(out)
    assert "SECRET1" not in blob and "SECRET2" not in blob
    assert out["devMap"][0]["id"] == 1            # structure and non-secrets intact


# -- truncation --------------------------------------------------------------
def test_long_arrays_are_clipped_and_say_so():
    """Per-cell reads return long arrays; a clipped one must admit it was clipped."""
    out = truncate({"batVolt": list(range(100))}, max_items=5, max_chars=50)
    assert len(out["batVolt"]) == 6               # 5 kept + the marker
    assert out["batVolt"][-1] == "...+95 more"


def test_long_strings_are_clipped_and_say_so():
    out = truncate({"blob": "x" * 200}, max_items=5, max_chars=10)
    assert out["blob"] == "x" * 10 + "...(+190)"


def test_short_values_are_left_exactly_alone():
    """A reader must be able to tell an untouched payload from a clipped one."""
    payload = {"soc": 66.5, "name": "Self-Consumption", "list": [1, 2, 3]}
    assert truncate(payload, max_items=5, max_chars=50) == payload


# -- the size ceiling --------------------------------------------------------
def test_rotation_keeps_total_bytes_under_the_ceiling(tmp_path):
    """Left running, the log must not grow without bound. This is the point."""
    log = WireLog(tmp_path / "w.jsonl", max_bytes=2048, backups=2).open()
    try:
        for _ in range(400):                      # far more than 3 x 2048 bytes
            log.log("req", 1301, {"opt": 0, "pad": "y" * 100})
        assert log.rotations > 0, "never rotated -- the cap did nothing"
        assert log.total_bytes() <= log.max_total_bytes
        assert log.max_total_bytes == 2048 * 3
        # The oldest file is deleted rather than accumulated.
        assert not (tmp_path / "w.jsonl.3").exists()
    finally:
        log.close()


def test_zero_backups_still_bounded(tmp_path):
    """backups=0 truncates in place; disk use stays under one file's cap."""
    log = WireLog(tmp_path / "w.jsonl", max_bytes=1024, backups=0).open()
    try:
        for _ in range(200):
            log.log("req", 1301, {"pad": "z" * 100})
        assert log.total_bytes() <= 1024
    finally:
        log.close()


def test_an_unbounded_log_cannot_be_constructed():
    with pytest.raises(ValueError, match="max_bytes"):
        WireLog("x.jsonl", max_bytes=0)
    with pytest.raises(ValueError, match="backups"):
        WireLog("x.jsonl", backups=-1)


def test_a_broken_log_does_not_break_the_caller(tmp_path):
    """A logging failure must never cost a device call."""
    log = WireLog(tmp_path / "w.jsonl").open()
    log._fh.close()                               # sabotage the handle underneath it
    log.log("req", 1301, {"opt": 0})              # must not raise
    log.close()


# -- end to end against the emulator ----------------------------------------
@pytest.fixture
def emulator():
    emu = Emulator("127.0.0.1", 0).start()
    yield emu
    emu.stop()


def test_full_payloads_are_logged_by_default(tmp_path, emulator):
    """Nothing is masked unless asked for: the default is what went over the wire.

    A debug log that quietly alters the payload is worse than none, because the field
    you are chasing is the one that got starred out.
    """
    path = tmp_path / "w.jsonl"
    with WireLog(path) as wl:
        with DirectConnectClient("127.0.0.1", emulator.port, timeout=3.0, wire_log=wl) as c:
            c.login()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    manifest = next(r for r in records if r["cmdType"] == 1102)
    assert manifest["dataArea"]["IBG_SN"] == emulator.equip_no     # verbatim, not masked
    assert "<redacted:" not in path.read_text()
    assert all("redacted" not in r for r in records)   # unmarked = holds real values


def test_the_login_exchange_is_captured(tmp_path, emulator):
    """The 1101/1102 login is the exchange a caller never makes explicitly, and the
    one a bug report most often needs. Hooking at frame level is what gets it."""
    path = tmp_path / "w.jsonl"
    with WireLog(path) as wl:
        with DirectConnectClient("127.0.0.1", emulator.port, timeout=3.0, wire_log=wl) as c:
            c.login()
            c.power_flow()

    records = [json.loads(line) for line in path.read_text().splitlines()]
    pairs = [(r["dir"], r["cmdType"]) for r in records]
    assert ("req", 1101) in pairs and ("resp", 1102) in pairs
    assert ("req", 1301) in pairs and ("resp", 1302) in pairs

    reply = next(r for r in records if r["cmdType"] == 1302)
    assert reply["name"] == "power_flow (reply)"  # responses are named, not bare numbers
    assert reply["ms"] >= 0                        # round-trip time recorded
    assert "soc" in reply["dataArea"]              # the useful payload is still there

    manifest = next(r for r in records if r["cmdType"] == 1102)
    assert "IBG_SN" in manifest["dataArea"]


def test_process_default_is_picked_up_without_passing_it(tmp_path, emulator):
    """How `--wire-log` reaches every subcommand without threading a parameter.

    The module is resolved HERE rather than at import time, deliberately. The default
    lives in a module global, and `test_deprecated_alias` purges the package from
    `sys.modules` to re-import it cold -- after which a reference captured at collection
    time points at a dead module whose global nobody reads. The CLI resolves the module
    inside `main()` for the same reason, so this mirrors how it is really used. Without
    this, the test passes alone and fails in the suite, which is worse than either.
    """
    wl_mod = importlib.import_module("franklinwh_direct_connect_api.wirelog")
    path = tmp_path / "w.jsonl"
    with WireLog(path) as wl:
        wl_mod.set_default(wl)
        try:
            with DirectConnectClient("127.0.0.1", emulator.port, timeout=3.0) as c:
                c.login()
        finally:
            wl_mod.set_default(None)
    assert any(json.loads(l)["cmdType"] == 1101 for l in path.read_text().splitlines())

    # Cleared afterwards: a later client must not keep writing to a closed log.
    assert wl_mod.get_default() is None


def test_redact_mode_masks_serials_and_marks_itself(tmp_path, emulator):
    """`redact=True` is the form you can send to someone: no serial reaches disk."""
    path = tmp_path / "red.jsonl"
    with WireLog(path, redact=True) as wl:
        with DirectConnectClient("127.0.0.1", emulator.port, timeout=3.0, wire_log=wl) as c:
            c.login()
    text = path.read_text()
    records = [json.loads(line) for line in text.splitlines()]
    assert emulator.equip_no not in text, "a serial reached a redacted log"
    manifest = next(r for r in records if r["cmdType"] == 1102)
    assert manifest["dataArea"]["IBG_SN"].startswith("<redacted:")
    # Marked, so the REDACTED file is the identifiable one. An unmarked file must be
    # assumed to hold real values -- the safe direction for whoever finds it.
    assert all(r.get("redacted") is True for r in records)


def test_wire_logs_cannot_be_committed_by_accident():
    """The default log holds real serials, so git must refuse it outright."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["git", "check-ignore", "-q", str(root / "wire.jsonl")],
                         cwd=root, capture_output=True)
    assert out.returncode == 0, "*.jsonl is not gitignored -- a full wire log could be committed"


# -- the measured 1102 shape (reference aGate, 2026-10-31) -------------------
#: Field shapes measured on the reference aGate 2026-10-31, IBG_VER
#: V12R02B60D00_260924, protocolVer V1.12.02, ONE aPower. Recorded here so a change
#: to FIRMWARE_FIELDS cannot silently drop a field the device actually sends.
MANIFEST_LISTS = (
    "FHP_SN", "PE_SN", "BMS_SN", "FPGA_VER", "DCDC_VER", "INV_VER", "BMS_VER",
    "BL_VER", "TH_VER", "PE_HW_VER", "BMS_MAIN_HW_VER", "BMS_BL_HW_VER", "BMS_TH_HW_VER",
)
MANIFEST_SCALARS = (
    "IBG_SN", "IBG_VER", "APP_VER", "AWS_VER", "SL_VER", "METER_VER", "protocolVer",
    "FHP_NUM", "SyHdVersion", "deviceType", "threePhasePvPower",
)


def test_firmware_fields_covers_every_measured_manifest_key():
    """`firmware()` must not silently drop a field the gateway really sends.

    Six keys were missing until 2026-10-31 -- the four per-aPower *_HW_VER lists,
    deviceType and threePhasePvPower -- so `firmware()` quietly omitted them. It
    filters by known key, so an unknown field fails silently rather than loudly,
    which is why this is pinned by a test rather than left to review.
    """
    from franklinwh_direct_connect_api.client import DirectConnectClient

    fields = set(DirectConnectClient.FIRMWARE_FIELDS)
    missing = [k for k in MANIFEST_LISTS + MANIFEST_SCALARS if k not in fields]
    assert not missing, f"measured 1102 keys absent from FIRMWARE_FIELDS: {missing}"


def test_sunspec_fw_is_not_treated_as_a_manifest_key():
    """It does not exist in the reply; it was invented elsewhere and withdrawn."""
    from franklinwh_direct_connect_api.client import DirectConnectClient

    assert "SUNSPEC_FW" not in DirectConnectClient.FIRMWARE_FIELDS


def test_redaction_keeps_every_measured_list_a_list():
    """The shapes the live read established must survive a redacted log.

    This is what makes a redacted capture usable as shape evidence: a reader has to
    be able to tell a one-element list from a short string.
    """
    manifest = {k: ["X" * 22] for k in MANIFEST_LISTS}
    manifest.update({k: "Y" * 20 for k in MANIFEST_SCALARS})
    out = redact(manifest)
    for key in MANIFEST_LISTS:
        assert isinstance(out[key], list), f"{key} lost its list shape under redaction"
        assert len(out[key]) == 1
    for key in MANIFEST_SCALARS:
        assert not isinstance(out[key], list), f"{key} gained a list shape"


# -- redaction must survive vendor misspellings ------------------------------
def test_the_agate_latitude_misspelling_is_still_redacted():
    """The aGate spells latitude "laitude", and the exact-name list missed it.

    This was a real disclosure: `--wire-log-redact` wrote the site's latitude in
    the clear while still stamping the record `"redacted": true` -- the one mode
    whose entire purpose is to be safe to share. Longitude and postcode were
    masked, which made the output look trustworthy.
    """
    out = redact({"laitude": -33.8688, "longitude": 151.2093, "postcode": "2069"})
    blob = json.dumps(out)
    for leak in ("33.8688", "151.2093", "2069"):
        assert leak not in blob, f"{leak} leaked through redaction"


@pytest.mark.parametrize("field", [
    "laitude", "latitude", "Latitude", "LAITUDE", "gps_latitude", "siteLongitude",
    "altitude", "postCode", "postal_code", "zipcode",
    "wifi_Password", "ap_pwd", "wifiPasswd",
    "MAC", "mac_addr", "eth0_mac", "router_ip", "dns_1",
    "WIDGET_SN", "widget_sn", "serialNumber", "fhp_serial",
])
def test_plausible_spellings_of_a_sensitive_field_are_all_redacted(field):
    """Over-redaction is harmless here; under-redaction is a disclosure.

    An exact-name allowlist cannot survive a vendor typo, and this protocol has
    several. Matching is therefore by exact name, `*_SN` suffix, substring pattern
    and whole token -- deliberately generous.
    """
    out = redact({field: "SECRET-VALUE-12345"})
    assert "SECRET-VALUE-12345" not in json.dumps(out), f"{field} was not redacted"


@pytest.mark.parametrize("field", ["machine", "clipping", "capacity", "soc", "p_load",
                                   "mode", "name", "serialization_mode"])
def test_ordinary_fields_are_not_over_redacted(field):
    """The broad patterns must not swallow telemetry. "mac" must not match
    "machine", and "ip" must not match "clipping" -- a log that hides the data you
    are debugging is useless."""
    out = redact({field: "KEEP-ME"})
    if field == "serialization_mode":
        assert out[field] == "<redacted:7>"      # contains "serial": masked, acceptable
    else:
        assert out[field] == "KEEP-ME", f"{field} was over-redacted"
