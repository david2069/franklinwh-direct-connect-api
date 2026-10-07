"""
Command catalog for the FranklinWH aGate local broker protocol.

These ``cmdType`` codes belong to the device<->broker channel observed on
TCP/9000 (see docs/PROTOCOL.md). They are a DIFFERENT numbering scheme from the
cloud REST relay codes (203/211/311/...) used by the ``franklinwh-cloud``
library. Convention: odd codes are requests, the reply is the next even code.

The catalog is reverse-engineered from packet captures and is intentionally
easy to extend — add a row to ``CATALOG`` as you observe new codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import IntEnum


class Cmd(IntEnum):
    """Known request ``cmdType`` codes (the reply is ``value + 1``)."""

    LOGIN = 1101                 # -> 1102 firmware/version manifest
    WIFI_SCAN = 1109             # -> 1110
    WIFI_CONFIG = 1111           # -> 1112 SSID/password/AP
    CONNECTIVITY = 1113          # -> 1114 router/net/aws status
    DEVICE_INFO = 1115           # -> 1116 installer/user config [cloud: get_device_info()]
    NETWORK_INTERFACES = 1117    # -> 1118 wifi/eth DHCP/MAC/IP/DNS
    NETWORK_SWITCHES = 1119      # -> 1120 eth/wifi/4G on-off
    CLOUD_CONFIG = 1121          # -> 1122 AWS IoT server address + cloud config
    TIME_LOCATION = 1201         # -> 1202 time/timezone/lat/lon/postcode
    GRID_POLICY = 1203           # -> 1204 grid compliance policy: policy, gridPowerUP/Down
    DER_COMMS = 1205             # -> 1206 DER comms: sunsMdEn (SunSpec Modbus) + IEEE 2030.5/SEP2
    AS_OV_TRIP = 1211            # -> 1212 grid over-voltage trip: HV1/HV2/HV_T1/HV_T2
    AS_OF_TRIP = 1213            # -> 1214 grid over-frequency trip: HF1/HF2/HF_T1/HF_T2
    AS_POWER_FACTOR = 1215       # -> 1216 grid fixed power factor: powerFactor
    AS_QV_MODE = 1217            # -> 1218 grid Q(V) curve: QV_MODE_V*/Q* points
    AS_PV_MODE = 1219            # -> 1220 grid P(V) curve: PV_MODE_V*/P* points
    AS_PF_MODE = 1221            # -> 1222 grid P(f) droop: PF_MODE_F*/P* points
    AS_RECONNECT = 1223          # -> 1224 grid reconnect ramp rates
    AS_DC_INJECT = 1225          # -> 1226 grid DC injection limit
    AS_RIDE_THROUGH = 1227       # -> 1228 grid volt/freq ride-through flags
    AS_BATT_ACCESS = 1229        # -> 1230 battery grid-access mode
    POWER_FLOW = 1301            # -> 1302 live power flow / mode / soc
    MODE_CONFIG = 1403           # -> 1404 mode config: runingMode, modeChoose, name [cloud: get_mode()]
    MODE_SOC = 1405              # -> 1406 reserved SoC per mode: selfMinSoc/Max, touMinSoc/Max [cloud: get_all_mode_soc()]
    TOU_SCHEDULE = 1407          # -> 1408 TOU schedule: touStrategy, workday/weekend flags [cloud: get_gateway_tou_list()]
    SMART_CIRCUITS = 1409        # -> 1410 smart-circuit config (set with opt=1)
    SMART_CIRCUIT_METER = 1411   # -> 1412 smart-circuit live V/I/P/energy
    DEVICE_SCAN = 1103           # -> 1104 device scan (request must carry devNum)
    DEVICE_CHECK = 1105          # -> 1106 device list + check result
    AGATE_SERIAL = 1123          # -> 1124 aGate serial
    ENERGY_HISTORY = 1303        # -> 1304 daily energy history (needs date "YYYY-MM-DD")
    POWER_ELECTRONICS = 1703     # -> 1704 per-device inverter/DC-bus detail (needs id)
    BATTERY_CELLS = 1705         # -> 1706 per-cell BMS telemetry (needs id)
    DEVICE_FIRMWARE = 1833       # -> 1834 per-device serials/firmware (needs id)
    DEVICE_STATES = 1835         # -> 1836 per-device DSP/PE/BMS states (needs id)
    FIRMWARE_DELIVER = 1501      # -> 1502 OTA file delivery status (read; write pushes firmware)
    FIRMWARE_UPGRADE = 1503      # -> 1504 OTA upgrade status (read; write triggers an upgrade)
    INSTALL_PROFILE = 1701       # -> 1702 electrical/install profile
    IBG_RUN_STATUS = 1707        # -> 1708 IBG run status + mode name [cloud: get_runtime_data()]
    RELAY_STATUS = 1709          # -> 1710 relay adhesion/open status [cloud: get_power_info()]
    DEVICE_CONTROL = 1721        # -> 1722 maintenance: reboot/reset/update (opt=1; DESTRUCTIVE)
    OFFGRID = 1723               # -> 1724 off-grid settings (set with opt=1)
    MODE_LIST = 1725             # -> 1726 operating-mode list (id, name, reserved_soc)
    MODE_PAGE = 1727             # -> 1728 list keep-alive; opt=3 SETS the active mode
    BATTERY_INHIBIT = 1801       # -> 1802 battery inhibit SoC thresholds: inhSocNormal/Cold
    IBG_STATE = 1827             # -> 1828 IBG DSP/main state, firmware, uptime
    EVENT_BLOCK = 1829           # -> 1830 indexed data/event block
    BATTERY_MODULES = 1831       # -> 1832 battery module list: devNum, devMap[{id, devSN}]
    GENERATOR = 1901             # -> 1902 generator + scheduled grid-charge config
    SOLAR_PV = 1903              # -> 1904 solar / PV config


@dataclass(frozen=True)
class CmdInfo:
    request: int
    response: int
    name: str
    description: str
    #: Equivalent ``franklinwh-cloud`` method/REST call, or ``None`` if the
    #: capability has no known cloud counterpart. Populated from ``_CLOUD_API``
    #: below; see docs/CLOUD_MAPPING.md for the human-readable mapping.
    cloud_api: str | None = None


# request cmdType -> metadata
CATALOG: dict[int, CmdInfo] = {
    1101: CmdInfo(1101, 1102, "login", "Login handshake; reply carries firmware/version manifest (IBG_SN, FHP_SN, BMS_SN, *_VER)"),
    1109: CmdInfo(1109, 1110, "wifi_scan", "Scan for nearby WiFi access points"),
    1111: CmdInfo(1111, 1112, "wifi_config", "WiFi/AP config: wifi_SSID, wifi_Pw, ap_SSID, ap_Pw, wifi_Safety"),
    1113: CmdInfo(1113, 1114, "connectivity", "Connectivity: routerStatus, netStatus, awsStatus"),
    1115: CmdInfo(1115, 1116, "device_info", "Installer/user config: custom, usrName, distributor, installerId [cloud: get_device_info()]"),
    1117: CmdInfo(1117, 1118, "network_interfaces", "Interfaces: wifi/eth0 DHCP, MAC, IP, DNS, gateway"),
    1119: CmdInfo(1119, 1120, "network_switches", "Interface on/off switches: eth0/eth1/wifi/4G"),
    1121: CmdInfo(1121, 1122, "cloud_config", "Cloud server config: serverAddr (AWS IoT endpoint), region, MQTT credentials"),
    1201: CmdInfo(1201, 1202, "time_location", "Time, timezone, DST, latitude, longitude, postcode"),
    1203: CmdInfo(1203, 1204, "grid_policy", "Grid compliance policy: policy(0=no/1=semi/2=strict), gridPowerUP/Down [cloud: get_grid_profile_info(requestType=1)]"),
    1205: CmdInfo(1205, 1206, "der_comms", "DER comms config (installer): 'Enable Modbus SunSpec' toggle = sunsMdEn (Modbus TCP served on ip/port, default 502; observed sunsMdEn=1 = ON) + IEEE 2030.5 / SEP2 (enable, uri, dcap2030_5, lfdi, sfdi, pin, status2030_5). NB: sunsMdEn enables the Modbus INTERFACE (reads), NOT the write-plane — the franklinwh-modbus write-lock (SPAN/Lumin) is a separate gate. Distinct from the 1251 SUNSPEC_MODBUS_*_EVAL certification flags."),
    1207: CmdInfo(1207, 1208, "unknown_1207", "UNCONFIRMED: returns {enable, mode} with placeholder-looking values (111/222); purpose unknown — confirm against installer app before use"),
    1209: CmdInfo(1209, 1210, "unknown_1209", "UNCONFIRMED: returns {enable}; purpose unknown"),
    # Grid-compliance cmdTypes. These are just settings; the values reflect whatever
    # grid profile the site has loaded (the API is profile-agnostic). Field names are
    # the device's own raw keys.
    1211: CmdInfo(1211, 1212, "grid_ov_trip", "Grid over-voltage trip: HV1/HV2 (V*10), HV_T1/HV_T2 (s) [cloud: get_grid_profile_info(requestType=2)]"),
    1213: CmdInfo(1213, 1214, "grid_of_trip", "Grid over-frequency trip: HF1/HF2 (mHz*10), HF_T1/HF_T2 (s) [cloud: get_grid_profile_info(requestType=2)]"),
    1215: CmdInfo(1215, 1216, "grid_power_factor", "Grid fixed PF: powerFactor (%) [cloud: get_grid_profile_info(requestType=2)]"),
    1217: CmdInfo(1217, 1218, "grid_qv_mode", "Grid Q(V) curve: QV_MODE_V*/Q* setpoints [cloud: get_grid_profile_info(requestType=2)]"),
    1219: CmdInfo(1219, 1220, "grid_pv_mode", "Grid P(V) volt-watt: PV_MODE_V*/P* setpoints [cloud: get_grid_profile_info(requestType=2)]"),
    1221: CmdInfo(1221, 1222, "grid_pf_mode", "Grid P(f) droop: PF_MODE_F*/P* setpoints [cloud: get_grid_profile_info(requestType=2)]"),
    1223: CmdInfo(1223, 1224, "grid_reconnect", "Grid reconnect ramp: normalRate, reconnectRate (%/min) [cloud: get_grid_profile_info(requestType=2)]"),
    1225: CmdInfo(1225, 1226, "grid_dc_inject", "Grid DC injection: voltage (V*10), reconnectTime (s) [cloud: get_grid_profile_info(requestType=2)]"),
    1227: CmdInfo(1227, 1228, "grid_ride_through", "Grid ride-through flags: isAntiEnable, isVoltRideEnable, isFreqRideEnable [cloud: get_grid_profile_info(requestType=2)]"),
    1229: CmdInfo(1229, 1230, "grid_batt_access", "Battery grid-access mode: batteryAccessMode (0=restricted/1=full)"),
    1301: CmdInfo(1301, 1302, "power_flow", "Live power flow: run_status, mode (programme id), p_uti/p_sun/p_gen/p_fhp/p_load, soc, t_amb, daily kWh"),
    1401: CmdInfo(1401, 1402, "smart_circuit_schedule", "MISLEADING NAME - NOT the schedule source. Declares swXMode, swXAtuoEn, swXFreq, swXTimeEn[], swXTimeSet[], swXTime[] for X=1..3, but on observed firmware every field reads back zero/empty while 1409 carries the REAL populated schedule, and the response includes a bogus sw4 block whose integers are ASCII bytes read as int32 (e.g. swFreq 809119792) - an unpopulated struct serialised by index. Writes are REFUSED: result:1 reason:-2 (tested 2026-09-14). Use 1409 to READ the schedule; it cannot be written at all (see DISCARDED_WRITES)."),
    1403: CmdInfo(1403, 1404, "mode_config", "Active mode config: runingMode (programme id), modeChoose, name, electricity_type [cloud: get_mode()]"),
    1405: CmdInfo(1405, 1406, "mode_soc", "Per-mode min/max SoC block (9 fields). WRITABLE but FULL-BLOCK ONLY: a partial frame is refused (result:1 reason:-2); echoing all 9 fields with opt:1 applies (proven 2026-09-14). The eight min/max fields are INERT: they read 0 and stay 0 even in an applied write, and even when written as VALID pairs (min 0 / max 100, matching the cloud) - tested 2026-09-14. Only BBBackupSoc holds a value. Live per-mode reserves are in mode_list (1725/1726) 'reserved_soc' and match the cloud exactly, but have NO local write path: the cloud sets them via REST tou/updateSocV2, not sendMqtt. See bridge BACKLOG RESEARCH-RESERVE-SOC. [cloud: get_all_mode_soc() / update_soc()]"),
    1407: CmdInfo(1407, 1408, "tou_schedule", "TOU schedule: touStrategy, workdayLv, workdayFlag[], weekendLv, weekendFlag[] [cloud: get_gateway_tou_list()]"),
    1409: CmdInfo(1409, 1410, "smart_circuits", "Smart-circuit config: SwMerge, SwXName, SwXMode, SwXProLoad ... (write via 'call 1409 --data {opt:1,...}' or cloud cmdType 310; no --set flag on the smart_circuits subcommand)"),
    1411: CmdInfo(1411, 1412, "smart_circuit_meter", "Smart-circuit live metering: SwXVolt/Curr, SWXExpPower/Energy, CarSW* (EV charger)"),
    1103: CmdInfo(1103, 1104, "device_scan", "Device scan: devNum. The REQUEST must carry devNum (e.g. {opt:0,devNum:1}); without it the aGate answers result=1 reason=-2."),
    1105: CmdInfo(1105, 1106, "device_check", "Device list with check state: devNum, isOver, devMap[{id, devSN, checkResult}]. The 'id' values here are the selectors for the per-device reads (1703/1705/1833/1835)."),
    1123: CmdInfo(1123, 1124, "agate_serial", "aGate serial: aGate_SN. Returns the serial but reports result=1 reason=-2 — request shape not fully understood."),
    1303: CmdInfo(1303, 1304, "energy_history", "Daily energy history for one day, STORED ON THE GATEWAY: 96 quarter-hour points (rec_time[] '00:15'..'24:00') of p_uti/p_gen/p_fhp/p_load (W), the seven kwh_* daily totals, and sharp/peak/flat/valley TOU splits. REQUIRES {date: 'YYYY-MM-DD'} — that format exactly; '20260911' is accepted but returns nothing. pointMax/pointId/sno are RESPONSE metadata (pointId = points filled so far; sno = sequential day number). dayType is ECHOED BUT IGNORED (values 0-5 all return the same 96 points) — unlike the cloud's type=1..5, local is DAY GRANULARITY ONLY. Retention is a rolling window of roughly 105 days; older dates return sno=0 and empty arrays. BUG: the p_load series is a byte-identical COPY of p_fhp (battery power), not home load — confirmed on 15/15 days sampled across the whole window, while 1301 power_flow and the cloud both report p_load correctly. There is also no p_sun series (solar appears only as the kwh_sun daily total). See BACKLOG DEF-1303-PLOAD-DUP."),
    1703: CmdInfo(1703, 1704, "power_electronics", "Per-device inverter & DC-bus detail: batVol, gridVol1/2, inverterVolt1/2, positive/negative/middleBusVolt, gridFreq, loadCurr1/2, inverterCurr1/2, buckboostCurr, runMode, inverterStatus, DCDCStatus. REQUIRES id (from device_check/battery_modules). This is the ELECTRICAL half of the cloud's get_bms_info() (211 type 2) payload: every field maps across, some renamed (inverterVolt*->invVolt*, inverterCurr*->invCurr*, middleBusVolt->midBusVolt, batVol->pebatVolt). Together with 1705 it reconstructs cloud 211 type 2."),
    1705: CmdInfo(1705, 1706, "battery_cells", "Per-cell BMS telemetry: batVolt[] (mV per cell), batTemp[] (degC per cell), batTotalVolt, singleHighest/LowestVolt, singleHighest/LowestTemp, currGrp (A), batSoc, batSoh, alarmLevel. REQUIRES id (from device_check/battery_modules) — without it the arrays come back empty with result=1 reason=-1."),
    1833: CmdInfo(1833, 1834, "device_firmware", "Per-device serials and firmware: fhp_sn, ibg_sn, ibg_ver, ibg_iot, ibg_local, pe_sn, pe_ver, bms_sn, bms_ver. REQUIRES id. Richer than the 1101 login manifest (adds PE/BMS serials + bms_ver). Cloud counterpart is get_apower_info(), whose per-aPower block carries bmsVer/peHwVer/invVer/dcdcVer/fpgaVer; note the cloud reports more component versions while local adds ibg_iot/ibg_local and the pe_sn/bms_sn serials."),
    1835: CmdInfo(1835, 1836, "device_states", "Per-device state block: ibgDspState, ibgMainState (programme id), peState, bmsState. REQUIRES id. Split across two cloud calls: ibgDspState/ibgMainState correspond to dspRunStatus/ibgRunStatus from get_power_info() (211 type 1), and bmsState to bms_work from get_stats() (203 runtimeData). peState has no identified cloud field."),
    1501: CmdInfo(1501, 1502, "firmware_deliver", "OTA file-delivery status: fileName, order, operator, deliverResult. Discovered by probe sweep 2026-09-11; idle state returns result=1 reason=5 with empty strings. READ ONLY — an opt=1 write would push a firmware file. Never attempted."),
    1503: CmdInfo(1503, 1504, "firmware_upgrade", "OTA upgrade status: fileName, order, sign, type, steps, upgradeResult. Discovered by probe sweep 2026-09-11; idle state returns result=1 reason=8, steps=4. READ ONLY — an opt=1 write would trigger a firmware upgrade. Never attempted."),
    1701: CmdInfo(1701, 1702, "install_profile", "Install/electrical profile: electricSys, electricSupply, airSwitchCur, gridPhase*, solarInstallState, genRatePower, solarInv*, fhpRatePower, ratedGridVolt/Hz, isThreePhaseInstall. NB (2026-09-22): on aGate X V10R01B04D00, fhpRatePower reads 0 and genRatePower/solarInvRatePower=0 here — 1701 is NOT a reliable source for the battery inverter's max charge/discharge kW. That value is DERIVED from Modbus SunSpec Model 702 (WChaRteMaxRtg/WDisChaRteMaxRtg = 5000W, confirmed from the raw register). Use Modbus 702 for the force Power(%) rating, not 1701. ALSO carries the grid POWER-PLANE limits: kwRatePower, gridSoftLimit, gridHardLimit (-1 = unlimited, the same convention as cloud globalGridChargeMax/DischargeMax), gridExportEnable, isPcsDischgEn. electricSupply is UNDECODED (observed 63 = 0b111111, possibly a capability bitfield; it is NOT the service amps - FWHAI reports service_amps=100, matching airSwitchCur)."),
    1707: CmdInfo(1707, 1708, "ibg_run_status", "IBG run status: ibgRunStatus (programme id), name, energyMode [cloud: get_runtime_data()]"),
    1709: CmdInfo(1709, 1710, "relay_status", "Relay status: gridRelayAdhesion, gridRelayOpen, genRelayAdhesion, genRelayOpen [cloud: get_power_info()]"),
    1721: CmdInfo(1721, 1722, "device_control", "Device maintenance controls: reboot, reset, update (read-only by default; writing opt=1 would trigger these — DESTRUCTIVE, write UNVERIFIED)"),
    1723: CmdInfo(1723, 1724, "offgrid", "Off-grid settings: offgridSet, offgridSoc, offgridState (set with opt=1)"),
    1725: CmdInfo(1725, 1726, "mode_list", "Operating-mode list: current_id + list[{id, name, reserved_soc, scheduling_type(=cloud workMode), electricity_type}]. 'id' is a GATEWAY-SPECIFIC GUID permanently correlated to a scheduling_type (TOU=1, Self=2, Backup=3), so the two identify the same mode - ids are NOT portable between sites. This is also the only usable local read of reserved_soc (the 1405 block reads zeros)."),
    1727: CmdInfo(1727, 1728, "mode_page", "SET active mode: opt=3 + current_id (site-specific id from 1725/1726). ONLY opt=3 is implemented - opt 0,1,2,4,5,6,7 draw no reply at all (swept write-identical 2026-09-11), so there is no hidden opt carrying a reserve write. Reply is {opt,result} with no reason field. Extra fields (reserved_soc/soc/minSoc/selfMinSoc) are accepted with result:0, but that was tested write-identical so it does not prove they are applied. Use CLI subcommand 'mode' (or alias 'mode_page')."),
    1801: CmdInfo(1801, 1802, "battery_inhibit", "Battery charge-inhibit SoC thresholds: topSoc, inhSocNormal, inhSocCold, InhSocExtCold, normalTemp, coldTemp, extColdTemp, startHeatBatTemp, stopHeatBatTemp, batMaxChFactor, delayToChTime, blackStartOnOff, startGenSoc, stopGenSoc, InhUseFlag. CAUTION: on observed firmware the values read back as the sequential integers 0,1,2,...,14 - i.e. field POSITION, not real data. Treat this block as unpopulated until a site is found that returns plausible values."),
    1821: CmdInfo(1821, 1822, "unknown_1821", "UNCONFIRMED: returns {enable}; purpose unknown"),
    1823: CmdInfo(1823, 1824, "unknown_1823", "UNCONFIRMED: returns {powerOn, powerOff}, both 0. NOT the grid charge/discharge power limits — those live in install_profile (1701: kwRatePower, gridSoftLimit, gridHardLimit) and solar_pv (1903: grid_feed_max), all using the -1=unlimited convention these do not. LEAD: likely the software equivalent of the PHYSICAL aPower power switch (the System User Manual documents one per unit), matching the cloud TOU block's optional powerOffApower field; 1821 {enable} may be its enable flag. UNTESTED and potentially DESTRUCTIVE - a successful write may shut the battery down, with recovery possibly needing the physical switch. DO NOT WRITE remotely. See BACKLOG TEST-1823-APOWER-POWER (on-site test planned ~2026-09-26)."),
    1825: CmdInfo(1825, 1826, "unknown_1825", "UNCONFIRMED: returns {power}, value 0. NOT a force-charge/discharge setpoint — the cloud has no sendMqtt code for that (force_charge/force_discharge build a TOU session; setPowerControl is REST), and the real power limits are in 1701/1903. Purpose still unknown."),
    1827: CmdInfo(1827, 1828, "ibg_state", "IBG DSP/main state: infiNum, ibgDspState, ibgMainState (programme id), firmware versions, uptime"),
    1829: CmdInfo(1829, 1830, "event_block", "Gateway event log. Returns ONLY {num} = the number of stored events; on a healthy site that is 0, as observed 2026-09-14. The documented data/level/startTime fields appear only when num > 0 — six request shapes (plain, num=1, num=10, index=0, id=0, no dataArea) all returned num:0 with result:0, so the entry-fetch shape is UNKNOWN and cannot be determined until a gateway actually has events. Do not build a viewer against a guess."),
    1831: CmdInfo(1831, 1832, "battery_modules", "Battery module list: devNum, devMap[{id, devSN}]"),
    1901: CmdInfo(1901, 1902, "generator", "Generator + scheduled grid-charge config: genEn/RatedPower/Start/CloseElec, chargeN windows"),
    1903: CmdInfo(1903, 1904, "solar_pv", "Solar/PV config: remoteSolarEn/Mode, solarRatedPower, installPV1/2port (the aGate's two AC solar inputs), PV1/PV2RatedPower (UNITS OF 100 W - observed 66 = 6.6 kW), loadSolar*, protectTime, reSolarSoc, solarPower, solarPowerGen, relay states. ALSO carries grid_feed_max (-1 = unlimited). NB local grid_feed_max=-1 while the cloud reports gridFeedMax=10.0 kW for the same site. Probably not a conflict: the cloud also returns notControlExportSolar=true ('solar export is unmetered/uncontrolled') and gridFeedMaxFlag=2, so the cloud appears to store a configured-but-unapplied value while the device reports the EFFECTIVE one. Unconfirmed - a cloud-side change plus a local re-read would settle it. See BACKLOG INFO-POWER-PLANE-LOCAL."),
}

# Detailed grid-compliance settings block — 14 cmdTypes (1251..1277, odd only).
# These are grid-compliance settings; their values reflect whatever grid profile the
# site has loaded (the API is profile-agnostic — it does not fix a standard). The
# ComplianceRuleType field just identifies the loaded profile. Field names are the
# device's own raw keys. Cloud equivalent: get_grid_profile_info(requestType=2).
_GRID_COMPLIANCE_SECTIONS: dict[int, tuple[str, str]] = {
    1251: ("grid_compliance_main",          "Compliance main: ComplianceRuleType (loaded profile id), ES_PERMIT_SERVICE_AS"),
    1253: ("grid_compliance_id",            "Compliance identity: ComplianceRuleType (loaded profile id)"),
    1255: ("grid_compliance_es_voltage",    "ES voltage window: ES_PERMIT_SERVICE_AS, ES_V_LOW/HIGH_AS, ES_HZ_LOW/HIGH_AS"),
    1257: ("grid_compliance_es_reconnect",  "ES reconnect timing: ES_DELAY_AS (s), ES_RAMP_RATE_AS (W/s)"),
    1259: ("grid_compliance_ui_mode",       "UI mode: UI_MODE_ENABLE_AS"),
    1261: ("grid_compliance_ov_trip",       "OV trip: OV1/OV2_TRIP_V_AS (V*10), OV1/OV2_TRIP_T_AS (s)"),
    1263: ("grid_compliance_const_pf",      "Constant PF: CONST_PF_MODE_ENABLE_AS, CONST_PF_AS, CONST_PF_EXCITATION_AS"),
    1265: ("grid_compliance_const_q",       "Constant Q: CONST_Q_MODE_ENABLE_AS, CONST_Q_AS"),
    1267: ("grid_compliance_pv_curve",      "P(V) volt-watt: PV_MODE_ENABLE_AS, PV_CURVE_V*/P*_AS setpoints"),
    1269: ("grid_compliance_qp_curve",      "Q(P): QP_MODE_ENABLE_AS, QP_CURVE_P*_GEN/LOAD_AS setpoints"),
    1271: ("grid_compliance_qv_curve",      "Q(V) volt-reactive: QV_MODE_ENABLE_AS, QV_VREF_AS, QV_CURVE_V*/Q*_AS"),
    1273: ("grid_compliance_pf_droop",      "P(f) droop: PF_MODE_ENABLE_AS, PF_DBOF/DBUF_AS, PF_KOF/KUF_AS"),
    1275: ("grid_compliance_ramp",          "Ramp rate: NORMAL_RAMP_AS (W/s)"),
    1277: ("grid_compliance_fast_reconnect", "Grid fast reconnect: gridFastEnable"),
}
for _cmd, (_name, _desc) in _GRID_COMPLIANCE_SECTIONS.items():
    CATALOG[_cmd] = CmdInfo(_cmd, _cmd + 1, _name, _desc)


# ── Local -> cloud equivalence ────────────────────────────────────────────
# Machine-readable form of docs/CLOUD_MAPPING.md §1. The value is the
# `franklinwh-cloud` method (or REST path) that covers the same capability.
#
# NOTE: the cloud sendMqtt codes (203, 211, 310/311, 317, 335/337, 339, 341)
# are a SEPARATE numbering space from the local codes in this file. Cloud 211
# is NOT local 211. Only the *capability* corresponds, never the number.
#
# They are also NOT REACHABLE over TCP/9000. Tested 2026-09-11 against a live
# aGate: every cloud code (203, 211, 310, 311, 315, 317, 327, 335, 337, 339,
# 341, 353) makes the gateway CLOSE THE CONNECTION rather than answer or
# refuse. Out-of-band codes generally do this — an in-band code the device does
# not implement replies {"opt":0,"result":1,"reason":4} on a healthy socket,
# whereas anything outside roughly 1101-1909 drops the session. So the cloud
# relay and the local broker are separate dispatchers; a capability the cloud
# reaches by sendMqtt is not automatically reachable locally.
#
# Absence from this dict means "no known cloud equivalent" — which for an
# unprobed area means *not yet found*, not *does not exist*.
#
# Not every entry is 1:1. The cloud packs into one cmdType with a `type`
# discriminator what the local channel splits across several codes, so cloud
# 211 type 1 (`get_power_info()`) covers local 1703 (electrical), 1709 (relays)
# and part of 1835 (DSP/IBG state). Read a value here as "the cloud call that
# carries this data", not "the cloud call with this exact payload".
_CLOUD_API: dict[int, str] = {
    1109: "wifi scan (335)",
    1111: "wifi config (337)",
    1113: "cloud connectivity (339)",
    1115: "get_device_info()",
    1117: "get_network_info() (317)",
    1119: "net switches (341)",
    1121: "cloud connectivity (339)",
    1203: "get_grid_profile_info(requestType=1)",
    1205: "get_grid_profile_info / DER comms",
    1301: "get_stats() / get_device_composite_info() (203)",
    1303: "get_power_by_day(dayTime) / get_electric_data(type=1)",
    1403: "get_mode()",
    1405: "get_all_mode_soc() / update_soc()",
    1407: "get_gateway_tou_list()",
    1409: "get_smart_circuits_info() (311) / toggle (310)",
    1411: "get_smart_circuits_info() (311)",
    1707: "get_runtime_data()",
    1709: "get_power_info()",
    1725: "set_mode()",
    1727: "set_mode()",
    1703: "get_bms_info() (211 type 2)",
    1705: "get_bms_info() (211 type 2/3)",
    1721: "system control (315) — reboot only; cloud never populates reset",
    1723: "get_grid_status() / set_grid_status() (REST selectOffgrid/updateOffgrid)",
    1833: "get_apower_info()",
    1835: "get_stats() bms_work (203) + get_power_info() (211 type 1)",
    1831: "get_bms_info() (211 type 2/3) — module list only",
    1901: "get_generator_info() / set_generator_mode()",
    1903: "get_stats() remoteSolar* (203 runtimeData) — partial",
}
# The grid-compliance settings blocks all map to the same coarse cloud call.
for _cmd in list(range(1211, 1230, 2)) + list(_GRID_COMPLIANCE_SECTIONS):
    _CLOUD_API.setdefault(_cmd, "get_grid_profile_info(requestType=2)")

# Apply the mapping and strip the now-redundant inline "[cloud: ...]" notes
# from the descriptions — the equivalence is a field/column now, not prose.
_CLOUD_NOTE_RE = re.compile(r"\s*\[cloud:[^\]]*\]")
for _cmd, _info in list(CATALOG.items()):
    CATALOG[_cmd] = replace(
        _info,
        description=_CLOUD_NOTE_RE.sub("", _info.description),
        cloud_api=_CLOUD_API.get(_cmd),
    )


# ── Confidence / grouping metadata (used by the CLI's catalog renderer) ───
#: Codes that respond but whose purpose is NOT confirmed. Their payloads look
#: like placeholders under the usual ``{"opt": 0}`` probe, which may simply mean
#: the request needs a different payload shape — see RESEARCH-BMS-CELL-LOCAL.
UNCONFIRMED: frozenset[int] = frozenset({1207, 1209, 1821, 1823, 1825})

#: Reads addressed to ONE device: the request must carry an ``id`` selector taken
#: from ``device_check`` (1105) / ``battery_modules`` (1831) ``devMap[].id``.
#: Called without it they answer result=1 reason=-1 with empty/zero fields, which
#: is easy to mistake for "this code returns nothing".
NEEDS_ID: frozenset[int] = frozenset({1703, 1705, 1833, 1835})

#: Reads that take a ``date`` ("YYYY-MM-DD") in the request. Without it they
#: return the full key set with empty arrays and ``result=1 reason=-1`` — the
#: same trap as NEEDS_ID.
NEEDS_DATE: frozenset[int] = frozenset({1303})

#: The seven energy channels, in the order used by the sharp/peak/flat/valley
#: arrays in ``energy_history`` (1303). Verified on hardware: for every channel
#: sharp+peak+flat+valley equals the matching ``kwh_*`` daily total.
ENERGY_CHANNELS: tuple[str, ...] = (
    "kwh_uti_in", "kwh_uti_out", "kwh_sun", "kwh_gen",
    "kwh_fhp_di", "kwh_fhp_chg", "kwh_load",
)

#: Tariff tiers used by the TOU schedule (1407 ``*Flag``). Same numbering as
#: ``franklinwh_cloud.const.WaveType`` — the local and cloud sides agree on this
#: vocabulary, so a schedule read locally can be named the same way the app names
#: it. Note 3 is unused/unobserved.
WAVE_TYPES: dict[int, str] = {
    0: "Off-Peak",
    1: "Mid-Peak",
    2: "On-Peak",
    4: "Super Off-Peak",
}

#: Tier array names carried by ``energy_history`` (1303).
#:
#: These are tariff-tier buckets and each channel's four values sum exactly to
#: that channel's ``kwh_*`` total (verified on hardware). What is NOT
#: established is which clock schedule the device buckets by:
#:
#: * It is NOT the local 1407 schedule, nor the cloud's static block list —
#:   integrating the grid series against either does not reproduce the split.
#: * A FIXED boundary does fit. Fitting against 30-second samples (from the
#:   bridge's store, far finer than 1303's 15-minute series) puts flat->peak
#:   somewhere around 15:45-18:00 and peak->valley around 20:15-21:00 on every
#:   day tested. The fit is NOT sharp: export is intermittent, so a wide range
#:   of boundary pairs scores similarly.
#:
#: An earlier note here claimed the boundary "moves day to day (14:45, 15:15,
#: 16:15, 18:15)". That was WRONG — an artifact of locating the boundary by
#: cumulative-crossing, which is only meaningful when export is continuous
#: across it. Window-fitting on the same days is consistent with a fixed
#: schedule.
#:
#: Observed behaviour instead: ``flat`` holds the solar day (~99% of kwh_sun and
#: all of kwh_fhp_chg), ``peak`` holds the evening discharge/export window
#: (kwh_fhp_chg is exactly 0 there every day), ``valley`` the overnight tail.
#: The boundary is most likely fixed but under-determined by energy data alone.
#: Settling it needs the live tier accumulators from 1301 (see
#: energy.tier_transitions), not more inference. No tier -> wave-code table is
#: published here. See BACKLOG DEF-1303-TIER-BASIS.
TIERS: tuple[str, ...] = ("sharp", "peak", "flat", "valley")

#: ``sharp`` appears DEPRECATED: zero for all seven channels on every day
#: sampled across the full ~105-day retention window. franklinwh-cloud's own
#: docs likewise list "Sharp" as an unlisted waveType. Kept in TIERS because the
#: device still emits the array and it still participates in the sum.
DEPRECATED_TIERS: frozenset[str] = frozenset({"sharp"})

#: Reads that sit next to destructive writes. The ``opt=0`` read itself is safe;
#: the flag exists so the CLI can say so rather than hiding the command.
MAINTENANCE: frozenset[int] = frozenset({1501, 1503, 1721})

#: Display grouping: (upper bound inclusive, label). Ordered by code.
_FAMILY_RANGES: tuple[tuple[int, str], ...] = (
    (1199, "Device, network & cloud"),
    (1209, "Time, grid policy & DER"),
    (1249, "Grid settings (trips, curves, ramps)"),
    (1299, "Grid compliance blocks"),
    (1399, "Live power flow"),
    (1499, "Modes & smart circuits"),
    (1699, "Firmware / OTA"),
    (1799, "Install, run status & control"),
    (1899, "Battery & device state"),
    (9999, "Generator & solar"),
)


def family(cmd_type: int) -> str:
    """Display group for a request ``cmdType``."""
    for upper, label in _FAMILY_RANGES:
        if cmd_type <= upper:
            return label
    return "Other"


def writes_for(cmd_type: int) -> list[str]:
    """Names of exposed write helpers that target this request ``cmdType``."""
    return sorted(n for n, w in WRITES.items() if w["cmd"] == cmd_type)


# ── Control writes (Direct-Connect) ───────────────────────────────────────
# The broker uses an opt convention: opt=0 reads, opt=1 writes a config block
# (the read cmdType, with the setpoint fields filled in), and 1727 opt=3 sets
# the active operating mode by id. Confirmed against aGate X by capturing the
# official app over TCP/9000 (2026-06-19). The aGate replies opt/result/reason;
# some settings (e.g. SOC cut-off) still bounce to the cloud ("System Busy").
WRITES: dict[str, dict] = {
    "set_mode": {
        "cmd": 1727, "opt": 3, "fields": ["current_id"],
        "note": "current_id is a programme id from mode_list (1725/1726), "
                "e.g. 47522 Emergency Backup / 85232 Self-Consumption / "
                "29287 TOU — IDs are site-specific.",
    },
    "set_offgrid": {
        "cmd": 1723, "opt": 1, "fields": ["offgridSet", "offgridSoc"],
        "note": "offgridSet=1 go off-grid / 0 reconnect; offgridSoc = floor SoC.",
    },
    "set_smart_circuit": {
        "cmd": 1409, "opt": 1, "fields": ["SwXMode", "SwXProLoad", "SwXMsgType"],
        "note": "Full-block RMW: read 1409, set every SwXMsgType=0 then the target "
                "SwXMsgType=1, SwXMode=1 on / 0 off, SwXProLoad=Mode^1, write the whole "
                "block back. Mirrors cloud set_smart_circuit_state (cmdType 311). "
                "Self-verifies by re-reading SwXMode. NOT yet hardware-verified (aGate "
                "offline) — the read-back is the safety net.",
    },
    "set_generator": {
        "cmd": 1901, "opt": 1,
        "fields": ["genEn", "manuSw", "genStartElec", "genCloseElec", "chargeNEn",
                   "chargeNStartTime", "chargeNEndTime", "oilmanoEn", "manoFre",
                   "manoDate", "manoStartTime", "manoTime"],
        "note": "HARDWARE-VERIFIED 2026-09-14 (FW V12R02B30D06). Full-block RMW + "
                "read-back. Operating windows (chargeN), the exercise schedule (mano*) "
                "and the generator SoC thresholds ALL apply and persist - verified on a "
                "site with NO generator module fitted, so the config is writable "
                "independently of the hardware being present. chargeN are the "
                "generator's three operating windows (FranklinWH documents 'up to 3 "
                "non-overlapping periods 00:00-23:59'), NOT grid-charge windows. "
                "Contrast set_circuit_schedule: the SAME gateway silently discards "
                "smart-circuit schedule writes - do not generalise between them.",
    },
    "set_der_comms": {
        "cmd": 1205, "opt": 1, "fields": ["sunsMdEn", "enable"],
        "note": "SunSpec Modbus / IEEE 2030.5 toggles (full-block RMW). The change is NOT "
                "immediate, and the delay depends on firmware. On FW V12R02B30D06, setting "
                "sunsMdEn makes the gateway open or close TCP port 502 a few seconds after the "
                "write - in both directions, and without a reboot. On older firmware, turning "
                "it OFF took effect at once but turning it ON did nothing until the gateway "
                "was rebooted. So do not judge success by a single read: keep checking whether "
                "port 502 is accepting connections for several seconds, and only fall back to "
                "--and-reboot if it never changes. Enabling IEEE 2030.5 hands dispatch control "
                "to a DERMS.",
    },
    "reboot": {
        "cmd": 1721, "opt": 1, "fields": ["reboot"],
        "note": "Full-block {reboot:1}. Destructive; can trigger 4G failover. Proven to "
                "reboot, after which the gateway resumes listening on TCP port 502 (verified 2026-07-25). Exposed with confirm + 4G "
                "pre-warning + subnet re-discovery.",
    },
}

#: Writes the aGate ACCEPTS (``result:0``) and then silently ignores. A ``result:0``
#: ack on this firmware means "frame parsed", NOT "setting applied" - every write needs
#: a read-back before it can be reported as success.
DISCARDED_WRITES: dict[str, dict] = {
    "smart_circuit_schedule": {
        "cmd": 1409, "opt": 1, "fields": ["SwXTime", "SwXTimeEn", "SwXTimeSet"],
        "firmware": "V12R02B30D06",
        "note": "HARDWARE-TESTED 2026-09-14 on circuit 2, five payload shapes: full "
                "block; + SwXMsgType target selector; + SwXAtuoEn=1; + SwXFreq=1; and a "
                "partial frame of only the schedule fields. Every one returned "
                "result:0 reason:0 and changed NOTHING. Writing via 1401 (the command "
                "named smart_circuit_schedule) is refused outright: result:1 reason:-2. "
                "CONTROL: set_smart_circuit (on/off) on the same command and circuit "
                "applied and read back 0->1->0 moments later, so the transport is fine "
                "and the schedule fields specifically are ignored - the signature of a "
                "cloud-owned setting, as with set_mode_soc. The cloud library also "
                "declines to write V2 schedules (franklinwh-cloud API_COOKBOOK.md:1607), "
                "so this is a vendor constraint, not a local gap. Schedules are "
                "READABLE locally (1409 SwXTime); change them in the app. Generator "
                "schedules are NOT affected - see set_generator. NEWER HARDWARE PATH (2026-09-14): the jkt628/franklinwh-python fork, captured from the Android app, uses CLOUD cmdTypes 387 (smart-circuit config, read opt:0 / WRITE opt:1 full-block) and 389 (status) with a completely different schema - smartSwitch[].openAction, merge:[1,2], and a per-circuit 'schedule' dict - versus this protocol's SwXName/SwXMode/SwXTime. That looks like the SCV2 module generation (the fork links the ACCY-SCV2-US install guide). Two caveats: (a) the LOCAL broker does not implement 387/389 at all - probed 385-391 on FW V12R02B30D06 and every one CLOSES THE CONNECTION, i.e. out-of-band, so this is not a local path on this firmware; (b) the fork READS schedule but never writes it - its only 387 writes are openAction and merge - so schedule writing is still not demonstrated anywhere, only made plausible by schedule living inside a block that is writable as a whole.",
    },
}

#: ``opt`` is an OPERATION SELECTOR, not a global read/write flag.
#:
#: The 0 = read / 1 = write convention holds for most commands, which is why it reads
#: like a rule — but it is only a convention:
#:
#:   * ``1725`` mode_list  — ``opt:1`` is the **READ**; ``opt:0`` draws no reply at all,
#:     and omitting ``opt`` is refused ``result:1 reason:-2``.
#:   * ``1727`` mode_page  — acts on ``opt:3``; 0,1,2,4-7 draw no reply.
#:   * most reads          — send **no dataArea at all** (``null``), not ``{"opt":0}``.
#:
#: So "is this a write?" can only be answered per command, by comparing against that
#: command's own read payload. Assuming ``opt != 0`` means write produced two real bugs:
#: eleven 1725 "write" attempts that were silently just re-reads, and a bridge write-gate
#: that refused a legitimate 1725 read with HTTP 428.
#:
#: The request payload a READ needs, for commands where plain ``{"opt": 0}`` does NOT
#: work. Sending the wrong shape here is not a soft failure: 1725 with ``opt:0`` draws
#: NO REPLY AT ALL and the caller blocks until timeout, and omitting ``opt`` entirely is
#: refused with ``result:1 reason:-1``.
#:
#: 1725 is the trap that matters: ``opt:1`` is its READ, not a write. Eleven "write"
#: attempts against it were silently just re-reads, which is exactly why they all came
#: back ``result:0`` with the state unchanged — see bridge BACKLOG RESEARCH-RESERVE-SOC.
READ_PAYLOADS: dict[int, dict] = {
    1725: {"opt": 1},                      # opt:1 IS the read; opt:0 hangs
    1303: {"opt": 0, "date": "YYYY-MM-DD"},
    1705: {"opt": 0, "id": 1},
    1703: {"opt": 0, "id": 1},
    1833: {"opt": 0, "id": 1},
    1835: {"opt": 0, "id": 1},
    1103: {"opt": 0, "devNum": 1},
}


def read_payload(cmd: int) -> dict:
    """The dataArea a read of ``cmd`` needs. Defaults to ``{"opt": 0}``."""
    return dict(READ_PAYLOADS.get(cmd, {"opt": 0}))


# Writes that are NOT exposed as commands — observed but not hardware-verified as safe.
UNVERIFIED_WRITES: dict[str, dict] = {
    "set_mode_soc": {
        "cmd": 1405, "opt": 1,
        "proven": "full-block only; partial frames refused result:1 reason:-2. Applies for "
                  "BBBackupSoc; the eight min/max fields are inert (stay 0).",
        "note": "Reserved SoC: local write is silently DISCARDED (result:0 but not "
                "persisted) — reserve is cloud-only. Do NOT expose. See "
                "DEF-RESERVED-SOC-RESEARCH (full-block 1727 test still pending).",
    },
}

# Reverse lookup: any code (request or response) -> human label.
_NAMES: dict[int, str] = {}
for _info in CATALOG.values():
    _NAMES[_info.request] = f"{_info.name} (request)"
    _NAMES[_info.response] = _info.description


def describe(cmd_type: int) -> str:
    """Human-readable label for a request or response ``cmdType``."""
    return _NAMES.get(cmd_type, f"cmdType {cmd_type} (unknown)")


# ── power_flow (1301) run_status ──────────────────────────────────────────
# The 1301 ``run_status`` is what the battery is *physically* doing. It uses the
# SAME integer vocabulary as the cloud API's ``runtimeData.run_status``
# (``franklinwh_cloud.const.RUN_STATUS``), so the local broker and the cloud
# agree byte-for-byte on this field. Do NOT confuse it with ``mode`` in the same
# payload — that is an arbitrary programme/schedule ID (large numbers like 29287
# or 85232), NOT a run_status key. VPP merely happens to use programme id 9.
# See docs/PROTOCOL.md and franklinwh-cloud docs/API_COOKBOOK.md.
RUN_STATUS: dict[int, str] = {
    0: "Standby",
    1: "Charging",
    2: "Discharging",
    3: "Reserved 3",
    4: "Reserved 4",
    5: "Off-Grid Standby",
    6: "Off-Grid Charging",
    7: "Off-Grid Discharging",
    8: "Debug Mode",
    9: "VPP mode",
}


#: Per-device state enums, matching ``franklinwh_cloud.const.states`` exactly so the
#: two projects describe the same number the same way. Used for 1835/1827.
BMS_STATE: dict[int, str] = {
    0: "Off", 1: "Initialization", 2: "Fault", 3: "Warning",
    4: "Shutdown", 5: "Standby", 6: "Charging", 7: "Discharging",
}

#: Power-electronics / PCS state (``peState``).
PCS_STATE: dict[int, str] = {
    0: "Off", 1: "Standby", 2: "Initialization", 3: "Fault", 4: "Warning",
    5: "Running / Active", 6: "Charging", 7: "Discharging",
    8: "Online / Running", 9: "Off-grid",
}

#: DC-DC controller state (``DCDCStatus`` from cmdType 1703). Mirrors the BMS values but
#: with a different standby offset. **Live-verified 2026-09-17** on an aPower against
#: bmsState + measured pack-current direction across all three states: 4 with I≈0 &
#: bmsState=Standby, 6 with I=+88A & bmsState=Charging, 7 with I=-6A & bmsState=Discharging
#: — closes the "211 state codes undecoded" question for ``DCDCStatus`` on this firmware.
#: NB: ``runMode`` and ``inverterStatus`` (same 1703 payload) held steady at 8 through all
#: three states, so they are NOT charge-state fields; their domains remain unproven.
DCDC_STATE: dict[int, str] = {4: "Standby", 6: "Charging", 7: "Discharging"}


def bms_state_desc(code: int) -> str:
    """Human label for a ``bmsState`` value."""
    return BMS_STATE.get(code, f"bmsState {code} (unknown)")


def pcs_state_desc(code: int) -> str:
    """Human label for a ``peState`` value."""
    return PCS_STATE.get(code, f"peState {code} (unknown)")


def dcdc_state_desc(code: int) -> str:
    """Human label for a ``DCDCStatus`` value (live-verified: 4/6/7 = Standby/Charging/
    Discharging). Unknown codes return the raw number rather than a guessed word."""
    return DCDC_STATE.get(code, f"DCDCStatus {code} (unknown)")


def run_status_desc(code: int) -> str:
    """Human label for a 1301 ``run_status`` code (aligns with the cloud API's
    ``RUN_STATUS``)."""
    return RUN_STATUS.get(code, f"run_status {code} (unknown)")


# ── Operating modes across channels ───────────────────────────────────────
# The local broker selects a mode by its SITE-SPECIFIC programme ``id`` (1727
# opt:3 ``current_id``). Its 1726 entries carry ``scheduling_type`` — which is
# the **cloud ``workMode``** value (TOU 1 / Self 2 / Backup 3) — but NOT the
# modbus ``oldIndex``. And modbus DISAGREES with cloud: register 15507 /
# ``oldIndex`` = Backup 1 / Self 2 / TOU 3 — i.e. it **swaps TOU and Backup**
# (only Self-Consumption matches). So map per channel and resolve by NAME, never
# reuse one channel's number on another. (TOU's local name may be a tariff name,
# e.g. "Ausgrid EA11 TOU" — match the substring "tou".)
OPERATING_MODES: dict[str, dict[str, int]] = {
    "Emergency Backup": {"modbus": 1, "cloud": 3},
    "Self-Consumption": {"modbus": 2, "cloud": 2},
    "Time-of-Use":      {"modbus": 3, "cloud": 1},
}

# Canonical mode name keyed by ``scheduling_type`` (== cloud ``workMode``).
WORK_MODE_NAMES: dict[int, str] = {v["cloud"]: name for name, v in OPERATING_MODES.items()}


def mode_label(entry: dict) -> str:
    """Canonical mode name for a 1726 ``list`` entry.

    The local broker labels the TOU mode with a SITE-SPECIFIC tariff name
    (e.g. ``"Ausgrid EA11 TOU"``); the mobile app and FWHAI show the generic
    ``"Time-of-Use"`` instead, which is clearer. Maps ``scheduling_type`` to the
    canonical name, falling back to the raw ``name`` if it's unknown.
    """
    return WORK_MODE_NAMES.get(entry.get("scheduling_type")) or entry.get("name", "?")


def response_for(cmd_type: int) -> int | None:
    """The response code paired with a request code.

    Known requests use the catalogued response. Unknown *odd* requests fall back to
    the protocol convention (response = request + 1) so a caller can still match the
    reply frame — important when probing un-catalogued cmdTypes. Returns ``None`` for
    even (non-request) codes.
    """
    info = CATALOG.get(cmd_type)
    if info:
        return info.response
    return cmd_type + 1 if cmd_type % 2 == 1 else None


def is_request(cmd_type: int) -> bool:
    """Odd codes are requests in this protocol."""
    return cmd_type % 2 == 1
