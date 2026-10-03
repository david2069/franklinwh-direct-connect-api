"""
High-level client for the FranklinWH aGate local broker protocol.

Wraps :class:`~franklinwh_local.transport.LocalTransport` with friendly,
named methods that return the decoded ``dataArea`` dict of each response.
"""

from __future__ import annotations

from typing import Any

from .catalog import CATALOG, Cmd
from .transport import DEFAULT_RETRIES, DEFAULT_TIMEOUT, LocalTransport

# Short mode aliases shared with the sibling CLIs (franklinwh-modbus / -cloud).
# Each alias key maps to a canonical needle (used for substring fallback) AND to a
# scheduling_type integer (= cloud workMode: TOU=1 / Self=2 / Backup=3). The
# scheduling_type is the preferred resolution path because it is a stable integer
# present on every mode_list entry, independent of site-specific tariff names
# (e.g. 'Ausgrid EA11 TOU' vs 'ActewAGL Residential TOU').
_MODE_ALIASES = {
    "tou": "tou", "time_of_use": "tou", "timeofuse": "tou",
    "self": "self", "self_consumption": "self", "selfconsumption": "self", "sc": "self",
    "backup": "backup", "emergency": "backup", "emergency_backup": "backup",
}

# Needle → scheduling_type (cloud workMode). Mirrors catalog.OPERATING_MODES["cloud"].
# scheduling_type is present in every 1726 list entry and is site-agnostic.
_NEEDLE_SCHEDULING_TYPE: dict[str, int] = {
    "tou": 1,
    "self": 2,
    "backup": 3,
}


def _validate_hhmm(value: str) -> str:
    """Validate a firmware ``HH:MM`` time-of-day string."""
    try:
        hh, mm = str(value).strip().split(":")
        h, m = int(hh), int(mm)
    except (ValueError, AttributeError):
        raise ValueError(f"time must be HH:MM, got {value!r}") from None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"time out of range: {value!r}")
    return f"{h:02d}:{m:02d}"


