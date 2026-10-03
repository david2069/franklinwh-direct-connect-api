"""Generator (1901) and smart-circuit schedule (1409) write paths.

Grounded in live testing on FW V12R02B30D06, 2026-09-14: generator writes APPLY,
smart-circuit schedule writes are ACCEPTED AND DISCARDED. The asymmetry is the
point — these tests pin both halves so neither is generalised to the other.
"""
import pytest

from franklinwh_local import catalog
from franklinwh_local.client import LocalClient, _validate_hhmm

GEN = {
    "opt": 0, "result": 0, "reason": 0,
    "genEn": 0, "genModel": "", "genRatedPower": 0, "genStat": 0, "manuSw": 0,
    "genStartElec": 20, "genCloseElec": 80, "startDelTime": 1800,
    "genOptiPPoint": 70, "gridVoltCheck": 3,
    "charge1En": 1, "charge1StartTime": "11:00", "charge1EndTime": "23:59",
    "charge2En": 0, "charge2StartTime": "00:00", "charge2EndTime": "00:00",
    "charge3En": 0, "charge3StartTime": "00:00", "charge3EndTime": "00:00",
    "oilmanoEn": 0, "manoFre": 7, "manoDate": 0, "manoStartTime": "",
    "manoTime": 5, "manoManExit": 0,
}


class FakeGen(LocalClient):
    """Applies writes like the real 1901 does."""

    def __init__(self, applies=True):
        self.state = dict(GEN)
        self.applies = applies
        self.sent = []

    def generator(self):
        return dict(self.state)

    def call(self, cmd, block=None):
        self.sent.append((cmd, block))
        if self.applies:
            self.state.update({k: v for k, v in (block or {}).items()
                               if k not in ("opt", "result", "reason")})
        return {"result": 0, "reason": 0}


def test_window_write_applies_and_confirms():
    c = FakeGen()
    out = c.set_generator_window(2, True, "02:00", "03:30")
    assert out["ok"] and out["confirmed"]
    assert out["after"]["charge2StartTime"] == "02:00"
    assert out["before"]["charge2En"] == 0


def test_whole_block_is_echoed_so_other_windows_survive():
    c = FakeGen()
    c.set_generator_window(2, True, "02:00", "03:30")
    _, block = c.sent[0]
    assert block["charge1StartTime"] == "11:00"     # untouched window preserved
    assert block["manoFre"] == 7                    # and the exercise schedule
    assert block["opt"] == 1


def test_soc_thresholds_validated():
    c = FakeGen()
    assert c.set_generator_soc(25, 85)["ok"]
    with pytest.raises(ValueError):
        c.set_generator_soc(80, 20)                 # stop must exceed start
    with pytest.raises(ValueError):
        c.set_generator_soc(-1, 50)


def test_exercise_write():
    c = FakeGen()
    out = c.set_generator_exercise(enabled=True, every_days=14, minutes=9, start="03:00")
    assert out["ok"] and out["after"]["manoFre"] == 14
    with pytest.raises(ValueError):
        c.set_generator_exercise()                  # nothing to change


def test_unknown_field_rejected_before_hitting_the_wire():
    c = FakeGen()
    with pytest.raises(ValueError):
        c.set_generator(genTurbo=1)
    assert not c.sent


def test_silent_discard_is_not_reported_as_success():
    """result:0 with no change must yield ok=False — the 1405/1409 signature."""
    c = FakeGen(applies=False)
    out = c.set_generator_window(2, True, "02:00", "03:30")
    assert out["result"] == 0
    assert out["ok"] is False and out["confirmed"] is False
    assert out["mismatched"]["charge2En"]["requested"] == 1


def test_bad_window_number():
    with pytest.raises(ValueError):
        FakeGen().set_generator_window(4, True, "01:00", "02:00")


def test_hhmm_validation():
    assert _validate_hhmm("7:5") == "07:05"
    for bad in ("24:00", "1:99", "noon", "", None):
        with pytest.raises(ValueError):
            _validate_hhmm(bad)


# ── the asymmetry, pinned ────────────────────────────────────────────────────
def test_generator_write_is_catalogued_as_verified():
    note = catalog.WRITES["set_generator"]["note"]
    assert catalog.WRITES["set_generator"]["cmd"] == 1901
    assert "HARDWARE-VERIFIED" in note


def test_circuit_schedule_is_catalogued_as_discarded():
    d = catalog.DISCARDED_WRITES["smart_circuit_schedule"]
    assert d["cmd"] == 1409 and d["firmware"] == "V12R02B30D06"
    assert "result:1 reason:-2" in d["note"]        # the 1401 refusal


def test_1401_description_warns_it_is_not_the_schedule_source():
    desc = catalog.CATALOG[1401].description
    assert "NOT the schedule source" in desc
    assert "REFUSED" in desc


def test_discarded_note_records_the_newer_387_path_and_its_limits():
    """A newer cloud cmdType exists but does not reopen this on local firmware."""
    note = catalog.DISCARDED_WRITES["smart_circuit_schedule"]["note"]
    assert "387" in note                       # the newer path is recorded
    assert "CLOSES THE CONNECTION" in note      # local broker rejects it
    assert "never writes it" in note            # and nobody writes schedule yet


def test_catalog_descriptions_stay_readable():
    """Descriptions render verbatim in the bridge's Device tab.

    One grew to 2,378 characters against a ~73-character median and swamped the
    panel. Research belongs in the backlog; the catalog says what a command IS.
    """
    long = {code: len(i.description or "")
            for code, i in catalog.CATALOG.items() if len(i.description or "") > 1000}
    assert not long, (
        f"catalog description(s) too long for the UI: {long}. "
        f"Summarise and link to the backlog entry instead."
    )


def test_1405_is_documented_as_full_block_writable():
    """Corrects the older 'accepted then discarded' note, measured on a partial frame.

    Proven 2026-09-14: partial -> result:1 reason:-2 (refused); full block -> applies
    (BBBackupSoc 20->25->20 with read-back). The eight min/max fields stay inert.
    """
    d = catalog.CATALOG[1405].description.lower()
    assert "full-block only" in d
    assert "reason:-2" in d          # the refusal signature
    assert "inert" in d              # min/max fields do not hold a value


def test_read_payloads_cover_the_commands_that_reject_opt_zero():
    """1725 answers ONLY opt:1 — opt:0 draws no reply and blocks until timeout.

    This is what made eleven 1725 'write' attempts meaningless: opt:1 is the READ,
    so each one was just a re-read returning unchanged state.
    """
    assert catalog.read_payload(1725) == {"opt": 1}
    assert catalog.read_payload(1301) == {"opt": 0}      # the ordinary case
    for cmd in (1705, 1703, 1833, 1835):
        assert "id" in catalog.read_payload(cmd)
    assert "date" in catalog.read_payload(1303)


def test_transport_records_the_frame_it_sent():
    """Provenance: the UI must be able to SHOW the request, not reconstruct it."""
    from franklinwh_local.transport import LocalTransport
    assert hasattr(LocalTransport, "last_request")


def test_device_state_enums_match_the_cloud():
    """bmsState/peState DO have enums — an earlier note wrongly said they had none."""
    assert catalog.bms_state_desc(7) == "Discharging"
    assert catalog.bms_state_desc(5) == "Standby"
    assert catalog.pcs_state_desc(8) == "Online / Running"
    assert "unknown" in catalog.bms_state_desc(99)      # never invent a label
