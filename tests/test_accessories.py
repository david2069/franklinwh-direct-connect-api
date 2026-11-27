"""accessories(): generator and V2L state, detected from the keys the aGate returns.

Key shapes: B30D06-like (no `mode`, no V2L keys) and B60D00-like (with them), from the
reference aGate. Labels are the one-site app mapping (docs/FIRMWARE_MAP.md section 6).
"""
import pytest

from franklinwh_direct_connect_api.client import (DirectConnectClient, METRICS_NOTE)

GEN_B30 = {
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
GEN_B60 = dict(GEN_B30, mode=1, gridVoltCheck=2, curr=0, volt=0, freq=500, power=0,
               genpowerGen=0, v2LModeEnable=1, v2LRunState=1, v2LCarRatedPower=3300,
               v2LModeCtrl=0, v2LStartTimeout=0, v2lAccessMethod=0, v2lChargeEna=1,
               v2lOutVoltLevel=0)
PF_B30 = {"run_status": 2, "p_gen": 0, "kwh_gen": 0}
PF_B60 = dict(PF_B30, genStat=0, v2lModeEnable=1, v2lRunState=1)


class Fake(DirectConnectClient):
    def __init__(self, gen, pf, fw=None):
        self._gen, self._pf = dict(gen), dict(pf)
        self._fw = fw or {"IBG_VER": "V12R02B60D00_260924", "protocolVer": "V1.12.02",
                          "SyHdVersion": 102}
        self.sent = []

    def firmware(self):
        return dict(self._fw)

    def generator(self):
        return dict(self._gen)

    def power_flow(self):
        return dict(self._pf)

    def call(self, cmd, block=None):                 # a read must never write
        self.sent.append((cmd, block))
        raise AssertionError("accessories() must not call() anything")


def test_b60_shape_reports_both_accessories_with_labels():
    a = Fake(GEN_B60, PF_B60).accessories()
    g, v = a["generator"], a["v2l"]
    assert g["installed"] is False
    assert (g["mode"], g["mode_raw"]) == ("auto", 1)
    assert (g["start_control"], g["start_control_raw"]) == ("ats", 2)
    assert g["windows"][1] == {"enabled": True, "start": "11:00", "end": "23:59"}
    assert v["reported"] is True and v["installed"] is True
    assert v["raw"]["1901"]["v2LCarRatedPower"] == 3300
    assert a["source"]["SyHdVersion"] == 102


def test_b30_shape_v2l_is_not_reported_not_off():
    """'Not reported by this firmware' must not be read as 'not installed'."""
    a = Fake(GEN_B30, PF_B30).accessories()
    assert a["v2l"] == {"reported": False, "installed": None,
                        "raw": {"1901": {}, "1301": {}}, "note": a["v2l"]["note"]}
    assert a["generator"]["mode"] is None and a["generator"]["mode_raw"] is None
    assert a["generator"]["start_control"] == "dry_contact"


def test_unknown_values_stay_raw_without_a_label():
    a = Fake(dict(GEN_B60, mode=7, gridVoltCheck=9), PF_B60).accessories()
    g = a["generator"]
    assert (g["mode"], g["mode_raw"]) == (None, 7)
    assert (g["start_control"], g["start_control_raw"]) == (None, 9)


def test_flag_absent_is_none_and_unexpected_value_is_none():
    gen = dict(GEN_B60); del gen["genEn"]
    assert Fake(gen, PF_B60).accessories()["generator"]["installed"] is None
    assert Fake(dict(GEN_B60, genEn=2), PF_B60).accessories()["generator"]["installed"] is None


def test_installed_generator_reads_true():
    assert Fake(dict(GEN_B60, genEn=1, v2LModeEnable=0), PF_B60) \
        .accessories()["generator"]["installed"] is True


def test_v2l_flag_from_1301_when_1901_lacks_it():
    gen = {k: v for k, v in GEN_B60.items() if not k.lower().startswith("v2l")}
    a = Fake(gen, PF_B60).accessories()
    assert a["v2l"]["reported"] is True and a["v2l"]["installed"] is True


def test_metrics_are_raw_and_labelled_unestablished():
    m = Fake(GEN_B60, PF_B60).accessories()["generator"]["metrics_raw"]
    assert m["1901"] == {"genStat": 0, "power": 0, "curr": 0, "volt": 0, "freq": 500,
                         "genpowerGen": 0}
    assert m["1301"] == {"genStat": 0, "p_gen": 0, "kwh_gen": 0}
    assert m["note"] == METRICS_NOTE and "not established" in METRICS_NOTE
