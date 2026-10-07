# FranklinWH aGate Local Broker Protocol

Reverse-engineered from packet captures of an aGate X (gateway serial
`10060006A02F2417xxxx`). This documents the **Direct-Connection** channel on
**TCP/9000**, which is distinct from the cloud `sendMqtt` REST relay.

**Connection model.** The aGate broadcasts its own WiFi hotspot (SSID
`AP_<serial-suffix>`, e.g. `AP_F24170091`) and listens on TCP/9000 there. The
mobile app joins the hotspot and connects to the gateway's AP-side IP
(`10.100.1.1` in the capture) on 9000. In the capture the client `10.100.1.81`
is the **phone** and `10.100.1.1:9000` is the **aGate**; this library plays the
phone's (client) role.

## Two layers, don't confuse them

| | Cloud `sendMqtt` (franklinwh-cloud) | Local broker (this repo) |
|---|---|---|
| Transport | HTTPS `POST /hes-gateway/.../sendMqtt` | Raw TCP, single long-lived socket |
| Envelope | Plaintext JSON | JSON header + position-ciphered body |
| `cmdType` space | `203, 211, 311, 317, 327, 335, 337, 339, 341, 353` | `1101–1120, 1201/2, 1301/2, 1409/10, 1701/2, 1723–1728, 1829/30, 1903/4` |

