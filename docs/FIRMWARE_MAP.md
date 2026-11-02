# Firmware map — what changed between two aGate releases

**Status: WORKING DRAFT.** This is the evidence as it stands, written down so the permanent
version can be formulated from something real rather than from memory. Structure and
wording are provisional; the measurements are not.

**Scope: one aGate, one site.** Everything here is the reference AU gateway (`SyHdVersion`
102 = `AGT-R1V1-AU`, "aGate X-01-AU"), single aPower. One site on one upgrade path is not a
release map for the product — it is two points on one device. Nothing here should be read
as "FranklinWH changed X in release Y".

| | |
|---|---|
| **Earlier** | `IBG_VER V12R02B30D06_260304` — from a packet capture of the official app |
| **Later** | `IBG_VER V12R02B60D00_260924` — from a read on 2026-10-31 |
| **Apart** | roughly six months |
| **Hardware** | identical. Nothing swapped between the two. |

---

## 1. The headline: the wire protocol version changed

```
protocolVer   V1.11.03  ->  V1.12.02
```

**This is the finding that explains the others.** Both commands known to have changed their
key set did so across this boundary. If a key set varies, `protocolVer` is the field most
likely to predict it — more so than `IBG_VER`, which moves for reasons that do not affect
the wire.

**Unverified:** that `protocolVer` *causes* or reliably signals key-set changes. Two
commands across one upgrade is a correlation, not a rule. But it is the right field to
record and to test against.

Note this library's login sends `minProtocolVer: "V1.00.00"`, and both firmwares accepted
it. There is no evidence the gateway refuses an old minimum.

## 2. Component versions — measured, complete for `1102`

All from the `1102` login manifest, both sides. Serials excluded.

| Field | Earlier | Later | |
|---|---|---|---|
| `protocolVer` | `V1.11.03` | `V1.12.02` | **changed** |
| `IBG_VER` | `V12R02B30D06_260304` | `V12R02B60D00_260924` | **changed** |
| `APP_VER` | `V12R00B07D04_260205` | `V12R00B16D00_260825` | **changed** |
| `AWS_VER` | `V12R00B06D04_260304` | `V12R00B15D00_260918` | **changed** |
| `SL_VER` | `V12R02B07D81` | `V12R02B12D00` | **changed** |
| `BMS_VER` | `['V11R50B03D00']` | `['V11R50B07D00']` | **changed** |
| `DCDC_VER` | `['V12R02B07D01']` | `['V12R02B10D00']` | **changed** |
| `INV_VER` | `['V12R02B09D03']` | `['V12R02B15D00']` | **changed** |
| `FPGA_VER` | `['V12R01B00D00']` | `['V12R01B00D00']` | unchanged |
| `TH_VER` | `['V11R02B01D00']` | `['V11R02B01D00']` | unchanged |
| `BL_VER` | `['V11R06B00D00']` | `['V11R06B00D00']` | unchanged |
| `METER_VER` | `V12R00B11D00` | `V12R00B11D00` | unchanged |
| `SyHdVersion` | `102` | `102` | unchanged |
| `deviceType` | `0` | `0` | unchanged |
| `FHP_NUM` | `1` | `1` | unchanged |
| `threePhasePvPower` | `0` | `0` | unchanged |

**Seven of eleven component versions moved; four did not.** An OTA is not monolithic — the
FPGA, thermal, bootloader and meter firmware stayed put while the controller, app, cloud
agent, BMS, DC-DC and inverter all advanced.

**`SyHdVersion` and `deviceType` did not move**, which is consistent with them identifying
hardware rather than firmware. Two readings on one device; not proof.

### Version string shape (inferred)

`V{major}R{revision}B{build}D{patch}` with an optional `_{YYMMDD}` build date:

- `V12R02B30D06_260304` → 2026-03-04; `V12R02B60D00_260924` → 2026-09-24.
- The date suffix appears only on `IBG_VER`, `APP_VER` and `AWS_VER` — the component
  versions carry none.
