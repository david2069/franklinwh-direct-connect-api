# Local cmdType ↔ Cloud API mapping

How the local **sendMqtt** protocol (TCP 9000, integer `cmdType`) maps to the FranklinWH
**cloud** API (`franklinwh-cloud`: Python methods and its REST wrapper). The mapping is
**not 1:1** — the local API is fine-grained RPC per register block, the cloud API is
coarser and adds account/portal features. Some settings are **cloud-owned** and only
*readable* locally.

> Generated from `franklinwh_local.catalog.CATALOG` + live probing (last: 2026-09-11,
> aGate X-01 AU, FW `IBG_VER V12R02B30D06_260304`). Cloud names are from `franklinwh-cloud`
> (`MqttCmd` in `models.py`, `docs/MQTT_CMD_CATALOG.md`, `docs/API_REFERENCE.md`); REST
> paths are its local wrapper (`localhost:8099`, e.g. `/api/gateways/{id}/...`).
>
> **Start at [§0 Full reconciliation](#0-full-reconciliation)** — both directions with a
> verdict per row. Sections 1–3 below are the older per-direction lists, kept for detail.
> The machine-readable form is `CmdInfo.cloud_api` (`franklinwh-local catalog --json`).

---

## 0. Full reconciliation

Both directions, with an explicit verdict per row. Generated against
`franklinwh_local.catalog` (70 codes, 53 mapped) and `franklinwh-cloud`
(`MqttCmd` in `models.py`, `docs/MQTT_CMD_CATALOG.md`, `docs/API_REFERENCE.md`).

**The two numbering spaces are disjoint and mutually unreachable.** Cloud `211` is not
local `211`, and cloud codes cannot be sent over TCP/9000 at all — the aGate closes the
connection (tested 2026-09-11). Only *capabilities* correspond.

### 0a. Cloud `sendMqtt` cmdTypes → local

All 13 members of `MqttCmd`. Note cloud `203` answers with `201`, not `204`; every other
cloud code answers N+1, as local codes do.

| cloud | name | local | verdict |
|---|---|---|---|
| `203` → `201` | `STATUS` — composite/runtimeData | `1301 power_flow` | ✅ **mapped.** Same field names (`p_uti`, `p_sun`, `p_fhp`, `p_load`, `soc`, `kwh_*`) |
| `211 {type:1}` | electrical | `1703 power_electronics` (partial), `1709 relay_status` (relays), `1827/1835` (DSP/IBG state) | ✅ mapped, **split across 3 local codes** |
| `211 {type:2}` | BMS "Layer 1" | `1705 battery_cells` + `1703 power_electronics` | ✅ **mapped** — the two local codes together reconstruct it (§3e) |
| `211 {type:3}` | BMS "Layer 2" | — | ⛔ **cloud-only, confirmed absent.** The 26 fields in §3e: thermal sensors, `balanState`, `mosState`, cell-extreme positions, `actPwr`/`reactPwr` |
| `310` | `SMART_CIRCUIT_TOGGLE` | `1409 smart_circuits` (`opt:1`) | ✅ mapped |
| `311` → `312` | `SMART_CIRCUIT_INFO` | `1409` + `1411 smart_circuit_meter` | ✅ mapped |
| `315` → `316` | `SYSTEM_CONTROL` reboot/reset | `1721 device_control` | ✅ mapped. **Both sides expose `reset`; neither should ever populate it** |
| `317` → `318` | `NETWORK_INTERFACES` | `1117 network_interfaces` | ✅ mapped |
| `327` → `328` | `AESTHETICS` — aPower RGB LEDs | — | ⛔ **cloud-only, confirmed absent** from the local band |
| `335` → `336` | `WIFI_SCAN` | `1109 wifi_scan` | ✅ mapped |
| `337` → `338` | `WIFI_CONFIG` | `1111 wifi_config` | ✅ mapped |
| `339` → `340` | `CLOUD_CONNECTIVITY` | `1113 connectivity` + `1121 cloud_config` | ✅ mapped |
| `341` → `342` | `NETWORK_SWITCHES` | `1119 network_switches` | ✅ mapped |
| `353` → `354` | `ACCESSORY_LOADS` — SC/V2L/generator draw | `1411 smart_circuit_meter` (`CarSW*` = V2L), `1901 generator` | ✅ mapped, split |

**11 of 13 cloud sendMqtt codes have a local equivalent.** The exceptions are `211 type 3`
and `327`.

### 0b. Cloud REST capabilities → local

Not sendMqtt — these are cloud-server features. "Absent" rows are confirmed against the
exhaustive local sweep, not merely unfound.

| cloud capability | local | verdict |
|---|---|---|
| `get_power_by_day()` / `get_electric_data(type=1)` — daily energy | `1303 energy_history` | ✅ mapped (§3c) |
| `get_power_details(type=2..5)` — week/month/year/lifetime | — | ⛔ **cloud-side aggregation.** Local `dayType` is echoed but ignored; roll up client-side from `1303` |
| `get_mode()` / `set_mode()` | `1403 mode_config`, `1725/1727 mode_list/mode_page` | ✅ mapped — **mode switch works locally** |
| `get_all_mode_soc()` reserve **read** | `1726 mode_list` `reserved_soc` | ✅ mapped (read-only cache). **Use 1726, not 1405** — the 1405 block reads all zeros except `BBBackupSoc` on observed firmware |
| `update_soc()` reserve **write** | — | ⛔ **cloud-owned.** Local writes ACK `result:0` and are discarded; see §3 and BACKLOG `DEF-RESERVED-SOC-RESEARCH` |
| `get_gateway_tou_list()` — tariff schedule | `1407 tou_schedule` | ✅ mapped (§3d) |
| `saveTouDispatch` / `get_tou_dispatch_detail()` — per-block **dispatch** | — | ⛔ **cloud-only, confirmed absent** (§3d) |
| `get_grid_status()` / `set_grid_status()` | `1723 offgrid` | ✅ mapped — same `offgridSet`/`offgridSoc` field names; **write works locally** |
| `get_generator_info()` / `set_generator_mode()` | `1901 generator` | ✅ mapped |
| `get_grid_profile_info(requestType=1\|2)` | `1203`, `1211–1229`, `1251–1277` | ✅ mapped — local is **far** finer-grained (25 codes vs one call) |
| `get_device_info()` | `1115 device_info` | ✅ mapped |
| `get_network_info()` | `1117` | ✅ mapped |
| `get_apower_info()` | `1833 device_firmware` | ✅ mapped (§3e) |
| `get_runtime_data()` | `1707 ibg_run_status` | ✅ mapped |
| `get_power_info()` | `1709 relay_status` | ✅ mapped |
| `get_stats()` `remoteSolar*` | `1903 solar_pv` | ✅ partial |
| `force_charge()` / `force_discharge()` (VPP) | — | ⛔ cloud-only |
| `get_backup_history()`, `get_charge_history()` | — | ⛔ cloud-only (server-side records) |
| `get_power_control_settings()` — import/export caps | — | ⛔ cloud-only |
| Pricing, tariff plans, utilities, geography, run log, warranty, notifications | — | ⛔ cloud-only (portal/account) |
| `led_light_settings()` (327) | — | ⛔ cloud-only |

### 0c. Local-only cmdTypes

17 of 70 have no cloud counterpart — device-level reads the cloud API does not surface:

| local | what it is |
|---|---|
| `1101 login` | handshake / firmware manifest — local transport only |
| `1103 device_scan`, `1105 device_check`, `1123 agate_serial` | device enumeration; `1105` supplies the `id` selectors |
| `1201 time_location` | time, timezone, DST, lat/lon, postcode |
| `1401 smart_circuit_schedule` | per-switch schedule/timer |
| `1501 firmware_deliver`, `1503 firmware_upgrade` | OTA status. **Read-only — never write** |
| `1701 install_profile` | electrical/install profile |
| `1801 battery_inhibit` | cold-climate charge inhibit, generator start/stop SoC |
| `1827 ibg_state` | DSP/main state, firmware, uptime, `infiNum`, `peState` |
| `1829 event_block` | indexed event/data block |
| `1207`, `1209`, `1821`, `1823`, `1825` | **UNCONFIRMED** — respond, purpose unknown; payloads ignore all selectors tried |

### 0d. Coverage summary

| | count |
|---|---|
| local cmdTypes catalogued | 70 |
| …with a cloud equivalent | 53 |
| …local-only | 17 (5 of them UNCONFIRMED) |
| cloud sendMqtt codes | 13 |
| …with a local equivalent | 11 |
| …cloud-only | 2 (`211 type 3`, `327`) |

**Completeness caveat.** "Confirmed absent" rests on an exhaustive read sweep of
1101–1909 — every odd code, several payload shapes including the `id` selector: 68
responded, all already catalogued, 317 explicitly rejected. A *write-only* code with no
read handler would still be invisible, though every write-capable code found so far (e.g.
`1721`, `1409`) does answer `opt=0`. Codes outside that band are unreachable — the aGate
closes the connection.

---

## 1. Local cmdTypes with a cloud equivalent

| Local | Name | Cloud method / REST | Notes |
|-------|------|---------------------|-------|
| `1115` | device_info | `get_device_info()` | installer/user config |
| `1203` | grid_policy | `get_grid_profile_info(requestType=1)` | compliance policy |
| `1211–1229` | grid_ov_trip … grid_batt_access | `get_grid_profile_info(requestType=2)` | grid-compliance settings |
| `1251–1277` | grid_compliance_* | `get_grid_profile_info(requestType=2)` | detailed compliance block |
| `1303` | energy_history | `get_power_by_day(dayTime)` / `get_electric_data(type=1)` | daily energy history — see §3c |
| `1301` | power_flow | `get_stats()` / `get_device_composite_info()` (cmdType 203) | live power/SoC/mode |
| `1403` | mode_config | `get_mode()` / REST `mode/current` | active mode |
| `1405` | mode_soc *(read)* | `get_all_mode_soc()` / REST `mode/reserves` | **reserve is cloud-owned — read-only locally** (§3). NB the 1405 block itself reads zeros; the live values are in `1726` |
| `1407` | tou_schedule | `get_gateway_tou_list()` | TOU schedule (read) |
| `1409` / `1411` | smart_circuits / smart_circuit_meter | `get_smart_circuits_info()` (311) / toggle 310 | smart-circuit config + metering |
| `1707` | ibg_run_status | `get_runtime_data()` | run status / mode name |
| `1709` | relay_status | `get_power_info()` | relay adhesion/open |
| `1725/1727` | mode_list / mode_page | `set_mode()` / REST `mode/set` | **mode switch works locally** (write) |
| `1109/1111` | wifi_scan / wifi_config | wifi scan (335) / wifi config (337) | |
| `1117/1119` | network_interfaces / network_switches | `get_network_info()` (317) / net switches (341) | |
| `1121/1113` | cloud_config / connectivity | cloud connectivity (339) | AWS IoT endpoint / reachability |
| `1705` | **battery_cells** | `get_bms_info()` (211 type 2/3) | **per-cell voltages + temps, SoC/SoH.** Needs `{"id": N}`; see §4 |
| `1703` | power_electronics | `get_bms_info()` (211 type 2) | electrical half of the BMS payload; needs `id`. See §3e |
| `1833` | device_firmware | `get_apower_info()` | per-device serials + firmware; needs `id`. See §3e |
| `1835` | device_states | `get_power_info()` (211 t1) + `get_stats()` `bms_work` (203) | needs `id`. See §3e |
| `1831` | battery_modules | BMS (`get_bms_info()`, 211 type 2/3) | module list/SNs only |
| `1205` | der_comms | (grid-profile / DER comms) | Modbus-SunSpec + IEEE 2030.5 config |

## 2. Local-only cmdTypes (no clean cloud equivalent)

These are device-level reads/controls the cloud API doesn't surface as a distinct call:

| Local | Name | What it is |
|-------|------|-----------|
| `1101` | login | handshake / firmware manifest (local transport only) |
| `1201` | time_location | time / timezone / lat-lon / postcode |
| `1401` | smart_circuit_schedule | per-switch schedule/timer |
| `1701` | install_profile | electrical/install profile |
| `1721` | device_control | reboot / reset / update (maintenance) |
| `1723` | offgrid | off-grid / islanding (write works locally) |
| `1801` | battery_inhibit | cold-climate charge-inhibit + generator + black-start (see INFO note) |
| `1827` | ibg_state | DSP/main state, firmware versions, uptime |
| `1829` | event_block | indexed event/data block |
| `1901` | generator | generator + scheduled grid-charge config |
| `1903` | solar_pv | solar/PV config |
| `1207/1209/1821/1823/1825` | unknown_* | UNCONFIRMED (placeholder-value structs; purpose TBD) |

## 3b. Request-shape gotcha: per-device reads need an `id`

Most local reads are addressed to the **aGate** and take `{"opt": 0}`. Four are addressed
to a **specific device** and require an `id` selector taken from `device_check` (1105) or
`battery_modules` (1831) — `devMap[].id`:

| local | without `id` | with `{"opt":0,"id":1}` |
|-------|--------------|--------------------------|
| `1703` power_electronics | zeros, `result=1 reason=-1` | live bus/grid/inverter V and A |
| `1705` battery_cells | **`batVolt: []`, `batTemp: []`** | 16 cell voltages + 16 cell temps |
| `1833` device_firmware | empty strings | PE/BMS serials + `bms_ver` |
| `1835` device_states | zeros | DSP/main/PE/BMS states |

The trap is that the reply has the **same keys either way** — only the values differ. A
probe that scores replies by key count cannot tell them apart. Note the selector is a small
integer `id`, **not** the `fhpSn` serial the cloud API uses for the same data.

## 3c. Energy reporting: local is day-only, the cloud does the rollups

The cloud reporting API and local `1303 energy_history` return **the same seven channels
under the same names** (camelCase vs snake_case):

| local (1303) | cloud (`get_electric_data`) |
|---|---|
| `kwh_sun` | `kwhSuArray` |
| `kwh_gen` | `kwhGenArray` |
| `kwh_uti_in` / `kwh_uti_out` | `kwhUtiInArray` / `kwhUtiOutArray` |
| `kwh_fhp_chg` / `kwh_fhp_di` | `kwhFhpChgArray` / `kwhFhpDiArray` |
| `kwh_load` | `kwhLoadArray` |
| `rec_time[]` | `deviceTimeArray` |

Both take the date as **`YYYY-MM-DD`** (local `date`, cloud `dayTime`).

**The difference is granularity, and it is the one real gap:**

| granularity | cloud | local |
|---|---|---|
| Day | `get_power_by_day(dayTime)` — `api-energy/power/getFhpPowerByDay` | ✅ `1303` — 96 quarter-hour points |
| Week / Month / Year / Lifetime | `get_power_details(type=2..5)` / `get_electric_data(type)` — `api-energy/electric/getFhpElectricData` | ❌ none |

Local `1303` carries a `dayType` field, but it is **echoed and ignored** — values 0-5 all
return the same 96 quarter-hour points (tested on hardware 2026-09-11). So the cloud's
week/month/year/lifetime rollups are computed **cloud-side**, not fetched from the gateway.

**But the underlying day data is on the gateway, not the cloud.** `1303` serves complete
past days over the local channel with no cloud involvement, on a rolling window of ~105
days (verified: 2026-05-30 returns data, 2026-05-29 returns `sno: 0`). So daily reporting
can be reconstructed locally within that window; only longer-horizon history and the
prebuilt rollups need the cloud.

Local-only bonus: `1303` also returns per-tariff splits (`sharp`/`peak`/`flat`/`valley`),
and for every channel those four sum exactly to that channel's `kwh_*` total (verified).
Which clock drives that split is **unresolved** — it is demonstrably not the local 1407
schedule, see BACKLOG `DEF-1303-TIER-BASIS`. `sharp` is always zero and looks deprecated.

**Two local gaps in the interval series** (the daily `kwh_*` totals are fine):

| field | local `1301` live | cloud `203` live | local `1303` history |
|---|---|---|---|
| `p_load` (home load) | ✅ 194 W | ✅ 0.19 kW | ❌ byte-identical copy of `p_fhp` |
| `p_sun` (solar) | ✅ | ✅ | ❌ absent — daily `kwh_sun` total only |

So per-interval **load and solar history are not available locally**; derive them, or poll
`1301` on an interval and store it. See BACKLOG `DEF-1303-PLOAD-DUP`.

## 3d. TOU: the tariff schedule is local, the dispatch schedule is not

`1407 tou_schedule` carries the **tariff (wave) schedule**, stored as parallel arrays —
`<day>Lv` (block count), `<day>Time[]` (block start times) and `<day>Flag[]` (tariff tier),
for `workday` and `weekend`. Each block runs to the next block's start; the last to 24:00.

Local and cloud agree on the tier numbering (`catalog.WAVE_TYPES` ==
`franklinwh_cloud.const.WaveType`), and the local energy-history tier arrays name the same
tiers as the cloud's rate fields:

| wave | local name | local tier array | cloud name | cloud rate field |
|---|---|---|---|---|
| 0 | Off-Peak | `valley` | Off-Peak | `eleticRateValley` |
| 1 | Mid-Peak | `flat` | Mid-Peak | `eleticRateShoulder` |
| 2 | On-Peak | `peak` | On-Peak | `eleticRatePeak` |
| 4 | Super Off-Peak | — | Super Off-Peak | `eleticRateSuperOffPeak` |
| ? | — | `sharp` | Sharp | (unlisted waveType, possibly 3 or 5) |

### The cloud TOU block is a per-block OVERRIDE layer over global device settings

`tou_json_schema` (`franklinwh_cloud/const/tou.py`) shows a TOU block carries far more than
time + dispatch + tariff. Beyond the five mandatory fields (`name`, `startHourTime`,
`endHourTime`, `waveType`, `dispatchId`) it accepts, per block:

| cloud block field | UI column | local equivalent |
|---|---|---|
| `maxChargeSoc` | MAX CHG% | `1405 selfMaxSoc` / `touMaxSoc` — **per mode**, not per block (and reads 0) |
| `minDischargeSoc` | MIN DIS% | `1405 selfMinSoc` / `touMinSoc` (reads 0); `1726 reserved_soc` is the live per-mode value |
| `gridChargeMax` | GRID CHRG(W) | `1701 kwRatePower` / `gridSoftLimit` / `gridHardLimit` — global |
| `gridDischargeMax` | GRID DISCHG(W) | as above — global |
| `gridFeedMax` | — | `1903 grid_feed_max` — **exact name match**, global |
| `offGrid` | — | `1723 offgrid` — global |
| `heatEnable` | — | `1801 startHeatBatTemp`/`stopHeatBatTemp` — global |
| `solarCutoff` | — | `1903 reSolarSoc`? — unconfirmed |
| `powerOffApower` | — | `1823 {powerOn, powerOff}`? — **unconfirmed lead**, see BACKLOG |
| `chargeMax`, `chargePower`, `dischargeMax`, `dischargePower`, `gridMax`, `gcaoMax`, `rampTime`, `useModeFlag`, `solarPriority`, `loadPriority` | (Advanced) | no identified local equivalent |

**The pattern:** most of these exist on the device as **global** settings; the cloud adds
the ability to schedule them **per TOU block**. So the local channel is not missing the
*capability* so much as the *scheduling layer* — you can read (and in some cases set) the
global value locally, but not vary it by time block.

This also re-frames `1405 mode_soc`: its `selfMinSoc`/`selfMaxSoc`/`touMinSoc`/`touMaxSoc`
are the **per-mode** analogue of the cloud's per-block `minDischargeSoc`/`maxChargeSoc`.
The block is real and correctly shaped — it is simply unpopulated and unwritable, because
the cloud owns those values (§3).

**The gap:** the per-block **dispatch** action (Home Loads 1 / Standby 2 / Solar Charging 3
/ Self-Consumption 6 / Grid Export 7 / Grid Charge 8) that the app shows beside each block
is **not on the local channel**. 1407 returns only the tariff arrays, and it has no
sub-type carrying more — tested `{"opt":0}` with `type` 1-5, `paraType` 1-2 and `dispatch`,
all returning the identical key set. The full 1101-1909 sweep found no other schedule code.
So dispatch scheduling is cloud-owned (`saveTouDispatch` / `get_tou_dispatch_detail`);
locally you can read which tariff tier applies when, and the active *mode*
(`mode_config` / `ibgMainState`), but not the per-block dispatch programme.

The gateway does hold the time basis for all of this: `1201 time_location` returns its own
local `time`, `timezone`, `DST` flag and lat/lon, so day-of-week (workday vs weekend) is
resolvable locally.

## 3e. The 211 fan-out: one cloud code, several local ones

Cloud `211` packs three payloads behind a `type` discriminator. The local channel splits
the same data across separate cmdTypes, so these rows are **not 1:1** — read `cloud_api` as
"the cloud call that carries this data", not "the call with this exact payload".

| cloud | local |
|---|---|
| `211 {type:1}` `get_power_info()` — electrical | `1703 power_electronics` |
| `211 {type:1}` `get_power_info()` — relays | `1709 relay_status` |
| `211 {type:1}` `get_power_info()` — DSP/IBG state | part of `1835 device_states` |
| `211 {type:2\|3}` `get_bms_info()` — cell telemetry | **`1705 battery_cells`** |
| `211 {type:2\|3}` `get_bms_info()` — module list | `1831 battery_modules` (serials only) |

**Addressing differs, and this is the part that hides things.** The cloud selects a battery
by **serial** (`fhpSn`); the local channel selects by **integer index** (`id`, from
`device_check`/`battery_modules` `devMap[].id`). A local per-device read called without its
`id` returns the full key set with empty values — see §3b.

### Field-level detail

**`1705` + `1703` together reconstruct cloud `get_bms_info()` (211 type 2).** Every field
in both local codes maps to a field in that one cloud payload; several are renamed:

| local (1703) | cloud | local (1705) | cloud |
|---|---|---|---|
| `inverterVolt1/2` | `invVolt1/2` | `currGrp` | `batCurr` |
| `inverterCurr1/2` | `invCurr1/2` | `batVolt[]`/`batTemp[]` | same |
| `middleBusVolt` | `midBusVolt` | `batTotalVolt`/`batSoc`/`batSoh` | same |
| `batVol` | `pebatVolt` | `singleHighest/Lowest*` | same |
| `gridVol1/2`, `loadCurr1/2`, `gridFreq`, `buckboostCurr`, `positive`/`negativeBusVolt`, `runMode`, `inverterStatus`, `DCDCStatus` | same names | `alarmLevel` | same |

**26 cloud BMS fields have no local equivalent** — likely the type 3 "Layer 2" half that
the cloud merges in, for which no local code has been found:

| group | fields |
|---|---|
| thermal | `devTemp`, `llcTemp`, `invTemp`, `buckBoostTemp` |
| hardware state | `mosState`, `switchState`, `heatState`, `fanState`, `balanState` |
| cell extremes | `maxVolPos`, `minVolPos`, `maxTempPos`, `minTempPos` |
| power | `actPwr1/2`, `reactPwr1/2`, `outCur1/2` |
| voltages | `gridVoltAN/BN`, `solarVoltAN/BN`, `gridLineVol`, `invLineVol`, `samBatVol` |

That includes the whole Thermal Sensors panel and the balancing indicator, so those are
**cloud-only today**.

**`1833` vs `get_apower_info()`** — both carry per-aPower firmware. Cloud reports more
component versions (`fpgaVer`, `dcdcVer`, `invVer`, `blVer`, `thVer`, `peHwVer`,
`mpptAppVer`); local adds `ibg_iot`, `ibg_local` and the `pe_sn`/`bms_sn` serials. Both
carry `bms_ver`/`bmsVer`. Local `1833` is also richer than the local `1101` login manifest,
which leaves `pe_sn`/`bms_sn` blank.

**`1835` / `1827`** — `bmsState` matches the cloud BMS payload and `get_stats()`
`bms_work` (203). `ibgDspState`/`ibgMainState` correspond to `dspRunStatus`/`ibgRunStatus`
from `get_power_info()` (211 type 1). **`peState` and `infiNum` have no identified cloud
field.**

## 3. Cloud-only capabilities (no local cmdType)

The cloud API is authoritative for these — there is **no** local sendMqtt write:

| Capability | Cloud method / REST | Note |
|-----------|---------------------|------|
| ~~Per-cell BMS telemetry~~ | ~~`get_bms_info()`~~ | **RESOLVED 2026-09-11 — there IS a local equivalent: `1705 battery_cells`.** Previously listed here because a plain `{"opt":0}` probe returned empty arrays. |
| **Reserved SoC write** | `update_soc()` / REST `PATCH mode/reserve` | **Cloud-owned.** Local `1726 reserved_soc` is a read-only cache that syncs from the cloud in ~seconds (confirmed 2026-07-30). Local writes (`1405/1725/1727`) are discarded. |
| TOU schedule write | `set_tou_schedule()` / REST `schedule/set` | |
| Force charge / discharge (VPP) | `force_charge()` / `force_discharge()` | VPP-aware |
| Backup history | `get_backup_history()` / REST `control/backup-history` | |
| Pricing models / rate plans | REST `pricing/*` | cloud/HA integration |
| Utility services, geography, run-log | `get_utility_companies()`, `get_geography_list()`, `get_run_log_list()` | portal/account data |
| Grid-profile **name** | `get_grid_profile_info` → `complianceRuleTypeName` | local returns only the numeric `ComplianceRuleType` |
| HA config, security setup, rate-limits | REST `ha/*`, `security/*`, `system/rate-limits` | wrapper/service features |

---

## 4. Gaps & non-equivalence — summary

- **Reserved SoC** is the headline non-equivalence: cloud-owned; local is read-only (§3).
- **Grid-profile name**: cloud resolves a human name; local exposes only the enum id.
- **Granularity**: one cloud call (e.g. `get_grid_profile_info(2)`) maps to ~14+ local
  cmdTypes; one local read (`power_flow`) is a subset of the cloud `get_stats()` aggregate.
- **Mode identity**: local uses site-specific programme `id` (`current_id`); the cloud uses
  `workMode` (+ `oldIndex`, which swaps TOU/Backup — see PROTOCOL.md).
- **Local-only**: install/electrical profile, device maintenance (reboot), event blocks,
  cold-climate/generator inhibit, and the UNCONFIRMED structs have no cloud call.

## 5. Re-scanning for new cmdTypes

The local catalog reflects **one unit's firmware**. Re-scan (read-only, safe) when:
- The aGate takes an **OTA firmware update** — behaviour and cmdTypes can change (e.g. the
  der_comms apply-timing changed between firmwares).
- Testing against a **different / newer model** (aPower 2 / S / X, MAC-1, three-phase, …) —
  newer hardware may expose cmdTypes this older aGate X does not.

Method: sweep odd cmdTypes `1103–1909` with reliable matching (`response == request+1`,
treat `9999` as the error frame, drain buffered frames between probes). Last full re-scan
**2026-07-30 found no new cmdTypes** on this firmware — the catalog is complete for it.
Newer-model discovery needs a scan on that hardware.
