# Live test: 1101 -> 1102 login manifest field shapes

**Date/time:** 2026-10-31, ~14:04 NZDT
**Gateway:** the reference aGate, `<AGATE_IP>` on the owner's LAN (serial withheld)
**Firmware:** `IBG_VER V12R02B60D00_260924`, `protocolVer V1.12.02`
**Approval:** the owner, in this session ("yes do read only login"); he also directed the
subnet scan used to locate the gateway.
**Operator:** this session (fwh-local). Read only.

## What was commanded

One `1101` request, the library's unmodified `LOGIN_DATA_AREA`:

```json
{"opt": 0, "minProtocolVer": "V1.00.00"}
```

Issued as `franklinwh-direct-connect --host <AGATE_IP> --wire-log <path>
--wire-log-redact firmware --json`. **One request, one reply, then disconnect.** No
`opt:1`, no second cmdType, nothing on `:502`.

## Roll call (owner's exclusive-access protocol, 2026-10-30)

Both asked before the read; both answered, so nothing rested on silence.

| Session | State | Scheduled | Jobs/windows |
|---|---|---|---|
| fwh-direct-connect-bridge | not connected on any port; no bridge process running | none vs the aGate | none; hourly GitHub check only |
| fwh-modbus-bridge | live Docker bridge stopped 9 days; test bridge has an empty host; demo points at mocks | none | none on this Mac |

**Unverified condition, recorded rather than resolved:** the owner's HA Live instance may
run the add-on and poll `:9000`. **Neither bridge session can see it.** Accepted for a
read-only login; would not be acceptable for a write.

Also observed: Docker on this Mac holds ten `CLOSED` sockets to the gateway's `:502` --
residue of a stopped container, consistent with the Modbus Bridge session's report. No
live traffic.

## Read-back

`opt: 0`, **`result: 0`, `reason: 0`**. 27 keys.

**Lists (13)** -- each with **exactly one element** on this single-aPower site:
`FHP_SN`, `PE_SN`, `BMS_SN`, `FPGA_VER`, `DCDC_VER`, `INV_VER`, `BMS_VER`, `BL_VER`,
`TH_VER`, `PE_HW_VER`, `BMS_MAIN_HW_VER`, `BMS_BL_HW_VER`, `BMS_TH_HW_VER`

**Scalars (14):** `IBG_SN`, `IBG_VER`, `APP_VER`, `AWS_VER`, `SL_VER`, `METER_VER`,
`protocolVer`, `FHP_NUM` (= 1), `SyHdVersion` (= 102), `deviceType` (= 0),
`threePhasePvPower` (= 0), `opt`, `result`, `reason`

**Absent:** `SUNSPEC_FW`. **Beyond `client.FIRMWARE_FIELDS`:** `deviceType`,
`threePhasePvPower`, `PE_HW_VER`, `BMS_MAIN_HW_VER`, `BMS_BL_HW_VER`, `BMS_TH_HW_VER`.

## Restore

None required -- read only, nothing changed. Verified off the device afterwards by
**counting sockets rather than trusting that the command exited**: `lsof -nP -iTCP`
showed no connection from this machine to the gateway on `:9000`, and no CLI process of
this library running. This library has no poller and no scheduler, so nothing can
reconnect by itself.

## What this establishes, and what it does NOT

**Establishes:** those 13 fields are lists and those 14 are scalars, on this site, this
firmware, one reading. `SUNSPEC_FW` is not a key. The login request as this library sends
it is accepted cleanly.

**Does NOT establish: that the lists carry one entry per aPower.** `FHP_NUM` is 1 and
every list has one element, which is equally consistent with "always a list of one". The
multi-aPower manifest remains unobserved. Nothing may model N entries for N aPowers on
this evidence.

**Appeared to contradict a relayed claim; the contradiction resolved, and my own framing
of it was wrong.** The Emulator session had reported, citing the Direct Connect Bridge's
stored sweep, that this reply carries `result: 1, reason: -2`. I reported my read as
"same firmware, **same request**, different result". **The "same request" part was
incorrect.**

The Bridge session then explained its record (its `validate_known.py`, frame at
2026-10-20T20:10:50Z): it logged in normally first -- that successful reply was not
stored -- and then sent a **raw second 1101 as just `{opt: 0}`, with `minProtocolVer`
omitted**, on the same connection. That is the frame that answered `result: 1,
reason: -2`, still returning a manifest.

So the two readings do not conflict at all; they are different requests:

| 1101 request | Result |
|---|---|
| `{opt: 0, minProtocolVer: "V1.00.00"}`, first on the connection | `result: 0, reason: 0` (this read, 2026-10-31) |
| `{opt: 0}`, no `minProtocolVer`, second login on one session | `result: 1, reason: -2` (Bridge record, 2026-10-20) |

**This revives a lead I had retired too quickly.** I had hypothesised that `-2` means
"request shape not as expected, served anyway", from the catalogue's 1103 (request
omitting `devNum`) and 1123. On seeing `result: 0` I withdrew it. The Bridge's
clarification supports the original lead rather than retiring it: a 1101 missing a field
behaves exactly like a 1103 missing `devNum`.

**Still not established:** whether the missing `minProtocolVer` or the repeat login on one
session is what triggers it. Settling that needs two more deliberate requests, which were
not part of this approved read and were not attempted.

**Still correct, and acted on:** the Emulator session had merged a change making its V12
profile answer `result: 1` to a *normal* login. That would have made the emulator disagree
with the hardware in the dangerous direction -- a client checking `result` would fail on
the emulator and pass on the device. It has reverted that (its #94/PR #95, merged
2c13e71); every profile now answers `0/0`, citing this read.

## Capture

Wire log taken with `--wire-log-redact`: serials appear only as `<redacted:N>` markers
with container shapes intact, which is what lets a redacted log answer a shape question.
Held in this session's scratchpad, outside the repository, not committed. No unredacted
capture was retained.