- Each component dates independently: at the earlier reading `APP_VER` was `_260205`
  while `IBG_VER` and `AWS_VER` were `_260304`.

**Inferred from eight strings on one device.** The `D` field is read as a patch number
because `D81` → `D00` alongside a build increase (`B07` → `B12`) resembles a reset, but
nothing confirms the letters' meaning.

## 3. Key-set changes — two commands, both confirmed

### `1102` login manifest: 23 keys → 27 keys

**Added** (all per-unit lists, all reading a single element on this one-aPower site):

```
PE_HW_VER [2]   BMS_MAIN_HW_VER [0]   BMS_BL_HW_VER [0]   BMS_TH_HW_VER [0]
```

**Removed: none.** The change is purely additive.

`PE_HW_VER` reading `[2]` is interesting but not established: `apower_models[2]` in
`franklinwh-cloud`'s catalogue is `APR-05K13V1-AU`, "aPower X-01-AU", which fits an AU
site. That `PE_HW_VER` *indexes that table* is **inferred** — aGate codes run 100–104 and
aPower codes 0–7, two separate spaces, and a hardware-revision field that happened to read
2 would look identical.

### `1701`/`1702` install profile: `gridImportLimit` absent → present

**Earlier, 21 keys**, no `gridImportLimit`, across four replies:

```
airSwitchCur  electricSupply  electricSys  fhpRatePower  genRatePower
gridExportEnable  gridHardLimit  gridPhaseConSet  gridPhaseSeqSet  gridSoftLimit
isPcsDischgEn  isThreePhaseInstall  kwRatePower  ratedGridHz  ratedGridVolt
solarInstallState  solarInvManu  solarInvRatePower  opt  result  reason
```

**Later:** `gridImportLimit` present, reading `-1`. **Partial evidence** — that is a single
field reported by the Direct Connect Bridge session from a raw read on 2026-10-24, not a
full `1702` of my own. **The rest of the later key set is unknown.**

---

## 4. What this document cannot tell you

**The comparison is complete for `1102` only.** Both sides exist for exactly one command.

| | Earlier firmware | Later firmware |
|---|---|---|
| `1102` | full | full |
| `1702` | full (21 keys) | one key, third-party |
| the other 30 cmdTypes | full | **nothing** |

The capture holds 32 cmdTypes: `1101/1102`, `1109/1110`, `1111/1112`, `1113/1114`,
`1117/1118`, `1119/1120`, `1301/1302`, `1409/1410`, `1411/1412`, `1701/1702`, `1723/1724`,
`1725/1726`, `1727/1728`, `1829/1830`, `1901/1902`, `1903/1904`. **For every one of those
except `1102` there is no later-firmware reading at all**, so this document cannot say
whether they changed. Absence of a reported change is not evidence of no change.

Also absent from both sides: `1105/1106 device_check`, `1709/1710 relay_status`,
`1831/1832 battery_modules`, `1303/1304 energy_history`, `1407/1408 tou_schedule`,
`1707/1708 ibg_run_status`. Never exercised by the recorded app session.

## 5. What would complete it

One read-only session on the current firmware, capturing the same 32 cmdTypes the earlier
capture holds, would turn a one-command comparison into a real map. It needs the owner's
go-ahead and the aGate roll call, and it is a read throughout — no `opt:1` anywhere.

Until then the honest summary is: **the protocol version moved, four keys were added to
the login manifest, one key was added to the install profile, and seven of eleven component
firmwares advanced. Everything else is unobserved.**

---

*Evidence: a packet capture of the official app against the reference aGate
(`V12R02B30D06_260304`), and an owner-approved read-only login on 2026-10-31
(`V12R02B60D00_260924`). No serials, no site identifiers. The capture became readable only
after the pcap decoder was fixed — before that it decoded 12 frames of 335 and reported
success, so any earlier conclusion drawn from it is suspect.*
