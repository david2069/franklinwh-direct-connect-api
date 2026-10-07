"""
Dynamic, per-seed synthetic aGate site model for the emulator.

A :class:`SyntheticSite` turns a single integer ``seed`` into a stable, deterministic
"virtual aGate": a unique serial, a solar/battery/load curve that follows the local
time of day, and the three payloads the local broker returns for the live dashboard
reads (1302 power flow, 1726 mode list, 1102 login manifest).

The physics are a straight port of the Modbus Bridge's
``gateway/mock_gateway.py::synthetic_points()`` — a daytime half-sine solar bell,
a breakfast/dinner load profile, a battery that soaks up solar surplus and discharges
in the evening, and a SoC integrated across the day — re-expressed in the REAL local
field names (``p_sun``/``p_fhp``/``p_uti``/``p_load``/``soc``/``t_amb``) and the local
sign conventions.

Determinism: everything derives from ``seed`` via ``random.Random(seed)`` plus ``math``
and the request timestamp. No global RNG, no wall-clock hidden state — the same seed
yields the same serial and the same curve at a given ``ts``. Stdlib only.
"""

from __future__ import annotations

import datetime
import math
import random
from typing import Any

from . import catalog

# Site-fixed programme ids per mode (arbitrary but stable — the local broker selects a
# mode by these site-specific ids). Mirrors the ids used across the docs/CLI examples.
MODE_IDS: dict[str, int] = {
    "Self-Consumption": 85232,
    "Time-of-Use": 29287,
    "Emergency Backup": 47522,
}

# Reserve floor SoC (%) per mode, and the cloud ``workMode`` (== 1726 scheduling_type).
MODE_RESERVE: dict[str, int] = {
    "Self-Consumption": 5,
    "Time-of-Use": 15,
    "Emergency Backup": 100,
}
MODE_WORKMODE: dict[str, int] = {
    "Time-of-Use": 1,
    "Self-Consumption": 2,
    "Emergency Backup": 3,
}

_HEX = "0123456789ABCDEF"