Both share the same JSON envelope (`type/timeStamp/snno/len/crc/dataArea`) and the
same `equipNo`. The local codes are a different numbering scheme — the cloud
`sendMqtt` catalog (`203, 211, 311, …`) is documented in
[`franklinwh-cloud/docs/MQTT_CMD_CATALOG.md`](https://github.com/david2069/franklinwh-cloud/blob/main/docs/MQTT_CMD_CATALOG.md).

**Shared field vocabulary.** Although the `cmdType` spaces differ, the *payload
fields* align across both channels. The most useful one is `run_status` (below):
the local `1301` `run_status` and the cloud `runtimeData.run_status` carry the
**same integer enum**, so an integration can normalise to one status model
regardless of transport.

## Frame format

A frame is one JSON object. The header is transmitted in cleartext; everything
from `"type"` onward is obfuscated:

```
{"cmdType":<N>,"equipNo":"<E>",   <- cleartext header
"type":<t>,"timeStamp":<ts>,"snno":<s>,"len":<L>,"crc":"<C>","dataArea":{...}}
\------------------------- ciphered region, i = 0 at first byte ----------------/
```

| Field | Meaning |
|-------|---------|
| `cmdType` | command code; odd = request, reply is `cmdType + 1` |
| `equipNo` | gateway serial; `"00000000"` in the pre-login `1101` |
| `type` | message type (0 in observed traffic) |
| `timeStamp` | Unix seconds |
| `snno` | monotonic per-session sequence number |
| `len` | byte length of the compact `dataArea` JSON string |
| `crc` | CRC32 (zlib) of the `dataArea` string, 8 uppercase hex digits |
| `dataArea` | command payload object |

## Cipher

Symmetric position-based additive cipher (no key):

```
encrypt: c[i] = (p[i] + seed + i) mod 256
decrypt: p[i] = (c[i] - seed - i) mod 256
```

- `seed = 0x3F` for normal frames (20-character serial).
- `seed = 0xA5` for the `1101` login (8-character `"00000000"` serial).

The first plaintext byte is always `"` (`0x22`), so decoding is
**self-synchronizing**: `seed = (firstCipherByte - 0x22) mod 256`. The library
detects the seed automatically on decode and selects it by `equipNo` on encode.

### Worked example

For a normal frame the ciphered region begins:

```
61 b4 ba b2 a8 66 7f 76 ...   ('a' = 0x61)
seed = 0x61 - 0x22 = 0x3F
p[0] = 0x61 - 0x3F - 0 = 0x22 = '"'
p[1] = 0xB4 - 0x3F - 1 = 0x74 = 't'   -> "type":...
```

## Command catalog

Odd code is the request; the reply is the next even code.

| Request → Reply | Name | dataArea highlights |
|---|---|---|
| 1101 → 1102 | login | req `{opt, minProtocolVer}`; reply: IBG_SN, FHP_SN, BMS_SN, PE_SN, all `*_VER` |
| 1109 → 1110 | wifi_scan | nearby APs |
| 1111 → 1112 | wifi_config | wifi_SSID, **wifi_Pw**, ap_SSID, ap_Pw, wifi_Safety |
| 1113 → 1114 | connectivity | routerStatus, netStatus, awsStatus |
| 1117 → 1118 | network_interfaces | wifi/eth0 DHCP, MAC, IP, DNS, gateway |
| 1119 → 1120 | network_switches | eth0/eth1/wifi/4G on-off |
| 1201 → 1202 | time_location | time, timezone, DST, latitude, longitude, postcode |
| 1205 → 1206 | der_comms | installer "**Enable Modbus SunSpec**" (sunsMdEn, ip, port 502) + IEEE 2030.5/SEP2 (dcap2030_5, lfdi, sfdi, pin) — **read-only here** (write withheld, see below) |
| 1301 → 1302 | power_flow | mode, run_status, p_uti, p_sun, p_gen, p_fhp, p_load, soc, t_amb, daily kWh |
| 1401 → 1402 | smart_circuit_schedule | per-switch schedule/timer: swXMode/AutoEn/Freq/TimeEn/TimeSet/Time (X=1..3) |
| 1409 → 1410 | smart_circuits | SwMerge, SwXName, SwXMode, SwXProLoad, SwXFreq, SwXTime (**write** with opt=1) |
| 1411 → 1412 | smart_circuit_meter | live SwXVolt/Curr, SWXExpPower/Energy, CarSW* (EV charger) |
| 1701 → 1702 | install_profile | electricSys, airSwitchCur, gridPhase*, solarInstallState, genRatePower, fhpRatePower |
| 1721 → 1722 | device_control | reboot, reset, update (maintenance; **destructive** if written) |
| 1723 → 1724 | offgrid | offgridSet, offgridSoc, offgridState (**write** with opt=1) |
| 1725 → 1726 | mode_list | current_id, list[{id, name, reserved_soc, ...}] |
| 1727 → 1728 | mode_page | opt=3 + current_id **SETS the active mode**; else paging/keep-alive |
| 1829 → 1830 | event_block | num, data, level, startTime |
| 1901 → 1902 | generator | genEn/RatedPower/Start/CloseElec, genStat, chargeN windows |
| 1903 → 1904 | solar_pv | remoteSolarEn, PV1/PV2RatedPower, loadSolar* |

> **Probing note (2026-07):** a full read-only sweep of odd cmdTypes `1103–1909`
> confirmed the above. Reliable probing requires matching the reply as
> `response == request + 1` and treating the aGate's `9999` frame as a generic
> error/unsupported response — otherwise late frames on a flaky link get
> mis-paired (an earlier sweep mis-attributed fields to the wrong cmdTypes).
> `response_for()` now returns `request + 1` for un-catalogued odd requests so
> `call()` works while probing.
>
> **Unconfirmed cmdTypes** (respond `result:0` but with minimal/placeholder fields;
> purpose not yet confirmed against the installer app): `1207 {enable,mode}`,
> `1209 {enable}`, `1821 {enable}`, `1823 {powerOn,powerOff}`, `1825 {power}`.

### Writes (control) — the `opt` convention

Most config commands are **read with `opt:0`** and **written with `opt:1`** (the
same cmdType, with the setpoint fields filled in). Operating-mode selection is
the exception — it's an `opt:3` on the mode-page command. The aGate replies with
`opt/result/reason`. Confirmed by capturing the official app driving an aGate X
over TCP/9000 (2026-06-19); see `franklinwh_direct_connect_api.WRITES`.

| Action | Request | dataArea |
|---|---|---|
| **Set operating mode** | `1727` | `{opt:3, current_id:<id>}` — `id` from `mode_list` (e.g. `47522` Emergency Backup, `85232` Self-Consumption, `29287` TOU; **site-specific**) |
| **Go off-grid / reconnect** | `1723` | `{opt:1, offgridSet:1\|0, offgridSoc:<n>}` |
| **Smart circuit on/off** | `1409` | `{opt:1, Sw1Mode:1\|0, …}` |
| **DER comms (Modbus / 2030.5)** | `1205` | `{opt:1, sunsMdEn:1\|0, enable:1\|0, …full block}` — full-block RMW |
| **Reboot** | `1721` | `{opt:1, reboot:1, reset, update}` — full block; **destructive** |

### Write apply timing — some settings do NOT take effect immediately

A `result:0` reply means the write was *accepted*, **not that it has taken effect**.
Settings differ in *when* they apply, and this can be **firmware-dependent** — so always
verify at the interface/service level, polling over a short window, not once.

| Setting | cmdType | When it applies |
|---|---|---|
| Operating mode | `1727` | **Immediate** |
| Off-grid / reconnect | `1723` | **Immediate** |
| Smart circuit on/off | `1409` | **Immediate** |
| **SunSpec Modbus** (`sunsMdEn`) | `1205` | **Delayed (~seconds), firmware-dependent.** On FW `V12R02B30D06` it applies a few seconds after the write in *both* directions (no reboot); on older firmware OFF was immediate and **ON required a reboot** to bind `:502`. Verify by polling `:502`; use a reboot only if it doesn't converge. |
| IEEE 2030.5 enable | `1205` | On **registration** with a 2030.5/DERMS server (`status2030_5`/`lfdi`), not on the flag write. |
| Reserved SoC | `1405` | **N/A locally** — silently discarded (cloud-only); see below. |

> ⚠ **Some settings require a reboot to take effect** (historically the Modbus toggle on
> older firmware; possibly others not yet characterised). A reboot (`1721`) is
> **destructive** and can make the aGate **fail over to 4G and not auto-reconnect to
> WiFi** — never reboot unattended (it can strand the local API until someone is on-site).
> See `DEF-WIFI-RECONNECT` in `BACKLOG.md`.

> **Reserved SoC `1405` is withheld** (not exposed as a command) — silently discarded
> locally (`result:0` but not persisted); reserve is cloud-only. See below and
> `PROTOCOL_DESIGN_REQUIREMENTS.md`.

> Not everything goes local: some settings (e.g. the smart-circuit **SoC cut-off**)
> returned "System Busy — try again later" over the broker, i.e. they still round-
> trip through the cloud. Mode / off-grid / circuit toggles complete locally.
>
> **Reserved SoC is CLOUD-OWNED — read-only locally (confirmed 2026-07-29).** The per-mode
> reserve appears only as a *read* field (`1726 reserved_soc`); local writes
> (`1405`/`1725`/`1727`, partial or full-block) ACK `result:0` but are discarded. Proof:
> setting a reserve via the FranklinWH **cloud** API changed the **local** `1726` value
> within ~8 s (cloud→aGate sync) — the aGate holds a read-only cache the cloud is
> authoritative for. **Set reserves via the cloud** (`franklinwh-cloud` `update_soc` /
> `PATCH …/mode/reserve`); read them locally with `mode --list`. (SPAN PICS also notes the
> reserve **resets on mode change** — consistent with a cloud-synced value.)

#### Mode identity differs by channel — resolve by name

The broker's `1726` list gives each mode a **site-specific `id`** (used as
`current_id`) plus `name`, `reserved_soc`, `electricity_type`, and
`scheduling_type` — and **`scheduling_type` IS the cloud `workMode`** (TOU 1 /
Self 2 / Backup 3). What's *not* in the local reply is the modbus `oldIndex`,
which **disagrees with cloud** — register `15507` / `oldIndex` swaps TOU and
Backup:

| Mode | modbus `oldIndex` | cloud `workMode` |
|---|---|---|
| Emergency Backup | 1 | 3 |
| Self-Consumption | 2 | 2 |
| Time-of-Use | 3 | 1 |

So **resolve a mode by name, never by number** (`franklinwh_direct_connect_api.OPERATING_MODES`
holds this mapping; `set_mode` already matches by name/alias). A multi-channel
integration must map each channel separately — using the modbus number on the
cloud (or vice versa) silently selects the wrong mode.

For **display**, `franklinwh_direct_connect_api.mode_label(entry)` returns the canonical name
(via `scheduling_type`), overriding TOU's site-specific tariff name (e.g.
"Ausgrid EA11 TOU" → "Time-of-Use") the way the mobile app and FWHAI do.

Add new rows to `franklinwh_direct_connect_api/catalog.py` as more codes are observed.

### `power_flow` (1301): `run_status` vs `mode` — don't confuse them

The `1302` reply carries two easily-confused fields:

**`run_status`** — what the battery is *physically* doing. Same integer enum as
the cloud API's `runtimeData.run_status` (`franklinwh_cloud.const.RUN_STATUS`),
so the two channels agree. Available as `franklinwh_direct_connect_api.run_status_desc(code)`:

| `run_status` | Meaning |
|---|---|
| 0 | Standby (idle) |
| 1 | Charging |
| 2 | Discharging |
| 3, 4 | Reserved |
| 5 | Off-Grid Standby |
| 6 | Off-Grid Charging |
| 7 | Off-Grid Discharging |
| 8 | Debug Mode (Franklin remote-support session) |
| 9 | **VPP mode** (utility/aggregator dispatch active) |

**`mode`** — *not* a status enum. It is an arbitrary **programme / schedule ID**
(the cloud calls it `runtimeData.mode`): large numbers like `29287` for a named
TOU programme, or `85232` as observed on this aGate. VPP merely happens to use
programme id `9`. **Do not** index `RUN_STATUS` with `mode` — only `run_status`
maps to the table. The active programme's human label arrives separately (cloud
`runtimeData.name`); the operating-mode list itself is the `1725/1726` page.

This mirrors the franklinwh-cloud guidance
([`API_COOKBOOK.md` → RUN_STATUS](https://github.com/david2069/franklinwh-cloud/blob/main/docs/API_COOKBOOK.md));
the operating-mode availability rules (grid-tied / has-solar gating) are in its
[`OPERATING_MODES_GUIDE.md`](https://github.com/david2069/franklinwh-cloud/blob/main/docs/OPERATING_MODES_GUIDE.md).

## Session flow (observed)

1. `1101 → 1102` login; the app connects with `equipNo "00000000"`, and the
   aGate returns the real serial and firmware manifest.
2. One-time enumeration of config/status blocks (11xx, 1701, 1903, 1829, …).
3. Steady-state polling: `1301/2` power flow, `1409/10` smart circuits,
   `1201/2` status, with `1727/8` as a ~5–6 s keep-alive.

`snno` increments per message; requests and responses are correlated by
`cmdType` pairing (and `snno`/`current_id` for paged lists).
