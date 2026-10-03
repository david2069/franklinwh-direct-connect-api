"""
Battery Management rendering — per-cell telemetry as a readable terminal view.

Built on the per-device reads found by the 2026-09-11 sweep: ``1705 battery_cells``
(per-cell voltages and temperatures), ``1703 power_electronics`` (bus/grid rails),
``1835 device_states`` and ``1833 device_firmware``. All local, no cloud.

Every function here is **pure** — it takes payload dicts and returns lines — so the
layout is testable without hardware.

Deliberately omits rows the local channel cannot fill (thermal sensors, balancing,
MOS/fan/heater state, A-N/B-N line voltages). Printing them as blanks would imply
this is a degraded copy of the cloud view; they simply are not on this channel.
See docs/CLOUD_MAPPING.md §3e.
"""

from __future__ import annotations

import os
import re
import sys

#: Cells per row in the grid. 8 keeps a 16-cell pack to two rows inside 100 columns.
CELLS_PER_ROW = 8

_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$", re.I)
_UNIT_S = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str) -> float:
    """Parse ``30``/``30s``/``5m``/``1h`` into seconds. Raises ValueError."""
    m = _DURATION.match(str(text))
    if not m:
        raise ValueError(
            f"bad duration {text!r} — expected e.g. 90, 30s, 5m, 2h")
    value, unit = m.groups()
    seconds = float(value) * _UNIT_S[unit.lower()]
    if seconds <= 0:
        raise ValueError(f"duration must be positive, got {text!r}")
    return seconds