class SyntheticSite:
    """A deterministic virtual aGate derived from an integer ``seed``.

    Parameters
    ----------
    seed:
        Any integer. Drives every per-site parameter (serial, solar capacity, base
        load, battery size, morning SoC, timezone offset).
    serial:
        Optional explicit IBG_SN override. When ``None`` a unique 20-char serial that
        embeds the seed is generated, so multiple seeds always look like distinct
        devices to a multi-gateway consumer.
    """

    def __init__(self, seed: int, serial: str | None = None):
        self.seed = int(seed)
        rng = random.Random(self.seed)

        # Per-site physical parameters (stable for the life of the site).
        self.solar_peak_kw = 3.5 + 2.5 * rng.random()   # 3.5–6 kW peak solar
        self.home_base_w = 400.0 + 400.0 * rng.random()  # 400–800 W base load
        self.batt_cap_kw = 2.0 + 1.5 * rng.random()      # 2–3.5 kW battery power limit
        self.soc_morning = 25.0 + 20.0 * rng.random()    # morning SoC base 25–45 %
        # Timezone offset so different mocks sit at different times of day (demo colour).
        self.tz_offset_hours = rng.randint(-11, 12)

        # Unique, collision-free serials. "MOCK" + 4-digit seed + 12 hex = 20 chars,
        # matching the real 20-char IBG_SN shape (and the header's [0-9A-Za-z] charset).
        gen = "".join(rng.choice(_HEX) for _ in range(12))
        self.serial = serial or f"MOCK{self.seed % 10000:04d}{gen}"
        fhp = "".join(rng.choice(_HEX) for _ in range(12))
        self.fhp_serial = f"MFHP{self.seed % 10000:04d}{fhp}"

        # ── mutable state so WRITES round-trip (reads reflect them) ──
        # Mode set via 1727 opt:3 pins the operating mode until changed; smart-circuit
        # writes (1409 opt:1) persist per-circuit on/off so a toggle actually sticks.
        self._mode_override_name: str | None = None
        self._circuits: dict[str, Any] = self._init_circuits()

    # -- current mode (write override wins over the time-of-day schedule) -----
    def _current_mode(self, ts: float) -> str:
        if self._mode_override_name:
            return self._mode_override_name
        return self.mode_for_hour(self.local_hour(ts))

    # -- time helpers --------------------------------------------------------
    def local_hour(self, ts: float) -> float:
        """Fractional local hour (0–24) at unix time ``ts`` for this site."""
        local = ts + self.tz_offset_hours * 3600.0
        return (local % 86400.0) / 3600.0

    def mode_for_hour(self, hour: float) -> str:
        """Active mode name for a local ``hour`` (port of mock_gateway blocks)."""
        if hour < 6.0 or hour >= 22.0:
            return "Emergency Backup"
        if 17.0 <= hour < 22.0:
            return "Time-of-Use"
        return "Self-Consumption"

    # -- 1302 power flow -----------------------------------------------------
    def snapshot(self, ts: float) -> dict[str, Any]:
        """Build the 1302 ``power_flow`` payload for unix time ``ts``.

        Sign conventions (verified against the bridge/library):
          - ``p_sun`` solar production, >= 0 (0 at night)
          - ``p_fhp`` battery: negative = charging, positive = discharging
          - ``p_uti`` grid: positive = importing, negative = exporting
          - ``p_load`` house load, >= 0
          - ``p_gen`` generator, 0
        Energy is balanced exactly via ``p_load = p_sun + p_uti + p_fhp + p_gen``.
        """
        seed = self.seed or 1
        hour = self.local_hour(ts)
        mode = self._current_mode(ts)
        reserve = MODE_RESERVE[mode]

        # ── Solar: half-sine bell, zero before dawn / after dusk, cloud ripple ──
        dawn, dusk = 6.0, 20.0
        solar_factor = max(0.0, math.sin((hour - dawn) * math.pi / (dusk - dawn)))
        cloud_noise = 0.88 + 0.12 * math.sin(ts / 15.0 + seed * 0.7)
        p_sun = round(self.solar_peak_kw * 1000 * solar_factor ** 1.3 * cloud_noise, 1)
        p_sun = max(0.0, p_sun)

        # ── House load: base + breakfast (8h) + dinner (19h) gaussians + jitter ──
        morning_peak = 900 * math.exp(-((hour - 8.0) ** 2) / 1.5)
        evening_peak = 1400 * math.exp(-((hour - 19.0) ** 2) / 3.5)
        load_jitter = 1.0 + 0.04 * math.sin(ts / 4.0 + seed * 1.3)
        p_load = round(max(0.0, (self.home_base_w + morning_peak + evening_peak) * load_jitter), 1)

        # ── SoC: integrate a morning-low → afternoon-high → evening-low curve ──
        soc_noon_peak = min(95.0, self.soc_morning + 55.0)
        soc_curve = self.soc_morning + (soc_noon_peak - self.soc_morning) * max(
            0.0, math.sin(max(0.0, (hour - 6.0) * math.pi / 14.0))
        ) ** 0.7
        soc_jitter = 0.3 * math.sin(ts / 25.0 + seed * 0.5)
        soc = round(max(5.0, min(98.0, soc_curve + soc_jitter)), 1)

        # ── Battery: soak up surplus (charge), cover deficit (discharge) ──
        # Respect the mode reserve floor and the ~98% charge ceiling and the power limit.
        cap_w = self.batt_cap_kw * 1000.0
        net_surplus = p_sun - p_load           # >0 surplus, <0 deficit
        raw_batt = -net_surplus * 0.75          # negative = charging (convention)
        p_fhp = max(-cap_w, min(cap_w, raw_batt))
        if p_fhp < 0 and soc >= 98.0:            # full — cannot charge further
            p_fhp = 0.0
        if p_fhp > 0 and soc <= reserve:         # at reserve — cannot discharge further
            p_fhp = 0.0
        p_fhp = round(p_fhp, 1)

        p_gen = 0.0
        # Exact energy balance: grid makes up the difference (positive = import).
        p_uti = round(p_load - p_sun - p_fhp - p_gen, 1)

        # ── run_status mirrors the physical battery direction (cloud vocabulary) ──
        if p_fhp <= -50.0:
            run_status = 1   # Charging
        elif p_fhp >= 50.0:
            run_status = 2   # Discharging
        else:
            run_status = 0   # Standby

        # ── Ambient temperature drift ──
        temp_base_amb = 18 + (seed % 8)
        temp_drift = math.sin(ts / 40.0 + seed * 0.4) * 1.5
        t_amb = round(temp_base_amb + 4.0 * solar_factor + temp_drift, 1)

        # Synthetic daily energy accumulators (kWh since local midnight) so the bridge's
        # "Energy Today" card is populated for a mock. Coarse integrals of the day's
        # curves — plausible and monotonic through the day, reset at midnight.
        prog = min(1.0, max(0.0, (hour - 6.0) / 14.0)) ** 0.85     # 0 at dawn → 1 at dusk
        kwh_sun = round(max(0.0, self.solar_peak_kw * 3.0 * prog), 2)
        kwh_load = round(max(0.0, (self.home_base_w / 1000.0) * hour + 2.5 * prog), 2)
        kwh_fhp_chg = round(kwh_sun * 0.45, 2)
        kwh_fhp_di = round(kwh_load * 0.35, 2)
        kwh_uti_out = round(max(0.0, kwh_sun - kwh_load - kwh_fhp_chg) * 0.6, 2)
        kwh_uti_in = round(max(0.0, kwh_load - kwh_sun - kwh_fhp_di) * 0.5, 2)
        return {
            "opt": 0,
            "result": 0,
            "mode": MODE_IDS[mode],
            "name": mode,
            "run_status": run_status,
            "p_uti": p_uti,
            "p_sun": p_sun,
            "p_gen": p_gen,
            "p_fhp": p_fhp,
            "p_load": p_load,
            "soc": soc,
            "t_amb": t_amb,
            "kwh_sun": kwh_sun,
            "kwh_load": kwh_load,
            "kwh_fhp_chg": kwh_fhp_chg,
            "kwh_fhp_di": kwh_fhp_di,
            "kwh_uti_out": kwh_uti_out,
            "kwh_uti_in": kwh_uti_in,
            "kwh_gen": 0,
        }

    # -- 1726 mode list ------------------------------------------------------
    def mode_list(self, ts: float | None = None) -> dict[str, Any]:
        """Build the 1726 ``mode_list`` payload (3 modes + current_id).

        ``current_id`` is the programme id of the mode active at ``ts`` (defaults to the
        Self-Consumption id when ``ts`` is not supplied — i.e. the identity of the list is
        stable, only the highlighted current mode tracks time)."""
        if ts is None:
            current = "Self-Consumption"
        else:
            current = self._current_mode(ts)
        entries = []
        for name in ("Self-Consumption", "Time-of-Use", "Emergency Backup"):
            entries.append({
                "id": MODE_IDS[name],
                "name": name,
                "reserved_soc": MODE_RESERVE[name],
                "scheduling_type": MODE_WORKMODE[name],
                "electricity_type": 0,
            })
        return {"opt": 0, "result": 0, "current_id": MODE_IDS[current], "list": entries}

    # -- 1102 login manifest -------------------------------------------------
    def login_manifest(self) -> dict[str, Any]:
        """Build the 1102 login/firmware manifest payload (seeded IBG_SN/FHP_SN + *_VER)."""
        return {
            "opt": 0,
            "result": 0,
            "IBG_SN": self.serial,
            "FHP_NUM": 1,
            "FHP_SN": [self.fhp_serial],
            "protocolVer": "V1.11.01",
            "IBG_VER": "V12R02B30D06",
            "APP_VER": "V2.0.0",
            "AWS_VER": "V1.0.0",
            "BMS_VER": "V1.2.3",
            "INV_VER": "V3.1.0",
            "DCDC_VER": "V1.0.5",
            "METER_VER": "V1.0.0",
        }

    # -- 1404 / 1708 mode reflection (trivial, optional) ---------------------
    def mode_config(self, ts: float) -> dict[str, Any]:
        """1404 ``mode_config`` reflecting the current mode."""
        mode = self._current_mode(ts)
        return {"opt": 0, "result": 0, "runingMode": MODE_IDS[mode],
                "modeChoose": MODE_WORKMODE[mode], "name": mode}

    def ibg_run_status(self, ts: float) -> dict[str, Any]:
        """1708 ``ibg_run_status`` reflecting the current mode."""
        mode = self._current_mode(ts)
        return {"opt": 0, "result": 0, "ibgRunStatus": MODE_IDS[mode],
                "name": mode, "energyMode": MODE_WORKMODE[mode]}

    # -- 1727 mode set (write round-trip) ------------------------------------
    def set_mode_write(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist a mode change (1727 opt:3 ``current_id``) so later reads reflect it."""
        cid = data.get("current_id")
        if cid is not None:
            for name, mid in MODE_IDS.items():
                if int(mid) == int(cid):
                    self._mode_override_name = name
                    break
        return {"opt": 0, "result": 0, "reason": 0}

    # -- 1409 smart circuits (read + write round-trip) -----------------------
    _CIRCUIT_NAMES = ("Water Heater", "EV Charger", "Air Conditioner")

    def _init_circuits(self) -> dict[str, Any]:
        d: dict[str, Any] = {"SwMerge": 0}
        for i in (1, 2, 3):
            on = i != 3                       # 1 & 2 on, 3 off by default
            d[f"Sw{i}Name"] = self._CIRCUIT_NAMES[i - 1]
            d[f"Sw{i}Mode"] = 1 if on else 0
            d[f"Sw{i}ProLoad"] = 0 if on else 1
            d[f"Sw{i}MsgType"] = 0
        return d

    def smart_circuits(self) -> dict[str, Any]:
        """1410 smart-circuit config: SwMerge + Sw{1..3}Name/Mode/ProLoad."""
        return {"opt": 0, "result": 0, "reason": 0, **self._circuits}

    def apply_smart_circuit_write(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist a 1409 opt:1 full-block write so the read-back confirms the toggle."""
        for k, v in data.items():
            if k.startswith("Sw"):
                self._circuits[k] = v
        return {"opt": 0, "result": 0, "reason": 0}

    # -- 1303 energy history (96 quarter-hour points for one stored day) ------
    def _tou_tier(self, hour: float) -> str:
        """Fixed tariff schedule for the tier split (sharp is deprecated -> unused)."""
        if hour >= 22.0 or hour < 7.0:
            return "valley"
        if 17.0 <= hour < 21.0:
            return "peak"
        return "flat"

    def energy_history(self, date_str: Any, now: float | None = None) -> dict[str, Any]:
        """1304 daily history: 96 quarter-hour points + seven kwh_* totals + tier splits.

        Mirrors the real device: requires ``date`` = 'YYYY-MM-DD', returns ~105 days of
        rolling history (older -> sno=0, empty), integrates the day's power curves into
        the totals, and buckets each into sharp/peak/flat/valley (each channel's four
        tiers sum to its total). Unlike the firmware, ``p_load`` is the true home load
        here (real hardware duplicates p_fhp into it — DEF-1303-PLOAD-DUP).
        """
        empty = {"opt": 0, "result": 0, "reason": 0, "sno": 0, "dayType": 0,
                 "pointMax": 96, "pointId": 0, "rec_time": [],
                 "p_uti": [], "p_gen": [], "p_fhp": [], "p_load": []}
        if not isinstance(date_str, str):
            return empty
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            return empty
        ref = datetime.datetime.fromtimestamp(now if now is not None else 0).date() \
            if now is not None else datetime.date.today()
        age = (ref - d).days
        if age < 0 or age > 105:                       # rolling ~105-day retention
            return empty

        midnight = (datetime.datetime(d.year, d.month, d.day).timestamp()
                    - self.tz_offset_hours * 3600)
        CH = catalog.ENERGY_CHANNELS
        rec_time: list[str] = []
        p_uti: list[int] = []; p_gen: list[int] = []
        p_fhp: list[int] = []; p_load: list[int] = []
        tot = {c: 0.0 for c in CH}
        tiers = {t: [0.0] * len(CH) for t in catalog.TIERS}
        for q in range(1, 97):
            ts = midnight + q * 900
            snap = self.snapshot(ts)
            mins = q * 15
            rec_time.append(f"{mins // 60:02d}:{mins % 60:02d}")   # 00:15 .. 24:00
            pu = round(snap["p_uti"]); pf = round(snap["p_fhp"]); pl = round(snap["p_load"])
            p_uti.append(pu); p_gen.append(0); p_fhp.append(pf); p_load.append(pl)
            e = 0.25 / 1000.0                                       # W for 15 min -> kWh
            contrib = {
                "kwh_uti_in": max(0, pu) * e, "kwh_uti_out": max(0, -pu) * e,
                "kwh_sun": snap["p_sun"] * e, "kwh_gen": 0.0,
                "kwh_fhp_di": max(0, pf) * e, "kwh_fhp_chg": max(0, -pf) * e,
                "kwh_load": pl * e,
            }
            tier = self._tou_tier(mins / 60.0)
            for ci, ch in enumerate(CH):
                tot[ch] += contrib[ch]
                tiers[tier][ci] += contrib[ch]

        out: dict[str, Any] = {
            "opt": 0, "result": 0, "reason": 0, "sno": max(1, 10000 - age),
            "dayType": 0, "pointMax": 96, "pointId": 96,
            "rec_time": rec_time, "p_uti": p_uti, "p_gen": p_gen,
            "p_fhp": p_fhp, "p_load": p_load,
        }
        for ch in CH:
            out[ch] = round(tot[ch], 2)
        for t in catalog.TIERS:
            out[t] = [round(x, 2) for x in tiers[t]]
        return out

    # -- multi-aPower battery reads (synthesised, perturbed per unit) ---------
    # Each aPower "feeds off" the same site sim (SoC / battery power / ambient)
    # but is offset just enough to look like a distinct battery — so the Battery
    # tab's per-aPower overlay has real, differing lines to draw.
    def apower_serial(self, dev_id: int) -> str:
        """Stable per-unit aPower (FHP) serial embedding the unit index."""
        base = self.fhp_serial
        return f"{base[:-2]}{dev_id % 100:02d}"

    def device_check(self, units: int) -> dict[str, Any]:
        """1106 device list: devNum + a devMap row per aPower."""
        return {
            "opt": 0, "result": 0, "reason": 0, "devNum": units, "isOver": 1,
            "devMap": [{"id": i + 1, "devSN": self.apower_serial(i + 1), "checkResult": 1}
                       for i in range(units)],
        }

    def _unit_soc(self, dev_id: int, ts: float):
        snap = self.snapshot(ts)
        soc = max(5.0, min(98.0, snap["soc"] - (dev_id - 1) * 4.0))
        return soc, snap

    def battery_cells(self, dev_id: int, ts: float) -> dict[str, Any]:
        """1706 per-cell BMS telemetry for one aPower."""
        soc, snap = self._unit_soc(dev_id, ts)
        rng = random.Random(self.seed * 100 + dev_id)
        base_mv = 3200.0 + soc * 4.0                       # ~3.22–3.59 V across 5–98 %
        cells, temps = [], []
        for c in range(16):
            off = (rng.random() - 0.5) * 6.0               # ±3 mV fixed per-cell
            jit = math.sin(ts / 12.0 + c + dev_id) * 1.0   # ±1 mV slow ripple
            cells.append(round(base_mv + off + jit + (dev_id - 1) * 2.0, 1))
            toff = (rng.random() - 0.5) * 1.5
            temps.append(round(snap["t_amb"] + 1.0 + toff + (dev_id - 1) * 0.7
                               + math.sin(ts / 30.0 + c) * 0.3, 1))
        cur = round(snap["p_fhp"] / 50.0, 1)               # −charging / +discharging (UI convention)
        return {
            "opt": 0, "result": 0, "reason": 0, "id": dev_id,
            "batVolt": cells, "batTemp": temps,
            "batTotalVolt": round(sum(cells) / 1000.0, 1),
            "singleHighestVolt": max(cells), "singleLowestVolt": min(cells),
            "singleHighestTemp": max(temps), "singleLowestTemp": min(temps),
            "currGrp": cur, "batSoc": round(soc, 1),
            "batSoh": round(95.0 - (dev_id - 1) * 1.5, 1), "alarmLevel": 0,
        }

    def power_electronics(self, dev_id: int, ts: float) -> dict[str, Any]:
        """1704 per-device inverter & DC-bus detail (incl. the verified DCDCStatus)."""
        soc, snap = self._unit_soc(dev_id, ts)
        rs = snap["run_status"]
        dcdc = {0: 4, 1: 6, 2: 7}.get(rs, 4)               # Standby / Charging / Discharging
        packv = round((3200.0 + soc * 4.0) * 16.0 / 1000.0, 1)
        return {
            "opt": 0, "result": 0, "reason": 0, "id": dev_id,
            "batVol": packv, "gridVol1": 121.0, "gridVol2": 121.0,
            "inverterVolt1": 121.0, "inverterVolt2": 121.0,
            "positiveBusVolt": 200.0, "negativeBusVolt": 200.0, "middleBusVolt": 314.0,
            "gridFreq": round(60.0 + math.sin(ts / 60.0) * 0.02, 2),
            "loadCurr1": 1.0, "loadCurr2": 1.0, "inverterCurr1": 1.0, "inverterCurr2": 1.0,
            "buckboostCurr": round(snap["p_fhp"] / 100.0, 1),
            "runMode": 8, "inverterStatus": 8, "DCDCStatus": dcdc,
        }

    def device_states(self, dev_id: int, ts: float) -> dict[str, Any]:
        """1836 per-device state block."""
        _soc, snap = self._unit_soc(dev_id, ts)
        rs = snap["run_status"]
        bms = {0: 5, 1: 6, 2: 7}.get(rs, 5)                # Standby / Charging / Discharging
        mode = self.mode_for_hour(self.local_hour(ts))
        return {"opt": 0, "result": 0, "reason": 0, "id": dev_id,
                "ibgDspState": 4, "ibgMainState": MODE_IDS[mode],
                "peState": 8, "bmsState": bms}

    def device_firmware(self, dev_id: int) -> dict[str, Any]:
        """1834 per-device serials and firmware."""
        sn = self.apower_serial(dev_id)
        return {"opt": 0, "result": 0, "reason": 0, "id": dev_id,
                "fhp_sn": sn, "ibg_sn": self.serial, "ibg_ver": "V12R02B30D06_260304",
                "ibg_iot": "V12R00B06D04_260304", "ibg_local": "V12R00B07D04_260205",
                "pe_sn": sn + "P1", "pe_ver": "", "bms_sn": sn + "B1", "bms_ver": "V11R50B03D00"}