class LocalClient:
    """
    Connect to an aGate broker and issue named commands.

    >>> with LocalClient("10.100.1.1") as c:
    ...     c.login()
    ...     print(c.power_flow()["soc"])
    """

    def __init__(self, host: str, port: int = 9000, *, timeout: float = DEFAULT_TIMEOUT,
                 retries: int = DEFAULT_RETRIES, equip_no: str | None = None):
        self.transport = LocalTransport(host, port, timeout=timeout, retries=retries)
        self._equip = equip_no

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self) -> "LocalClient":
        self.transport.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.transport.close()

    @property
    def equip_no(self) -> str:
        eq = self._equip or self.transport.equip_no
        if not eq:
            raise RuntimeError("equipNo unknown — call login() first or pass equip_no=")
        return eq

    def login(self) -> dict[str, Any]:
        """Handshake; returns the firmware/version manifest and caches equipNo."""
        return dict(self.transport.login().data_area)

    # The version/serial fields carried in the login (1102) manifest.
    FIRMWARE_FIELDS = (
        "protocolVer", "IBG_VER", "APP_VER", "AWS_VER", "SL_VER", "FPGA_VER",
        "DCDC_VER", "INV_VER", "BMS_VER", "BL_VER", "TH_VER", "SyHdVersion", "METER_VER",
        "IBG_SN", "FHP_SN", "BMS_SN", "PE_SN",
    )

    def firmware(self) -> dict[str, Any]:
        """Firmware/version block from the login manifest (a read; no separate cmdType).

        Returns the version and serial fields the aGate reports at login. Behaviours can
        be firmware-gated, so record this alongside any hardware-verification result.
        """
        manifest = self.login()
        return {k: manifest[k] for k in self.FIRMWARE_FIELDS if k in manifest}

    # -- generic -------------------------------------------------------------
    def call(self, cmd: int, data_area: dict | None = None) -> dict[str, Any]:
        """Issue any request cmdType and return the response dataArea."""
        return dict(self.transport.request(cmd, self.equip_no, data_area).data_area)

    # -- named reads ---------------------------------------------------------
    def power_flow(self) -> dict[str, Any]:
        """Live power flow / mode / SoC (cmd 1301 -> 1302)."""
        return self.call(Cmd.POWER_FLOW)

    def smart_circuits(self) -> dict[str, Any]:
        """Smart-circuit configuration (cmd 1409 -> 1410)."""
        return self.call(Cmd.SMART_CIRCUITS)

    def network_interfaces(self) -> dict[str, Any]:
        """WiFi/Ethernet interface details (cmd 1117 -> 1118)."""
        return self.call(Cmd.NETWORK_INTERFACES)

    def network_switches(self) -> dict[str, Any]:
        """Interface on/off switches (cmd 1119 -> 1120)."""
        return self.call(Cmd.NETWORK_SWITCHES)

    def wifi_config(self) -> dict[str, Any]:
        """WiFi/AP configuration (cmd 1111 -> 1112). Contains credentials."""
        return self.call(Cmd.WIFI_CONFIG)

    def connectivity(self) -> dict[str, Any]:
        """Router/internet/AWS connectivity (cmd 1113 -> 1114)."""
        return self.call(Cmd.CONNECTIVITY)

    def time_location(self) -> dict[str, Any]:
        """Time, timezone and site location (cmd 1201 -> 1202)."""
        return self.call(Cmd.TIME_LOCATION)

    def install_profile(self) -> dict[str, Any]:
        """Electrical / install profile (cmd 1701 -> 1702)."""
        return self.call(Cmd.INSTALL_PROFILE)

    def offgrid(self) -> dict[str, Any]:
        """Off-grid settings (cmd 1723 -> 1724)."""
        return self.call(Cmd.OFFGRID)

    def solar_pv(self) -> dict[str, Any]:
        """Solar / PV configuration (cmd 1903 -> 1904)."""
        return self.call(Cmd.SOLAR_PV)

    def mode_list(self) -> dict[str, Any]:
        """Operating-mode list (cmd 1725 -> 1726)."""
        return self.transport.request(Cmd.MODE_LIST, self.equip_no, {"opt": 1}).data_area

    def wifi_scan(self) -> dict[str, Any]:
        """Scan for nearby WiFi access points (cmd 1109 -> 1110)."""
        return self.call(Cmd.WIFI_SCAN)

    def device_info(self) -> dict[str, Any]:
        """Installer/user device config: usrName, distributor, installerId (cmd 1115 -> 1116).
        Cloud equivalent: get_device_info()"""
        return self.call(Cmd.DEVICE_INFO)

    def cloud_config(self) -> dict[str, Any]:
        """Cloud server config: AWS IoT endpoint, region (cmd 1121 -> 1122)."""
        return self.call(Cmd.CLOUD_CONFIG)

    def grid_policy(self) -> dict[str, Any]:
        """Grid compliance policy overview: policy, gridPowerUP/Down (cmd 1203 -> 1204).
        Cloud equivalent: get_grid_profile_info(requestType=1)"""
        return self.call(Cmd.GRID_POLICY)

    def grid_profile(self) -> dict[str, Any]:
        """Full grid-compliance profile — fans out across all local compliance sections.

        Calls grid_policy() (1203) for the overview, the 10 summary sections (1211..1229),
        and the 14 detailed sections (1251..1277). Values reflect whatever grid profile
        the site has loaded. Sections that time out are silently omitted.
        Cloud equivalent: get_grid_profile_info(requestType=2).
        """
        result: dict[str, Any] = {}
        result["grid_policy"] = self.call(Cmd.GRID_POLICY)
        compliance: dict[str, Any] = {}
        for cmd in (
            list(range(1211, 1230, 2))   # summary sections: OV/OF trip, PF, QV, PV, Pf, reconnect, DC, ride-through, batt-access
            + list(range(1251, 1278, 2))  # detailed compliance sections
        ):
            info = CATALOG.get(cmd)
            key = info.name if info else f"cmd_{cmd}"
            try:
                compliance[key] = self.call(cmd)
            except TimeoutError:
                pass
        result["compliance_sections"] = compliance
        return result

    def mode_config(self) -> dict[str, Any]:
        """Active mode config: runingMode, modeChoose, name (cmd 1403 -> 1404).
        Cloud equivalent: get_mode()"""
        return self.call(Cmd.MODE_CONFIG)

    def mode_soc(self) -> dict[str, Any]:
        """Reserved SoC % per mode: selfMinSoc, selfMaxSoc, touMinSoc, touMaxSoc (cmd 1405 -> 1406).
        Cloud equivalent: get_all_mode_soc()"""
        return self.call(Cmd.MODE_SOC)

    def tou_schedule(self) -> dict[str, Any]:
        """TOU schedule: touStrategy, workday/weekend flags (cmd 1407 -> 1408).
        Cloud equivalent: get_gateway_tou_list()"""
        return self.call(Cmd.TOU_SCHEDULE)

    def der_comms(self) -> dict[str, Any]:
        """DER communication config (cmd 1205 -> 1206).

        ``sunsMdEn`` = SunSpec Modbus interface toggle (Modbus TCP on ``ip``/``port``,
        default 502). ``enable``/``status2030_5``/``uri``/``lfdi``/``sfdi``/``pin`` =
        IEEE 2030.5 (SEP2) client config.
        """
        return self.call(Cmd.DER_COMMS)

    def set_der_comms(self, *, sunspec_modbus: bool | None = None,
                      sep2: bool | None = None) -> dict[str, Any]:
        """Write DER comms config (cmd 1205 opt:1) via full-block read-modify-write.

        ``sunspec_modbus`` toggles ``sunsMdEn``; ``sep2`` toggles the 2030.5 ``enable``
        field. ``None`` leaves a field unchanged. Reads the full block and writes it all
        back (the aGate rejects partial frames). Returns the reply plus ``prior_der_comms``
        (for revert).

        **This does NOT self-verify.** The write is asymmetric and cloud-independent, so
        correctness must be confirmed at the *interface* level by the caller — the actual
        `:502` service for Modbus, or ``status2030_5``/``lfdi`` for 2030.5 — NOT by reading
        the config field back (a `result:0` reply and a changed flag are not proof).
        """
        from .transport import TransportError
        prior = self.der_comms()
        prior_block = {k: v for k, v in prior.items()
                       if k not in ("opt", "result", "reason")}
        block = dict(prior_block)
        if sunspec_modbus is not None:
            block["sunsMdEn"] = 1 if sunspec_modbus else 0
        if sep2 is not None:
            block["enable"] = 1 if sep2 else 0
        reply = self.call(Cmd.DER_COMMS, {"opt": 1, **block})
        if reply.get("result") not in (0, None):
            raise TransportError(
                f"aGate rejected der_comms write: result={reply.get('result')} "
                f"reason={reply.get('reason')} (sent {block})"
            )
        return {"prior_der_comms": prior_block, **reply}

    def smart_circuit_meter(self) -> dict[str, Any]:
        """Smart-circuit live metering: V/I/P/energy per circuit (cmd 1411 -> 1412)."""
        return self.call(Cmd.SMART_CIRCUIT_METER)

    def ibg_run_status(self) -> dict[str, Any]:
        """IBG run status: ibgRunStatus, name, energyMode (cmd 1707 -> 1708).
        Cloud equivalent: get_runtime_data()"""
        return self.call(Cmd.IBG_RUN_STATUS)

    def relay_status(self) -> dict[str, Any]:
        """Relay adhesion/open status (cmd 1709 -> 1710).
        Cloud equivalent: get_power_info()"""
        return self.call(Cmd.RELAY_STATUS)

    def battery_inhibit(self) -> dict[str, Any]:
        """Battery charge-inhibit SoC thresholds: inhSocNormal, inhSocCold (cmd 1801 -> 1802)."""
        return self.call(Cmd.BATTERY_INHIBIT)

    def ibg_state(self) -> dict[str, Any]:
        """IBG DSP/main state, firmware, uptime (cmd 1827 -> 1828)."""
        return self.call(Cmd.IBG_STATE)

    def event_block(self) -> dict[str, Any]:
        """Indexed event/data block (cmd 1829 -> 1830)."""
        return self.call(Cmd.EVENT_BLOCK)

    def battery_modules(self) -> dict[str, Any]:
        """Battery module list: devNum, devMap[{id, devSN}] (cmd 1831 -> 1832)."""
        return self.call(Cmd.BATTERY_MODULES)

    # -- per-device reads (require an `id` selector) -------------------------
    # `id` comes from device_check (1105) / battery_modules (1831) devMap[].id.
    # Without it the aGate replies result=1 reason=-1 with empty arrays — which
    # reads as "no data here" but actually means "you didn't say which device".

    def device_check(self) -> dict[str, Any]:
        """Device list + check state (cmd 1105 -> 1106): devMap[{id, devSN, checkResult}]."""
        return self.call(Cmd.DEVICE_CHECK)

    def agate_serial(self) -> dict[str, Any]:
        """aGate serial (cmd 1123 -> 1124)."""
        return self.call(Cmd.AGATE_SERIAL)

    def device_ids(self) -> list[int]:
        """Selector ids for the per-device reads, from device_check/battery_modules."""
        ids: list[int] = []
        for source in (self.device_check, self.battery_modules):
            try:
                entries = source().get("devMap") or []
            except (TransportError, OSError, TimeoutError, ValueError):
                continue
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("id"), int):
                    if entry["id"] not in ids:
                        ids.append(entry["id"])
            if ids:
                break
        return ids or [1]

    def energy_history(self, date: str | None = None) -> dict[str, Any]:
        """One day of quarter-hour energy history (cmd 1303 -> 1304).

        ``date`` must be ``YYYY-MM-DD`` (defaults to today). The data lives **on
        the aGate**, not the cloud — a rolling window of roughly 105 days. Older
        dates come back with ``sno: 0`` and empty arrays rather than an error.

        The reply carries 96 quarter-hour points, seven ``kwh_*`` daily totals,
        and per-tariff splits: for each channel in ``catalog.ENERGY_CHANNELS``,
        ``sharp + peak + flat + valley`` sums to that channel's total.
        """
        if date is None:
            import datetime as _dt
            date = _dt.date.today().isoformat()
        return self.call(Cmd.ENERGY_HISTORY, {"opt": 0, "date": date})

    def tou_blocks(self, day_type: str = "workday") -> list:
        """TOU schedule (1407) decoded into ordered tariff blocks."""
        from . import energy as _energy
        return _energy.decode_tou(self.tou_schedule(), day_type)

    def energy_rollup(self, period: str = "month", date: "str | None" = None,
                      **kwargs):
        """Aggregate daily history (1303) into a week/month/year/total rollup.

        The aGate serves one day per request and has no rollup call of its own,
        so this fetches the days in the period and sums them. Retention is a
        rolling ~105 days, so longer periods come back partial — the result
        carries its own coverage rather than presenting a short sum as complete.
        """
        import datetime as _dt

        from . import energy as _energy

        target = (_dt.date.fromisoformat(date) if date else _dt.date.today())
        return _energy.rollup(lambda d: self.energy_history(d), period, target,
                              **kwargs)

    def battery_cells(self, dev_id: int = 1) -> dict[str, Any]:
        """Per-cell BMS telemetry for one battery (cmd 1705 -> 1706).

        The local equivalent of the cloud's ``get_bms_info()``: ``batVolt`` is a
        per-cell voltage array (mV) and ``batTemp`` a per-cell temperature array
        (degC), alongside pack totals, SoC/SoH and ``alarmLevel``.
        """
        return self.call(Cmd.BATTERY_CELLS, {"opt": 0, "id": dev_id})

    def power_electronics(self, dev_id: int = 1) -> dict[str, Any]:
        """Per-device inverter / DC-bus electrical detail (cmd 1703 -> 1704)."""
        return self.call(Cmd.POWER_ELECTRONICS, {"opt": 0, "id": dev_id})

    def device_firmware(self, dev_id: int = 1) -> dict[str, Any]:
        """Per-device serials + firmware versions (cmd 1833 -> 1834)."""
        return self.call(Cmd.DEVICE_FIRMWARE, {"opt": 0, "id": dev_id})

    def device_states(self, dev_id: int = 1) -> dict[str, Any]:
        """Per-device DSP/main/PE/BMS state block (cmd 1835 -> 1836)."""
        return self.call(Cmd.DEVICE_STATES, {"opt": 0, "id": dev_id})

    def generator(self) -> dict[str, Any]:
        """Generator + scheduled grid-charge configuration (cmd 1901 -> 1902)."""
        return self.call(Cmd.GENERATOR)

    # -- writes (control) ----------------------------------------------------
    # Verified on aGate X over LAN TCP/9000 (2026-06-19). See catalog.WRITES.

    def _resolve_mode_id(self, mode: int | str) -> int:
        """Accept a programme id (int / digit-string), a full mode name, or a
        short alias and return the id.

        Resolution order:

        1. Raw integer / digit string → used directly as the programme id.
        2. Exact mode name match (case-insensitive).
        3. ``scheduling_type`` lookup — the preferred alias path. ``scheduling_type``
           equals the cloud ``workMode`` (TOU=1 / Self=2 / Backup=3) and is a stable
           integer on every 1726 entry, independent of site-specific tariff names like
           ``'Ausgrid EA11 TOU'``. This is why ``tou`` / ``self`` / ``backup`` aliases
           work reliably across all sites.
        4. Substring fallback (legacy) — for callers who pass a raw tariff name such as
           ``'Ausgrid EA11 TOU'`` that contains the alias as a substring.

        Aliases (shared with franklinwh-modbus / -cloud)::

            tou / time_of_use / timeofuse  →  scheduling_type 1
            self / self_consumption / sc   →  scheduling_type 2
            backup / emergency / emergency_backup  →  scheduling_type 3
        """
        s = str(mode).strip()
        if s.isdigit():
            return int(s)
        key = s.lower().replace("-", "_").replace(" ", "_")
        needle = _MODE_ALIASES.get(key, s).lower()
        modes = self.mode_list().get("list", [])

        # 1. Exact name match.
        for m in modes:
            if str(m.get("name", "")).lower() == s.lower():
                return int(m["id"])

        # 2. scheduling_type match — site-agnostic, preferred over substring.
        stype = _NEEDLE_SCHEDULING_TYPE.get(needle)
        if stype is not None:
            for m in modes:
                if m.get("scheduling_type") == stype:
                    return int(m["id"])

        # 3. Substring fallback — handles raw tariff names (e.g. 'Ausgrid EA11 TOU').
        for m in modes:
            if needle in str(m.get("name", "")).lower():
                return int(m["id"])

        raise ValueError(
            f"unknown mode {mode!r}; "
            f"available: {[m.get('name') for m in modes]}"
        )

    def set_mode(self, mode: int | str) -> dict[str, Any]:
        """Set the active operating mode (1727 opt:3).

        ``mode`` accepts, in order of preference:

        - A canonical alias: ``tou``, ``self`` / ``sc``, ``backup`` / ``emergency``.
          Resolved via ``scheduling_type`` — works on any site regardless of the
          local tariff name.
        - An exact mode name: ``"Self-Consumption"``, ``"Ausgrid EA11 TOU"``, etc.
        - A site-specific programme id (int or digit string): ``85232``, ``29287``.
        """
        return self.call(Cmd.MODE_PAGE, {"opt": 3, "current_id": self._resolve_mode_id(mode)})

    def set_offgrid(self, on: bool, soc: int = 5) -> dict[str, Any]:
        """Go off-grid (``on=True``) or reconnect (``on=False``); ``soc`` = floor
        SoC % to hold while islanded (1723 opt:1)."""
        return self.call(Cmd.OFFGRID,
                         {"opt": 1, "offgridSet": 1 if on else 0, "offgridSoc": int(soc)})

    # -- generator (1901) ----------------------------------------------------
    # HARDWARE-VERIFIED 2026-09-14: operating windows, the exercise schedule and the
    # generator SoC thresholds all apply and read back. This is in deliberate
    # contrast to the smart-circuit SCHEDULE (see set_circuit_schedule), which the
    # same gateway accepts and discards — do not generalise from one to the other.
    GENERATOR_WRITABLE = (
        "genEn", "manuSw", "genRatedPower", "genModel", "genOptiPPoint",
        "startDelTime", "genStartElec", "genCloseElec", "gridVoltCheck",
        "oilmanoEn", "manoFre", "manoDate", "manoStartTime", "manoTime", "manoManExit",
        "charge1En", "charge1StartTime", "charge1EndTime",
        "charge2En", "charge2StartTime", "charge2EndTime",
        "charge3En", "charge3StartTime", "charge3EndTime",
    )

    def set_generator(self, **changes: Any) -> dict[str, Any]:
        """Change generator settings (1901 opt:1) by full-block read-modify-write.

        The aGate rejects partial frames on some commands, so the whole block is read,
        patched and written back — which also preserves the operating windows when you
        are only touching a threshold, and vice versa.

        Self-verifying: re-reads 1901 and reports ``ok`` only when every requested field
        reads back as asked. ``result:0`` alone is NOT treated as success — on this
        firmware some commands accept a frame and silently ignore it.

        Returns ``{ok, result, requested, before, after, confirmed, mismatched}``.
        """
        unknown = set(changes) - set(self.GENERATOR_WRITABLE)
        if unknown:
            raise ValueError(f"not writable on 1901: {sorted(unknown)}")

        prior = self.generator()
        block = {k: v for k, v in prior.items()
                 if k not in ("opt", "result", "reason")}
        before = {k: prior.get(k) for k in changes}
        block.update(changes)
        block["opt"] = 1
        reply = self.call(Cmd.GENERATOR, block)

        post = self.generator()
        after = {k: post.get(k) for k in changes}
        mismatched = {k: {"requested": v, "actual": after.get(k)}
                      for k, v in changes.items() if after.get(k) != v}
        return {
            "ok": bool(reply.get("result") == 0 and not mismatched),
            "result": reply.get("result"),
            "requested": dict(changes),
            "before": before,
            "after": after,
            "confirmed": not mismatched,
            "mismatched": mismatched,
        }

    def set_generator_window(self, window: int, enabled: bool,
                             start: str | None = None,
                             end: str | None = None) -> dict[str, Any]:
        """Set one of the generator's three operating windows (``HH:MM``).

        FranklinWH documents up to 3 non-overlapping periods with at least a 1-minute
        gap; overlap is NOT enforced here because the caller may be editing them one at
        a time, so validate across windows before calling if that matters.
        """
        if window not in (1, 2, 3):
            raise ValueError(f"window must be 1, 2 or 3 (got {window!r})")
        changes: dict[str, Any] = {f"charge{window}En": 1 if enabled else 0}
        if start is not None:
            changes[f"charge{window}StartTime"] = _validate_hhmm(start)
        if end is not None:
            changes[f"charge{window}EndTime"] = _validate_hhmm(end)
        return self.set_generator(**changes)

    def set_generator_exercise(self, enabled: bool | None = None,
                               every_days: int | None = None,
                               day: int | None = None,
                               start: str | None = None,
                               minutes: int | None = None) -> dict[str, Any]:
        """Set the generator maintenance/exercise run (``oilmanoEn``/``mano*``)."""
        changes: dict[str, Any] = {}
        if enabled is not None:
            changes["oilmanoEn"] = 1 if enabled else 0
        if every_days is not None:
            changes["manoFre"] = int(every_days)
        if day is not None:
            changes["manoDate"] = int(day)
        if start is not None:
            changes["manoStartTime"] = _validate_hhmm(start)
        if minutes is not None:
            changes["manoTime"] = int(minutes)
        if not changes:
            raise ValueError("nothing to change")
        return self.set_generator(**changes)

    def set_generator_soc(self, start_below: int, stop_above: int) -> dict[str, Any]:
        """Generator auto start/stop SoC thresholds (``genStartElec``/``genCloseElec``)."""
        start_below, stop_above = int(start_below), int(stop_above)
        if not 0 <= start_below <= 100 or not 0 <= stop_above <= 100:
            raise ValueError("SoC thresholds must be 0..100")
        if stop_above <= start_below:
            raise ValueError(
                f"stop_above ({stop_above}) must exceed start_below ({start_below})")
        return self.set_generator(genStartElec=start_below, genCloseElec=stop_above)

    def set_circuit_schedule(self, circuit: int, slots: list[str],
                             enabled: list[int]) -> dict[str, Any]:
        """Attempt to write a smart-circuit schedule (1409 opt:1). **Usually a no-op.**

        HARDWARE-TESTED 2026-09-14 on a live aGate (FW V12R02B30D06): this does NOT
        work. Five payload shapes were tried on circuit 2 — full block; with the
        ``SwXMsgType`` target selector; with ``SwXAtuoEn=1``; with ``SwXFreq=1``; and a
        partial frame carrying only the schedule fields. All returned ``result:0`` and
        changed nothing. Writing the schedule through 1401 (the command actually *named*
        ``smart_circuit_schedule``) is refused outright with ``result:1 reason:-2``.

        The control rules out the transport: an on/off write via :meth:`set_smart_circuit`
        on the same command and circuit applied and read back correctly moments later.
        So the schedule fields specifically are ignored — the signature of a cloud-owned
        setting, as with 1405 ``mode_soc``. Note this is NOT true of the generator
        schedule: 1901 windows write fine (:meth:`set_generator_window`).

        Kept because it is harmless and self-verifying, and may behave differently on
        other firmware. ``discarded`` is True for the accepted-but-ignored case so
        ``result:0`` can never be mistaken for success.
        """
        if circuit not in (1, 2, 3):
            raise ValueError(f"circuit must be 1, 2 or 3 (got {circuit!r})")
        if len(slots) != 4 or len(enabled) != 4:
            raise ValueError("slots and enabled must each have 4 entries")

        prior = self.smart_circuits()
        block = {k: v for k, v in prior.items()
                 if k not in ("opt", "result", "reason")}
        before = {"time": prior.get(f"Sw{circuit}Time"),
                  "enabled": prior.get(f"Sw{circuit}TimeEn")}

        for i in (1, 2, 3):
            if f"Sw{i}MsgType" in block:
                block[f"Sw{i}MsgType"] = 0
        block[f"Sw{circuit}MsgType"] = 1
        block[f"Sw{circuit}Time"] = list(slots)
        block[f"Sw{circuit}TimeEn"] = list(enabled)
        block[f"Sw{circuit}TimeSet"] = [1, 0, 1, 0]
        block["opt"] = 1
        reply = self.call(Cmd.SMART_CIRCUITS, block)

        post = self.smart_circuits()
        after = {"time": post.get(f"Sw{circuit}Time"),
                 "enabled": post.get(f"Sw{circuit}TimeEn")}
        confirmed = after["time"] == list(slots) and after["enabled"] == list(enabled)
        accepted = reply.get("result") == 0
        return {
            "ok": bool(accepted and confirmed),
            "result": reply.get("result"),
            "circuit": circuit,
            "before": before,
            "after": after,
            "confirmed": confirmed,
            "discarded": bool(accepted and after == before and not confirmed),
            "note": ("schedule writes are silently discarded on FW V12R02B30D06; "
                     "read the schedule locally, change it in the app"),
        }

    def set_smart_circuit(self, circuit: int, on: bool) -> dict[str, Any]:
        """Turn a smart circuit on/off (cmd 1409 opt:1) via full-block read-modify-write.

        Mirrors the cloud ``set_smart_circuit_state`` recipe, translated to the local
        1409 block: read the current smart-circuit config, set every ``Sw{i}MsgType`` to
        0 then flag only ``Sw{circuit}MsgType=1`` (target this circuit), set
        ``Sw{circuit}Mode = 1|0`` and ``Sw{circuit}ProLoad = Mode ^ 1``, and write the
        whole block back (the aGate rejects partial frames).

        Self-verifying: re-reads 1409 and only reports ``ok`` when the read-back
        ``Sw{circuit}Mode`` confirms the request. A ``result:0`` reply is NOT taken as
        proof — if the read-back does not match, ``ok`` is False and ``note`` flags that a
        delayed apply is possible. Raises on transport error.

        Returns ``{ok, result, circuit, requested, before, after, confirmed[, note]}``.
        """
        if circuit not in (1, 2, 3):
            raise ValueError(f"circuit must be 1, 2 or 3 (got {circuit!r})")
        requested = 1 if on else 0

        prior = self.smart_circuits()
        block = {k: v for k, v in prior.items()
                 if k not in ("opt", "result", "reason")}
        before = block.get(f"Sw{circuit}Mode")

        for i in (1, 2, 3):
            if f"Sw{i}MsgType" in block:
                block[f"Sw{i}MsgType"] = 0
        block[f"Sw{circuit}MsgType"] = 1
        block[f"Sw{circuit}Mode"] = requested
        block[f"Sw{circuit}ProLoad"] = requested ^ 1

        block["opt"] = 1
        reply = self.call(Cmd.SMART_CIRCUITS, block)

        after = self.smart_circuits().get(f"Sw{circuit}Mode")
        confirmed = after == requested
        out: dict[str, Any] = {
            "ok": bool(reply.get("result") == 0 and confirmed),
            "result": reply.get("result"),
            "circuit": circuit,
            "requested": requested,
            "before": before,
            "after": after,
            "confirmed": confirmed,
        }
        if reply.get("result") == 0 and not confirmed:
            out["note"] = ("device acked (result:0) but read-back Sw%dMode=%r != "
                           "requested %d — NOT confirmed; a delayed apply is possible, "
                           "re-read before trusting." % (circuit, after, requested))
        return out

    def reboot(self) -> dict[str, Any]:
        """Reboot the aGate (cmd 1721 opt:1, ``reboot`` in the full block).

        DESTRUCTIVE. Reads the full device-control block first and writes it back with
        ``reboot=1`` (the aGate rejects partial frames with ``result:1``). The gateway
        drops the connection while it restarts, so a missing reply / dropped socket here
        is *expected* and returns ``{"dropped": True}`` rather than raising. On boot the
        aGate reloads saved config (e.g. re-binds Modbus :502 if ``sunsMdEn=1`` —
        verified live 2026-07-25).
        """
        from .transport import TransportError
        try:
            prior = self.call(Cmd.DEVICE_CONTROL)          # {reboot, reset, update}
            block = {k: v for k, v in prior.items()
                     if k not in ("opt", "result", "reason")}
            block["reboot"] = 1
            reply = self.call(Cmd.DEVICE_CONTROL, {"opt": 1, **block})
            return {"dropped": False, **reply}
        except (TransportError, TimeoutError, OSError) as e:
            return {"dropped": True, "detail": str(e)}