def use_colour(stream=None) -> bool:
    """Colour only for an interactive TTY, and never when NO_COLOR is set."""
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class _C:
    """ANSI helpers that collapse to identity when colour is off."""

    def __init__(self, on: bool):
        self.on = on

    def _w(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def dim(self, t):    return self._w("2", t)
    def bold(self, t):   return self._w("1", t)
    def red(self, t):    return self._w("31", t)
    def green(self, t):  return self._w("32", t)
    def yellow(self, t): return self._w("33", t)
    def cyan(self, t):   return self._w("36", t)


def _num(value, default=None):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def cell_stats(volts: list, temps: list) -> dict:
    """Extremes and their 1-based cell numbers, derived from the arrays.

    The cloud reports these as maxVolPos/minVolPos/maxTempPos/minTempPos; locally
    they are simply argmax/argmin, so no field is missing in practice.
    """
    out: dict = {}
    if volts:
        out["v_max"], out["v_min"] = max(volts), min(volts)
        out["v_max_cell"] = volts.index(out["v_max"]) + 1
        out["v_min_cell"] = volts.index(out["v_min"]) + 1
        out["spread"] = out["v_max"] - out["v_min"]
    if temps:
        out["t_max"], out["t_min"] = max(temps), min(temps)
        out["t_max_cell"] = temps.index(out["t_max"]) + 1
        out["t_min_cell"] = temps.index(out["t_min"]) + 1
    return out


def cell_grid(volts: list, temps: list, *, per_row: int = CELLS_PER_ROW,
              colour: bool = False) -> list[str]:
    """The per-cell grid: cell number, voltage, temperature, extremes marked."""
    c = _C(colour)
    st = cell_stats(volts, temps)
    lines: list[str] = []
    width = 10
    for base in range(0, len(volts), per_row):
        idx = range(base, min(base + per_row, len(volts)))
        lines.append("  " + "".join(c.dim(f"#{i + 1}".ljust(width)) for i in idx))
        cells = []
        for i in idx:
            mv = volts[i]
            mark = ("↓" if i + 1 == st.get("v_min_cell") else
                    "↑" if i + 1 == st.get("v_max_cell") else " ")
            txt = f"{mark}{mv / 1000:.3f}V".ljust(width)
            if mark == "↑":
                txt = c.green(txt)
            elif mark == "↓":
                txt = c.yellow(txt)
            cells.append(txt)
        lines.append("  " + "".join(cells))
        if temps:
            row = []
            for i in idx:
                if i >= len(temps):
                    break
                mark = "*" if i + 1 == st.get("t_max_cell") else " "
                txt = f"{mark}{temps[i]:.1f}°C".ljust(width)
                row.append(c.red(txt) if mark == "*" else c.dim(txt))
            lines.append("  " + "".join(row))
        lines.append("")
    return lines


def render(cells: dict, pe: dict | None = None, states: dict | None = None,
           firmware: dict | None = None, check: dict | None = None, *,
           colour: bool = False, dev_id: int = 1, when: str = "") -> list[str]:
    """Full Battery Management view. Sections with no data are omitted."""
    c = _C(colour)
    pe, states, firmware, check = pe or {}, states or {}, firmware or {}, check or {}
    volts = [v for v in (cells.get("batVolt") or []) if isinstance(v, (int, float))]
    temps = [t for t in (cells.get("batTemp") or []) if isinstance(t, (int, float))]
    st = cell_stats(volts, temps)
    L: list[str] = []
    bar = "=" * 62

    sn = firmware.get("fhp_sn") or ""
    L.append(bar)
    L.append(c.bold(f"  Battery Management — aPower {sn[-4:] if sn else f'id {dev_id}'}"))
    if when:
        L.append(c.dim(f"  {when}"))
    L.append(bar)

    def kv(label, value, note=""):
        L.append(f"{label + ':':>22} {value}" + (c.dim(f"   {note}") if note else ""))

    # ── identity ──
    L.append("")
    L.append(c.cyan("\U0001f50b Device"))
    if sn:
        kv("aPower SN", sn)
    if firmware.get("bms_ver"):
        kv("BMS firmware", firmware["bms_ver"])
    if _num(check.get("devNum")) is not None:
        kv("Units online", check["devNum"])

    # ── pack health ──
    L.append("")
    L.append(c.cyan("\U0001f49a Pack Health"))
    soc, soh = _num(cells.get("batSoc")), _num(cells.get("batSoh"))
    if soc is not None:
        kv("Charge (SoC)", f"{soc:.1f}%")
    if soh is not None:
        kv("Health (SoH)", f"{soh:.1f}%")
    if _num(cells.get("batTotalVolt")) is not None:
        kv("Total Voltage", f"{cells['batTotalVolt']:.1f} V")
    cur = _num(cells.get("currGrp"))
    if cur is not None:
        flow = "Discharging" if cur > 0 else ("Charging" if cur < 0 else "Idle")
        kv("Current", f"{cur:+.1f} A", f"({flow})")
    if _num(pe.get("gridFreq")) is not None:
        kv("Grid Frequency", f"{pe['gridFreq']:.2f} Hz")
    alarm = _num(cells.get("alarmLevel"))
    if alarm is not None:
        kv("Alarm Level", c.green("0 (none)") if alarm == 0 else c.red(f"{alarm}"))

    # ── cells ──
    if volts:
        L.append("")
        L.append(c.cyan(f"\U0001f52c Cell Telemetry ({len(volts)} series)"))
        kv("Highest", f"{st['v_max']} mV", f"(cell {st['v_max_cell']})")
        kv("Lowest", f"{st['v_min']} mV", f"(cell {st['v_min_cell']})")
        spread = st["spread"]
        txt = f"{spread} mV"
        kv("Spread", c.green(txt) if spread <= 20 else
                     c.yellow(txt) if spread <= 50 else c.red(txt))
        if temps:
            kv("Temp Range",
               f"{st['t_min']:.1f}°C → {st['t_max']:.1f}°C",
               f"(cells {st['t_min_cell']}–{st['t_max_cell']})")
        L.append("")
        L.extend(cell_grid(volts, temps, colour=colour))

    # ── bus topology ──
    rails = [
        ("Grid Feed (L1/L2)", pe.get("gridVol1"), pe.get("gridVol2"), "V"),
        ("Inverter (L1/L2)", pe.get("inverterVolt1"), pe.get("inverterVolt2"), "V"),
        ("DC Bus (+/−)", pe.get("positiveBusVolt"), pe.get("negativeBusVolt"), "V"),
        ("Load Current (1/2)", pe.get("loadCurr1"), pe.get("loadCurr2"), "A"),
        ("Inv Current (1/2)", pe.get("inverterCurr1"), pe.get("inverterCurr2"), "A"),
    ]
    shown = [r for r in rails if _num(r[1]) is not None]
    if shown or _num(pe.get("middleBusVolt")) is not None:
        L.append(c.cyan("\U0001f50c Grid & Bus"))
        for label, a, b, unit in shown:
            kv(label, f"{a:.1f} {unit}  |  {b:.1f} {unit}")
        if _num(pe.get("batVol")) is not None:
            kv("PE Battery / Mid Bus",
               f"{pe['batVol']:.1f} V  |  {pe.get('middleBusVolt', 0):.1f} V")
        if _num(pe.get("buckboostCurr")) is not None:
            kv("BuckBoost Current", f"{pe['buckboostCurr']:.1f} A")

    # ── states ──
    rows = [("BMS Status", states.get("bmsState")),
            ("PE Status", states.get("peState")),
            ("Inverter Status", pe.get("inverterStatus")),
            ("DCDC Status", pe.get("DCDCStatus")),
            ("Run Mode", pe.get("runMode"))]
    rows = [(k, v) for k, v in rows if _num(v) is not None]
    if rows:
        L.append("")
        L.append(c.cyan("\U0001f527 Hardware States"))
        for k, v in rows:
            kv(k, v)

    L.append("")
    L.append(c.dim("  Local only (cmdTypes 1705/1703/1835/1833). Thermal sensors, cell"))
    L.append(c.dim("  balancing and MOS/fan/heater state are not on this channel."))
    return L
