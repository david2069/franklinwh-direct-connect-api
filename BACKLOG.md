# Backlog / Defect Queue

Tracked defects and planned work for `franklinwh-local`. Newest first.
Status: `queued` → `planned` → `in-progress` → `done`.

---

## EPIC-NETWORK-DIAGNOSTICS — replicate the Cloud API's network config + troubleshooting tooling, locally

**Status:** QUEUED
**Filed:** 2026-09-19
**Related:** [[INFO-VOIDSTARR-XREF]] · surfaces in `franklinwh-local-bridge` (Health tab)

The Cloud API repo (`franklinwh-cloud`) has a substantial **network diagnostics /
troubleshooting** layer we should mirror on the local (Direct Connect) side — primarily
for **troubleshooting**, secondarily for config/setup. The local transport works
without the cloud, so a local troubleshooting suite is exactly what someone with a
flaky gateway or a fresh install needs.

### What the Cloud side has (to mirror — read its docs, don't reinvent)
* Methods: `get_connection_status`, `get_network_info`, `get_network_state`,
  `get_network_switches`, `get_wifi_config`, `scan_wifi_networks` / `_poll` / `_ranked`.
* CLI: `network`, `diagnostic` subcommands.
* Docs: `docs/TROUBLESHOOTING.md` (login/auth · **network connectivity test** with
  single / continuous / JSON modes · "config looks wrong" triage via verbose discover,
  raw-vs-parsed compare, and a **redacted system snapshot** + snapshot diff),
  `NETWORK_CONNECTIVITY_DESIGN.md`, `NETWORK_PROBE_TEST_PLAN.md`.

### What we already have locally (the raw reads)
`network_interfaces` (317), `network_switches` (341), `wifi_config` (337),
`connectivity` (339, AWS/internet reachability), `wifi_scan` (335). These are the
inputs; what's missing is the **analysis + troubleshooting** layer on top.

### What to build
1. **Connectivity test + monitor** — a `diagnose`/`connectivity` command wrapping 339
   (+ `:9000` login reachability, `:502` Modbus listener) with single-shot, JSON, and
   continuous-monitoring (every Ns) modes; interpret results into pass/warn/fail with
   suggested fixes, mirroring TROUBLESHOOTING.md §2.
2. **Ranked / repeated Wi-Fi scan** — a local `scan_wifi_networks_ranked` equivalent
   over 335 (aggregate several scans, rank by signal/stability) for siting/setup.
3. **Network-state summary** — combine 317/341/337/339 into one readable report
   (interfaces, active link, SSID, DHCP, cloud reachability).
4. **Redacted system snapshot + diff** — a full local read dump with serials/SSIDs/IPs
   redacted, plus a snapshot-compare for "config appears wrong" triage (TROUBLESHOOTING
   §3). Reuse the existing redaction discipline (never emit real serials/creds).
5. **Bridge surfacing** — extend the bridge's **Health** tab (which already probes
   `:9000`/`:502`/login/poller) into a Diagnostics view: network summary, connectivity
   monitor, Wi-Fi scan, and a one-click redacted snapshot for support.

### Not applicable
The Cloud troubleshooting guide's §1 (login/auth) is a cloud-account concern — the local
path has no account, only the obfuscated handshake, so skip it.

---

## PRIVACY-HISTORY-SCRUB — purge real device serials from git history + pcaps (pre-public)

**Status:** QUEUED — only needed if this repo is ever made public
**Filed:** 2026-09-19
**Related:** [[INFO-VOIDSTARR-XREF]]

The working tree and every built sdist/wheel are now clean: the reference serials
were swapped for `FAKEGATE…` / `FAKEAPOWER…` fixtures (commit 7241f9c, verified by
rebuilding the artifacts). But two places still hold the **real** reference serials (the aGate `IBG_SN` and the aPower
`FHP_SN` — the actual values are deliberately not repeated here):

1. **Git history** — every pre-scrub commit (text form, trivially greppable).
2. **Old capture blobs in history** — the bundled pcaps were REMOVED from the tree
   (2026-09-20); they survive only in history, where the serial lives in the
   sendMqtt frames' *obfuscated* payload, so it is NOT plain-text greppable and a naive
   `filter-repo --replace-text` (or `--blob-callback` byte swap) misses it. These pcaps
   are NOT shipped in the artifacts, so they are not a PyPI leak — only a public-repo one.

### Why it is deferred
The repo is private and staying private; the serial is device-identifying, not a
credential. None of this is a live leak while private. (The same serial is also in the
already-public `franklinwh-cloud` history — out of scope here.)

### What a proper scrub needs (if going public)
- Decrypt → replace serial → re-encrypt each affected pcap frame (recompute the CRC-32
  envelope) so the captures decode to the fake serial — OR regenerate the fixtures from the
  emulator and drop the real captures.
- `git filter-repo` to rewrite history: `--replace-text` for the plain-text commits, plus
  swapping the pcap blobs for the regenerated ones.
- Force-push; note GitHub may retain old objects reachable by direct SHA-URL (ask Support to
  purge). Back up with a bundle first.

---

## INFO-VOIDSTARR-XREF — cross-reference vs voidstarr/franklinwh_local (independent local-protocol lib)

**Status:** INFO — records what an independent reverse-engineering of the same protocol
gave us; two follow-up leads remain
**Filed:** 2026-09-19
**Related:** [[PRIVACY-HISTORY-SCRUB]]

[`voidstarr/franklinwh_local`](https://github.com/voidstarr/franklinwh_local) (MIT) is an
independent (not a fork) implementation of the same local Direct-Connect protocol, reverse-
engineered from the app's **Dart AOT** (via `blutter`) rather than from captures. It is
transport + a command table only — no battery-cell decode, energy history, emulator,
discovery or bridge (we are far ahead on data). What it gave us:

### ✅ DONE — general seed formula (commit c6fc615)
Our `seed_for_equip()` hardcoded `0x3F`, correct only for serials that hash to it (i.e. only
our own). voidstarr recovered the real per-serial formula
`(sum(utf8(SN)) + len(SN) + 29) & 0xFF`, which reproduces BOTH seeds we had only *observed*
(`00000000`→`0xA5`, our serial→`0x3F`). Adopted as `protocol.derive_seed()` — fixes the send
path for any other gateway (beta testers) and makes the emulator wire-faithful. Our second
data point corroborated a formula voidstarr could only fit to one. Credited (MIT).

### ✅ RESOLVED — `optType` is NOT a wire key (do not "fix")
voidstarr's `CmdSpec` carries an `optType`/`opt_type` field for several commands (1701, 1203,
1205, 1117). It is an **internal Dart enum field, not something the app puts on the wire** —
our captures show `optType` **zero times**, and the real 1701 write uses plain `"opt": 0`.
Our requests already match the captured ground truth. Adding `optType` would corrupt working
writes. **No change — verified against the (now-archived) reference captures.**

### ▢ LEAD — cross-check our catalog against the authoritative Dart enum
voidstarr's `commands.py` is the full 44-entry `CommunicationCmd` enum with
`index/name/req_code/resp_id`. Worth a one-pass diff against our `catalog.py` to validate
names/coverage and catch any cmdType we mislabel. Low priority (our catalog is capture- and
cloud-doc-grounded and richer on semantics).

### ▢ LEAD — the `blutter` Dart-AOT decompilation methodology
They lifted the enum + seed math straight from the app binary. If we hit a command whose
payload shape we can only guess (e.g. the UNCONFIRMED 1823 aPower-power write), decompiling
`com.Franklinwh.FamilyEnergy` with `blutter` could settle it **without** an on-site capture.

---

## DEF-EXPORT-LIMIT-ENFORCEMENT — no plane enforces a site-wide power limit

**Status:** OPEN — the central enforcement question is **untested** (the 2026-09-13 attempt
was confounded)
**Filed:** 2026-09-13
**Related:** [[INFO-POWER-PLANE-LOCAL]], [[INFO-EXPORT-CONTROL]], [[EPIC-LOCAL-ORCHESTRATION]]

### The architecture
Per the owner, **Modbus is a standalone local API — no interaction with the Cloud API or the
local sendMqtt API.** So the site has **three independent control planes**:

| plane | transport | carries a discharge/export limit? |
|---|---|---|
| Cloud | REST `setPowerControl` | ✅ `globalGridDischargeMax`, `gridFeedMax` |
| Local sendMqtt | TCP/9000 | ❌ no field carries it (verified by sweep + sync test) |
| Modbus | TCP/502 | ❌ `/api/battery/limits` = `5000/5000`, `source: "default"` |

A limit set in one plane is invisible to the other two. Whether it is *enforced* against
commands from another plane is the open question.

### Why it matters
This site can physically exceed its **10 kW Ausgrid export limit**: ~5.7 kW observed solar +
5 kW battery = 10.7 kW. Today they never coincide only because the control strategy
separates them in time — solar charges by day, battery exports after dark. That separation
is a *scheduling* property, not a hardware limit. A daylight export block would coincide
them.

### What is established
- Local and Modbus planes **cannot see** the cloud limit (sweep, sync test, `/api/battery/limits`).
- `notControlExportSolar: true` — **solar export is uncontrolled**, so `gridFeedMax` does not
  cap it (this is why the aGate exports regardless).
- Peak export observed in 30 days: 5,313 W — never near 10 kW.

### What is NOT established
**Whether the device enforces the cloud's `globalGridDischargeMax` against a
Modbus-commanded discharge.** The 2026-09-13 test was invalidated by an accidental reset to
5.0 kW at an unknown time; 4,955 W observed is equally consistent with "3 kW ignored" and
"5 kW enforced".

### How to test it properly
1. Set `globalGridDischargeMax` to **2.0 kW** — well clear of the 5 kW hardware rating, so
   enforcement and non-enforcement predict clearly different peaks.
2. **Verify via `schema --live` immediately before** the Modbus export window, and again
   **immediately after** — the confound was an unverified value, not a bad idea.
3. Let the Modbus schedule fire (18:00) and read the bridge's 30-second record.
4. ~2,000 W ⇒ enforced across planes. ~5,000 W ⇒ not enforced; the cloud limit is advisory
   to anything but cloud dispatch.

### Consequence either way
If **not enforced**, local/Modbus orchestration must own power limiting itself — there is no
device-side backstop — and that is a hard requirement on
[[EPIC-LOCAL-ORCHESTRATION]], not a nice-to-have. If **enforced**, the cloud limit becomes a
usable safety rail that local tooling should read (via the cloud) and respect.

---

## FEAT-CLI-CLOUD-PARITY — match the Cloud CLI's commands AND output

**Status:** queued — **extends [[EPIC-CLI-ALIGN]]**, still blocked on its (a)/(b) decision
**Filed:** 2026-09-13

Owner has reconfirmed the intent: the local CLI should offer near-identical options and
output to `franklinwh-cli`, so muscle memory and scripts transfer.

### Where we now stand against the cloud CLI

| cloud command | local | note |
|---|---|---|
| `bms` | ✅ `battery` / `bms` | shipped 0.3.0; cloud-only rows omitted (§3e) |
| `tou` | ✅ `tou` | tariff only — dispatch is cloud-owned |
| `mode` | ✅ `mode` | incl. `--set` |
| `discover` | ✅ `scan` | `discover` alias still to add |
| `raw` | ✅ `call` | `raw` alias still to add |
| `schema` | ~ `catalog --json` | not the same shape |
| **`status`** | ❌ | quick one-screen summary — the most-missed |
| **`metrics`** | ~ `energy_rollup` | different shape/flags |
| **`monitor`** | ~ `--watch` | reconcile into one verb |
| **`sc`** | ❌ | smart circuits (1409/1411 exist) |
| **`accessories`** | ❌ | V2L/generator (1411 `CarSW*`, 1901) |
| **`diag`** | ~ `health` | narrower than the cloud's |
| `support` / `fetch` | ❌ | account/portal — likely out of scope |

### Output, not just commands
The cloud CLI uses formatted sections (`print_section`/`print_kv`, emoji headers, aligned
values); local is plainer apart from the new `battery` view. Adopt one shared style and put
`--json` on **every** command. `battery` is the reference for how this should look.

**Still blocked on the same decision:** whether the local surface becomes the cloud's
noun-per-domain shape (recommended: **(b)**) or a generated verb surface (a). Adding
`status`/`sc`/`accessories` before that is choosing (b) by default, so decide first.

---

## INFO-EXPORT-CONTROL — nothing in this stack limits SOLAR export; that is why it exports regardless

**Status:** explained (2026-09-12) — architectural, no local defect
**Related:** [[INFO-POWER-PLANE-LOCAL]], [[EPIC-LOCAL-ORCHESTRATION]]

Official-app screenshot ("Grid Import & Export") mapped against
`get_power_control_settings` (franklinwh-cloud `docs/CLI_SCHEMA_COMMAND.md`,
`mixins/power.py`):

| app control | cloud field | this site |
|---|---|---|
| Max allowable total **charge** rate of the aPower(s) | `globalGridChargeMax` | `No Limit` (-1) |
| **aPower Export to Grid (Net Export)** toggle | `globalGridDischargeMax` **= 0 or not** | ON |
| Max allowable total **discharge** rate of the aPower(s) | `globalGridDischargeMax` (kW) | 5.0 kW |

The toggle and the discharge field are the **same** cloud field. `set_power_control_settings`
documents the encoding: `-1` unlimited, **`0` = "Solar only (and no battery) export"**,
`>0` = kW cap. So switching "Net Export" off sets it to 0.

### Why the aGate exports anyway
**`globalGridDischargeMax = 0` only stops BATTERY export — solar keeps exporting.** And the
one field that would cap total feed-in, `gridFeedMax`, is reported alongside
**`notControlExportSolar: true`**, which franklinwh-cloud documents as *"solar export is
unmetered/uncontrolled"*.

So on this configuration **no setting in the stack limits solar export**. That matches the
owner's observation exactly: the unit exports regardless of the export controls.

### Hypothesis for the US/AU difference (unproven, but evidenced)
`get_power_control_settings` also returns US programme flags — `isNem3`, `isCalifornia`,
`sgipFlag`, `itcFlag`. On this AU site `isNem3 = 0` and `isCalifornia = 0`. The owner
reports export limiting works on US units and is sometimes absent where the PTO prohibits
export. A plausible reading is that the export-enforcement path is **gated on those
programme flags**, so an AU site with both at 0 never engages it. Evidenced by the flags'
existence and values; not proven.

### ✅ Sync test run (2026-09-12): the cap does NOT reach the local channel

Owner set **`globalGridDischargeMax` 5.0 → 3.0 kW** in the official app; local `1701` and
`1903` were read immediately before and after.

**No setting field moved.** The only deltas were `1903 solarPower` (11700 → 51280) and
`solarPowerGen` (79 → 92) — live/cumulative solar counters that advance on their own, not
configuration. No local field anywhere carries `3`, `30` or `3000`.

`1407 tou_schedule` was also unchanged, still the same five tariff blocks
(00:00/00:30/02:00/04:00/23:00, flags [2,1,0,1,2]) — consistent with 1407 carrying tariff
tiers only, never dispatch or per-block power ([[DEF-LOCAL-TOU-DISPATCH]]).

So unlike reserved SoC — where the local `1726` cache **does** follow a cloud change within
~8 s — the grid power-control limits have **no local representation at all**. Confirms the
REST-only reading below, by experiment rather than inference.

### ⚠️ The cap may apply only during scheduled grid export
When the value was changed, the app asked whether to also change the **TOU schedule**,
saying the new limit takes effect for *scheduled grid export*. That points at the per-block
`gridDischargeMax` in `tou_json_schema` rather than a global clamp — i.e. the 3.0 kW may bind
**only inside a `Grid Export (7)` block**, which on this site is 19:00–20:00.

This sharpens the observation test: check the evening in windows, not as one lump.

| window | expectation if the cap is per-block |
|---|---|
| 19:00–20:00 (`Grid Export (7)`) | discharge clips at ~3,000 W |
| rest of the evening | unclamped, up to ~5,000 W |

If discharge clips at 3 kW **across the whole evening**, it is a global clamp instead. If it
never exceeds 3 kW anywhere, that is also consistent with a global clamp; the discriminator
is whether 3–5 kW discharge still appears outside 19:00–20:00.

### These are REST-only — there is no local cmdType
The doc labels the whole section `get_power_control_settings` **(REST)**. The power-control
limits are **not** `sendMqtt`, so they are cloud-only *by architecture*, not merely
undiscovered locally. `1701` (`kwRatePower`, `gridSoftLimit`, `gridHardLimit`) and
`1903` (`grid_feed_max`) are separate **device-level** fields that resemble them.

### Correction: the 5 kW discharge ceiling may be configured, not physical
[[INFO-POWER-PLANE-LOCAL]] attributes the observed 4,999 W discharge ceiling to the
aPower's 5 kW inverter rating. The app shows a configured **`globalGridDischargeMax` =
5.0 kW**. Both are 5 kW, so the telemetry **cannot distinguish them** — the ceiling may be
the configured cap rather than the hardware limit. Testable: set it to 3.0 kW in the app and
see whether discharge clips at 3 kW.

If it is the configured cap, then raising it toward the aPower rating while solar is strong
is precisely the path to the >10 kW export described in [[INFO-POWER-PLANE-LOCAL]].

### ✅ Confirmed: the app control IS `globalGridDischargeMax` (2026-09-12)
After the owner set 3.0 kW in the app, `franklinwh-cli schema --live --filter grid` reports:

```
globalGridChargeMax       Unlimited (-1)
globalGridDischargeMax    3.0 kW        <- the app's "Max allowable total discharge rate"
gridFeedMax               10.0 kW
notControlExportSolar     True
gridFeedMaxFlag / gridMaxFlag   2
sgipFlag 1 · itcFlag 0 · isNem3 0 · isCalifornia 0
```

**The earlier app-vs-cloud "mismatch" is explained.** The app showed `5.0` while the cloud
reported `-1`. Most likely the **app displays the EFFECTIVE cap** — bounded by the aPower's
5 kW rating — while the cloud stores the **raw setting** (`-1` = unlimited). Not a conflict,
and it was correctly not called one at the time.

### Visibility: the cap is cloud-only, confirmed across four channels

| channel | discharge limit reported |
|---|---|
| cloud `get_power_control_settings` | **3.0 kW** ✅ the real setting |
| local sendMqtt (`1701`/`1903`) | absent entirely |
| Modbus Bridge `/api/battery/limits` | `5000 W`, `source: "default"` (its own default, not the device) |
| FWHAI gateway summary | `capacity.max_discharge_kw: 5.0` — the aPower **rating**, not the cap |

Note the FWHAI figure sits under `capacity` beside `total: 13.6` / `available: 13.46`, so it
is the hardware capability. That is evidence the observed 4,999 W ceiling was the **5 kW
rating**, weakening the earlier suggestion that it might have been a configured cap.

**Consequence for [[EPIC-LOCAL-ORCHESTRATION]]:** a local-only integration cannot see this
limit, and the Modbus Bridge would dispatch up to 5,000 W believing that is the ceiling.

### ⚠️ CONFOUND FOUND: the evening export is driven by the MODBUS BRIDGE, not a cloud TOU dispatch

The Modbus Bridge (`:8100`) has an enabled schedule **"Battery Bonus TOU Export"**:

```
trigger      daily @ 18:00        duration 5400 s (90 min)  ->  18:00–19:30
action       force_discharge      params {power_pct: 100}
release      release              conflict defer
entry cond   soc 50–100 AND grid.connected AND tariff.bonus_window_active
```

So the evening export is a **Modbus-initiated force discharge at 100 % power**, *not* the
cloud's `Grid Export (7)` TOU block (19:00–20:00). The two even **overlap** 19:00–19:30,
with both systems commanding export.

### This explains two things that were previously puzzling

**1. The near-constant ~7.2 kWh "peak" export bucket.** [[DEF-1303-TIER-BASIS]] recorded
`kwh_uti_out` in the `peak` tier as suspiciously stable (6.9, 7.07, 7.17, 7.25, 7.26 kWh)
regardless of solar. That is simply **5 kW × 1.5 h = 7.5 kWh** — a fixed-duration scheduled
discharge, minus house load. Not a tariff artefact at all.

**2. The 18:00 tier boundary.** Window-fitting put `flat→peak` at 15:45–18:00, with two days
landing on 18:00:33 and 18:00:57. That is this schedule firing at **18:00**. The export
starts there because the *schedule* starts there.

This does not settle what drives the device's tier *attribution* — and with TOU mode
inactive, the cloud's wave types cannot be driving it either. Checked: mapping the cloud
blocks onto the observed split fails (19:00–19:30 of the export would fall in Off-Peak and
should show ~2.5 kWh in `valley`, but `valley` reads ~0.003 kWh). So `1407` does not explain
it, the cloud blocks do not explain it, and the accounting basis remains **open**. What the
schedule does remove is the anomaly — the near-constant `peak` total — that made any fixed
schedule look implausible.

### ⛔ The cloud TOU blocks are CONFIGURED BUT NOT IN EFFECT

**FranklinWH TOU schedules only apply when the operating mode is TOU.** This site runs
**Self-Consumption** (`85232`, `workMode 2`), so the cloud TOU blocks — including
`Grid Export (7)` at 19:00–20:00 — are **inert**. The owner found the native scheduler too
inflexible and wrote their own in the Modbus Bridge instead.

**Correction:** an earlier note here said the export window was "19:00–20:00, confirmed
from the device's own view rather than inferred". That was **wrong in implication**. FWHAI's
`tou_active`/`tou_next` report the *configured* schedule; they do not mean it is running.
Mode-gating has to be checked before reading them as live behaviour.

This also reframes [[DEF-LOCAL-TOU-DISPATCH]] and [[EPIC-LOCAL-ORCHESTRATION]]: the cloud's
per-block dispatch layer is not merely cloud-only, it is **unavailable in any mode but TOU**.
For a site that wants Self-Consumption *plus* scheduled export, the native scheduler cannot
express it at all — which is precisely why an external scheduler exists here. That is a
stronger argument for the epic than "the local API lacks a scheduling layer".

### Tonight's observation
The export actually observed will be the Modbus schedule's **18:00–19:30** force discharge.

**That makes tonight a sharper test, of a different question.** The schedule requests
`power_pct: 100`, and the Modbus Bridge converts that using its own 5,000 W default — so it
will ask for ~5 kW. The question becomes: **does the cloud's 3.0 kW
`globalGridDischargeMax` clamp a Modbus-initiated force discharge?**

### ⛔ ANSWERED (2026-09-13): the cloud cap does NOT govern a Modbus-commanded discharge

The Modbus schedule fired at **18:00:13** today (the owner confirmed the earlier no-show was
a container-timezone problem). With `globalGridDischargeMax` set to **3.0 kW** in the app,
measured from the bridge's own 30-second record:

| | 11/09 (cap 5.0 kW) | 13/09 (cap **3.0 kW**) |
|---|---|---|
| peak discharge | 4,990 W | **4,955 W** |
| peak export | 4,783 W | 4,721 W |

Sustained ~4,950 W for the whole window — **no clipping whatsoever**. Minute by minute from
18:00 it holds 4,890–4,951 W while SoC falls 98.1 % → 88.9 %.

**⚠️ CONCLUSION RETRACTED — the test is confounded.** The owner reports accidentally
resetting the app back to **5.0 kW**, and a check at ~18:20 confirms it now reads 5.0 kW.
The reset time is unknown, so the cap during the 18:00–18:14 window is not established.

The two hypotheses are **indistinguishable from this data**:

| scenario | predicted peak |
|---|---|
| cap 3.0 kW, ignored by Modbus | ~5,000 W (the aPower rating) |
| cap 5.0 kW, correctly enforced | ~5,000 W |

Observed 4,955 W fits both. **The test needs re-running** with the cap confirmed at 3.0 kW
immediately before the window and re-checked immediately after — ideally with a value well
clear of the hardware rating (e.g. **2.0 kW**) so enforcement and non-enforcement predict
visibly different numbers.

What **is** established regardless of the reset: neither the local sendMqtt plane nor the
Modbus plane reports that the limit exists at all — `/api/battery/limits` answers
`5000/5000` with `source: "default"`, and no local cmdType carries it. See
[[DEF-EXPORT-LIMIT-ENFORCEMENT]] for the enforcement question, which is the part that
matters and is still open.

### ⚠️ Correction: `electricSupply` is NOT the service rating in amps
An earlier entry decoded `1701 electricSupply = 63` as the service amps, from the owner's
"65 amp" remark. **Probably wrong.** FWHAI reports `service_amps: 100`, which matches
`1701 airSwitchCur = 100`, not `electricSupply`. And `63` is `0b111111`, which looks more
like a capability bitfield than an ampere value. Treat `electricSupply` as **undecoded**.

---

## EPIC-LOCAL-ORCHESTRATION — what charge/discharge control is actually possible locally?

**Status:** planned — research + documentation. **Phase 1 is safe; Phase 2 is mutating.**
**Filed:** 2026-09-12
**Related:** [[DEF-LOCAL-TOU-DISPATCH]], [[INFO-POWER-PLANE-LOCAL]],
[[DEF-RESERVED-SOC-RESEARCH]], [[FEAT-CMDTYPE-RECONCILE]], [[XREF-BRIDGE-DEFECTS]]

### Goal
The cloud orchestrates charge/discharge by attaching per-block attributes to TOU blocks —
`dispatchId`, `maxChargeSoc`, `minDischargeSoc`, `gridChargeMax`, `gridDischargeMax`,
`chargePower`/`dischargePower`, `gridFeedMax`, `solarCutoff`, `rampTime` and more. Most of
those correspond to **global** settings the local channel already exposes
(see CLOUD_MAPPING §3d). So the open question is not "can the device do it" but:

> **Which of those globals can actually be WRITTEN locally, and what orchestration can a
> local-only bridge build by scheduling those writes itself?**

Produce a capability matrix and document it for both the library and the bridge.

### Working hypothesis
The local channel has **no scheduling layer**, but may have most of the **actuators**. If
so, a bridge can emulate cloud TOU dispatch locally by running its own scheduler and
issuing local writes at block boundaries — mode switch + global setting changes — rather
than uploading a schedule. Whether that is viable turns entirely on which writes take.

### What is already known

**Writes confirmed working locally** (`catalog.WRITES`): `set_mode` (1727 opt=3),
`set_offgrid` (1723), `set_smart_circuit` (1409), `set_der_comms` (1205), `reboot` (1721).

**Confirmed NOT writable:** reserved SoC (1405/1725/1727 — ACKed, echoed, discarded).

**Unknown — the gap this epic closes:** `1701` `kwRatePower` / `gridSoftLimit` /
`gridHardLimit` / `gridExportEnable` / `isPcsDischgEn`, and `1903` `grid_feed_max` /
`reSolarSoc`. These are the grid charge/discharge/export power plane. **Nobody has tried
writing them.**

### Phase 1 — correlation and read matrix (SAFE, no writes)
1. For every cloud TOU block attribute in `tou_json_schema`, identify the local field,
   cmdType, units and current value. Extend the CLOUD_MAPPING §3d table to cover all of
   them, including the ones currently marked "no identified local equivalent"
   (`chargeMax`, `chargePower`, `dischargeMax`, `dischargePower`, `gridMax`, `gcaoMax`,
   `rampTime`, `useModeFlag`, `solarPriority`, `loadPriority`).
2. Resolve the **`grid_feed_max` discrepancy** already flagged in
   [[INFO-POWER-PLANE-LOCAL]]: local `-1` vs cloud `10.0 kW`. Determine which the hardware
   enforces — this is a compliance-relevant export limit, and it is the single most
   important open item in this epic.
3. Map cloud `dispatchId` (1,2,3,6,7,8) against local mode `scheduling_type` (1/2/3) and
   `run_status`. Dispatch is per-block behaviour; mode is site-wide. Document how far they
   correspond and where they cannot.
4. Record which cloud attributes are **greyed out per dispatch code** in the app UI — the
   UI already encodes which combinations are legal, and that constrains any local emulation.

### Phase 2 — write verification (MUTATING, one field at a time)
For each candidate in `1701`/`1903`, run the established pattern — the same one that
settled reserved SoC:

1. Full-block read-modify-write, change **one** field.
2. Read back; **and check an independent witness** where one exists. (The reserve write
   read back "unchanged" from a block that reads zeros regardless — the load-bearing
   evidence was `1726`, not the block itself. Do not repeat that mistake: decide the
   witness *before* writing.)
3. Restore; verify prior state.
4. Classify: **takes** / **silently discarded** / **rejected**.

**Safety rules**
- Export/import limits affect grid compliance. Change to a *less* permissive value first
  (e.g. cap export below current output), never more permissive.
- One field per session, restore immediately, never batch.
- Not during an outage, off-grid operation, or VPP dispatch (`run_status` 9).
- `isPcsDischgEn` and `gridExportEnable` are booleans that could stop export entirely —
  test last, and only with the owner watching.

### Phase 3 — document the orchestration surface
- **`docs/ORCHESTRATION.md`**: what a local-only integration can and cannot do — force
  charge, force discharge, cap export, hold SoC — with the cmdType and the verified
  write behind each, and an explicit list of what requires the cloud.
- Extend `catalog.WRITES` with whatever Phase 2 proves, each with its verification note.
- Bridge handoff: which primitives a local scheduler can drive, and the honest failure
  modes (a write that ACKs but is discarded must never be surfaced as success —
  [[XREF-BRIDGE-DEFECTS]] B1).

### Open questions
- Can force-charge be emulated at all locally? The cloud does it via a TOU session, not a
  cmdType. Mode switch + grid charge limit may approximate it — or may not.
- Does the device *enforce* `1701`/`1903` limits, or are they a cache the cloud overwrites
  (as with reserved SoC)? A cloud-side change plus a local re-read answers this cheaply
  and safely, and should be done in Phase 1.
- Does `useModeFlag` gate whether per-block overrides apply at all?

---

## TEST-1823-APOWER-POWER — on-site test: is 1823 the aPower power switch?

**Status:** planned — **ON-SITE ONLY, scheduled ~2026-09-26** (owner on site in two weeks)
**Filed:** 2026-09-12
**Risk:** HIGH — a successful write may shut the battery down
**Related:** [[INFO-POWER-PLANE-LOCAL]], [[DEF-LOCAL-TOU-DISPATCH]]

### Hypothesis
`1823` returns `{powerOn, powerOff}` (both 0). The cloud TOU block schema carries an
optional **`powerOffApower`**, and the FranklinWH System User Manual documents a **physical
aPower power switch** on each unit. So `1823` is plausibly the software equivalent of that
switch — with `1821 {enable}` possibly its enable flag.

### Why on-site, and why not sooner
If `powerOff` works and `powerOn` does **not** (or the unit stops answering once off), the
only recovery is the **physical switch on the aPower**. Do not attempt remotely. This is
also why it was not run during the 2026-09-11 probing session.

### Step 1 — CAPTURE FIRST (preferred; no writes at all)
The app is the safe oracle. On site, joined to Direct-Connect:

```bash
franklinwh-local proxy 192.0.2.110 --listen 0.0.0.0:9000   # decode app<->aGate live
# or: sudo tcpdump -i <iface> -s0 -w fwh.pcap 'tcp port 9000'
franklinwh-local analyze fwh.pcap --unknown
```

Then exercise any aPower power control the app offers (check both the user app and the
installer app; the HotSpot-mode app has a reduced feature set, so the control may not be
present — that itself is informative). If a frame appears, we get the exact cmdType and
payload with **zero** guessing, and Step 2 becomes unnecessary.

### Step 2 — mutating write (only if capture yields nothing, and only with the switch in reach)

**Pre-flight — abort if any fails**
- [ ] Physically at the aPower, switch located and reachable
- [ ] Grid present and stable; **not** off-grid / islanded (`offgrid` reads `offgridState=0`)
- [ ] No critical loads running; household informed the battery may stop
- [ ] SoC comfortable; not mid-VPP-dispatch (`power_flow` `run_status` != 9)
- [ ] Baseline captured: `1823`, `1821`, `power_flow`, `device_check`, `battery_modules`,
      `device_states` (`bmsState`), `relay_status`
- [ ] Note the LED strip state (manual: 5 segments) for before/after comparison

**Write** — full-block RMW, change one field only:
```
1823 {"opt":1, "powerOn":0, "powerOff":1}     # or powerOn:1/powerOff:0 — see note
```
Semantics are unknown: the pair may be *momentary commands* (write 1 to act) or *state
flags*. Prefer testing **`powerOn`** first if the unit is already on — a no-op if it is a
state flag, and harmless if momentary.

**Observe (within ~30 s)**
- `power_flow` `p_fhp` → 0 and `fhpPower` → 0?
- `device_states` `bmsState` change? `battery_cells --id 1` still answering?
- `device_check` / `battery_modules` — does the unit drop out of `devMap`?
- aPower LED strip — segments off?
- Does `1823` now read back non-zero (i.e. does it retain state)?

**Rollback**
1. Write the inverse (`powerOn:1`).
2. If unresponsive → **physical switch on the aPower**.
3. Re-verify all baseline reads match; record anything that did not return.

**Abort immediately** if the gateway stops answering, any relay state changes
unexpectedly, or the site goes off-grid.

### Expected outcomes
- **Silent discard** (like reserve) — write ACKs, nothing changes. Most likely, and
  harmless. Record and close.
- **Works** — 1823 is the aPower power switch. Catalogue it as a **DESTRUCTIVE write**,
  add to `WRITES` only behind an explicit confirm (as `reboot` is), and note that recovery
  may need physical access.
- **Partial** — e.g. powers off but `powerOn` does not restore. **Worst case**; this is the
  scenario the physical-switch precondition exists for.

Whatever happens, record it here and in `docs/PROTOCOL.md`, and update the `1823`
description from UNCONFIRMED.

---

## INFO-POWER-PLANE-LOCAL — grid power limits live in 1701/1903, not the unknown codes

**Status:** answered (2026-09-11)
**Related:** [[FEAT-CMDTYPE-RECONCILE]], [[DEF-RESERVED-SOC-RESEARCH]]

Two hypotheses were put: (a) are `1823 {powerOn,powerOff}` / `1825 {power}` the force
charge/discharge inverter power? (b) is `1405 mode_soc` showing the *last value set*, and
possibly the Self or TOU reserve?

### (a) No — and the real fields were found

Scanned all 70 catalogued reads for values matching this site's cloud-reported power
control (`globalGridChargeMax`/`globalGridDischargeMax` = -1, `gridFeedMax` = 10.0 kW). The
power plane is local, in two already-known codes:

| local | fields |
|---|---|
| `1701 install_profile` | `kwRatePower: -1`, `gridSoftLimit: -1`, `gridHardLimit: -1`, `gridExportEnable: 1`, `isPcsDischgEn: 1` |
| `1903 solar_pv` | `grid_feed_max: -1` |

These use the **-1 = unlimited** convention the cloud documents for
`globalGridChargeMax`/`globalGridDischargeMax`. `1823`/`1825` read `0` for every field and
do not follow it, so they are very unlikely to be the same thing. Also, the cloud has **no
sendMqtt code** for force power to mirror: `force_charge`/`force_discharge` build a TOU
session, and `setPowerControl` is a REST endpoint.

Both catalog descriptions updated — `1701` and `1903` previously listed only a handful of
fields and never mentioned the power limits at all.

### ✅ `grid_feed_max` discrepancy checked (2026-09-12) — probably not a conflict, and not consequential

Local `1903 grid_feed_max = -1` (unlimited) vs cloud `gridFeedMax = 10.0 kW`. Two
independent lines of evidence, neither needing a mutating write:

**1. The cloud's own flags say export control is not applied.** `get_power_control_settings`
returns `notControlExportSolar: true`, documented in franklinwh-cloud's
`CLI_SUPPORT_INFO.md` as *"solar export is unmetered/uncontrolled"*, with
`gridFeedMaxFlag: 2` ("feed-in limit mode, 2 = default"). So the cloud appears to be storing
a **configured-but-unapplied** value while the device reports the **effective** one. Read
that way the two agree, and `-1` is correct.

**2. The limit has never been approached — but it IS reachable.** Site facts (from the
owner): 6.6 kW solar, which is the aGate's max AC input across its two AC inputs; a 230 V
63 A service; and an Ausgrid **10 kW export limit** for the area/capacity. Against 30 days
of 30-second samples from the bridge store (84,923 samples, 39,423 exporting):

| | observed | rating |
|---|---|---|
| peak solar | 5,699 W | 6.6 kW nameplate |
| peak battery discharge | 4,999 W | 5 kW aPower |
| **peak grid export** | **5,313 W** | **10 kW Ausgrid limit** |
| samples exporting above 6 kW | **0** | |
| samples with solar+discharge > 10 kW | **0** | |

**Why it has never been approached:** solar and battery discharge never export at the same
time. At the peak-solar sample (2026-09-08 11:03, 5,699 W) the battery was *charging* at
4,735 W. The control strategy sends solar to battery+load and exports the remainder, then
discharges in the evening once solar is zero — so export is bounded by whichever single
source is active, not by their sum.

**⚠️ That separation is a control-strategy property, not a hardware limit.** 5.7 kW solar +
5 kW battery = **10.7 kW**, which would breach the 10 kW Ausgrid limit. Their TOU schedule
already contains a `Grid Export (7)` dispatch block (19:00–20:00, after dark). Move an
export block into daylight — or take a midday VPP dispatch — and both sources could export
together. Local `grid_feed_max = -1` gives no reason to believe the device would clip it.

**Conclusion:** a **latent** exposure, not a current one. Not urgent, but it is one
schedule change away from being real, so it should not be dismissed.

**Corrections to my own earlier framing.** First I called this *"the single most important
open item"* and compliance-relevant, having checked neither the cloud's flags nor the data.
Then, after finding peak export at 5.3 kW, I called it *"moot"* — also wrong, because I had
only compared against the 5 kW aPower rating and not considered the two sources summing.
Both overstatements came from concluding before establishing the physical envelope.

**To settle it definitively** (still unrun, needs a cloud-side change): set `gridFeedMax`
to a distinct value via the cloud, wait ~10 s, re-read local `1903`. If local follows, it is
a synced cache and the cloud is authoritative — the same test that settled
[[DEF-RESERVED-SOC-RESEARCH]]. If it stays `-1`, the two fields are independent and the
device value is the effective one.

**The question worth answering first** is not which field wins but whether **anything**
enforces 10 kW. A safe test: schedule a short daylight `Grid Export` block (or wait for a
midday VPP dispatch) with the battery charged and solar strong, and watch `p_uti` at
30-second resolution. If export clips near 10 kW, something enforces it. If it sails past,
nothing does, and the limit needs to be set somewhere that works.

### Field decodings confirmed by these site facts
- `1701 electricSupply = 63` → the **service rating in amps** (a 230 V 63 A supply).
- `1903 PV1RatedPower = 66` → **units of 100 W**, i.e. 6.6 kW, matching the owner's solar.
  `installPV1port=1` / `installPV2port=0` — only one of the aGate's two AC inputs is in use.

### New lead for 1823 from the cloud TOU schema (2026-09-12, untested)

The cloud TOU block schema accepts an optional **`powerOffApower`** field. Local
`1823` returns **`{powerOn, powerOff}`**. The naming is close enough to be worth a probe:
`1823` may be the global aPower power-on/off control the cloud schedules per TOU block.

Untested — both local values read 0, and distinguishing "ignored" from "applied" needs a
mutating write to a code of unknown purpose on a live battery. **Do not write to 1823
without an independent confirmation of what it does** (installer app capture, or the field
appearing non-zero on another site). Recorded as a lead only.

Other cloud TOU block fields with plausible local globals: `gridFeedMax` ↔ `1903
grid_feed_max` (exact name match), `offGrid` ↔ `1723 offgrid`, `heatEnable` ↔ `1801`
heat temps, `solarCutoff` ↔ `1903 reSolarSoc` (unconfirmed). See CLOUD_MAPPING §3d.

### (b) No — disproved by the mutating test

`1405` does **not** retain the last value set: the 2026-09-11 test wrote `selfMinSoc = 12`,
the reply **echoed 12**, and the read-back was `0`. Nor does it mirror the live reserves —
`selfMinSoc` reads 0 while Self reserve is 11, and `touMinSoc` reads 0 while TOU is 15.
Only `BBBackupSoc = 20` is populated, and 20 matches none of the three reserves.

The live per-mode reserve remains `1726 reserved_soc`, the only working local read.

---

## XREF-BRIDGE-DEFECTS — RESOLVED; two of the four were not defects

**Status:** ✅ closed (2026-09-12). B2/B3 fixed in the bridge; **B1/B4 were my error**.
**Filed:** 2026-09-11
**Related:** [[DEF-1303-TIER-BASIS]], [[DEF-RESERVED-SOC-RESEARCH]]

Filed from bridge screenshots. On reading the bridge source (with the owner's explicit
permission to work in that repo), **half of it was wrong** — I inferred defects from a UI
without checking the code behind it, the same over-reading that produced the
"reconnect churn" and "moving boundary" errors elsewhere in this backlog.

### B1. Reserve "Set" buttons — ❌ NOT A DEFECT
The bridge already handles this correctly. `POST /api/cloud/reserve` routes to the **cloud**
provider with the docstring *"the local API silently discards this write (reserve is
cloud-owned)"*, returning 503 when no cloud provider is configured. The local mode-set
endpoint additionally returns `not_applied_locally` plus an explanatory note. Nothing to fix.

### B2. Stale vendored wheel — ✅ REAL, FIXED
`wheels/` held `franklinwh_local_api-0.1.0` while the library had changed substantially
under the same version. Library bumped to **0.2.0**, re-vendored. Since the Device tab
renders `CmdInfo.description` verbatim, this was surfacing text advertising a `mode_soc`
write the device discards — plus six other descriptions corrected on 2026-09-11.

### B3. Tier accumulators not recorded — ✅ REAL, FIXED
Confirmed then fixed: `tiers` column, `tier_samples()` returning the shape
`energy.tier_transitions()` consumes, sourced from the same `power_flow` read and kept out
of the MQTT payload. 7 tests. **Unblocks [[DEF-1303-TIER-BASIS]]**, which energy-fitting
cannot settle.

### B4. Hardcoded provenance labels — ❌ NOT A DEFECT (but it led to a real one)
`GET /api/catalog` already sources from `franklinwh_local.catalog`; the stale labels were
purely B2. **However**, checking it surfaced a genuine bug: `client.READ_METHODS` was
hand-maintained and had drifted **7 methods** behind — `battery_cells`,
`power_electronics`, `device_firmware`, `device_states`, `device_check`, `agate_serial`,
`energy_history` — so per-cell BMS telemetry had no endpoint. Now derived from the catalog
(29 → 35 endpoints), the same fix as [[DEF-CLI-CATALOG-DRIFT]] here.

### Lesson
Screenshots show *symptoms*; they do not show whether the code already handles the cause.
File cross-repo defects as **questions** until the source is read.

---

## INFO-1727-OPT-SWEEP — only opt=3 exists on 1727; no hidden reserve-write opt

**Status:** tested and closed (2026-09-11) — negative result
**Related:** [[DEF-RESERVED-SOC-RESEARCH]], [[DEF-RESERVED-SOC-PARTIAL-FRAME]]

The `opt` field is not binary — `0` reads, `1` writes, and `1727` uses `3` to set the
active mode — so a reserve write could plausibly have lived on an unenumerated `opt`. It
does not.

Swept `opt` 0–7 on `1727`, **write-identical** (`current_id` = 85232, the mode already
active, so a successful write is a no-op), re-reading `1726` after each:

| opt | result |
|---|---|
| 0, 1, 2, 4, 5, 6, 7 | **no reply at all** (timeout) |
| 3 | `result:0`, empty payload, no `reason` field |

`current_id` and all three `reserved_soc` values were unchanged after every probe.

**Conclusion:** `1727` implements exactly one `opt`. No hidden reserve-write opt on this
code.

**Catalog correction:** the description claimed `opt=1` was "keep-alive/paging". It drew no
reply with `{opt:1, current_id}`. Either it needs different fields or the claim was wrong;
the description now states only what was observed.

### Selector question closed: `id` ≡ `scheduling_type`

Follow-up asked whether the reserve write might key on `scheduling_type` (== cloud
`workMode`) rather than `current_id`. Per the device owner, **`id` is a gateway-specific
GUID permanently correlated to a `scheduling_type`** — on this gateway 85232≡2 (Self),
29287≡1 (TOU), 47522≡3 (Backup). They are two names for the same mode, so `current_id`
already selected Self unambiguously and the selector was never the missing variable. No
re-test needed.

### Probe interrupted by a transport failure (cause: most likely the WiFi link)

The follow-up probe stopped partway: `login failed (timed out)`, then
`ConnectionResetError`. It recovered unaided after ~20 s with **state intact** (current_id
85232, reserves 100/15/11, discharging normally). Nothing was mutated.

**Correction.** This was first written up as "rapid reconnect cycling destabilises the
gateway". That over-read a single event — the probe did open ~14 connect/login cycles in
quick succession, but nothing distinguished that from ordinary link flakiness. Per the
device owner, **this aGate is on WiFi and is intermittently unreliable**, which explains it
at least as well. The repo already encodes that: `DEFAULT_TIMEOUT = 20.0` is commented
"generous for slow/flaky local wifi", and `--timeout`/`--retries` are documented "raise for
slow/flaky wifi". Treat transport failures on this link as expected noise, not as evidence
about gateway behaviour.

Practical guidance is unchanged and holds either way: prefer one long-lived session, use
the built-in retries, and back off rather than hammering reconnects — see
[[FEAT-LOCAL-RECORDER]]'s bridge handoff notes. A probe script should also verify state
after a transport error rather than assuming nothing happened.

To actually attribute a future failure, note whether other traffic to the gateway is
failing at the same time (the bridge polls continuously and would show it), rather than
inferring cause from the probe alone.

### Limitation — this test cannot prove field acceptance
`1727 opt=3` also accepted `reserved_soc`, `soc`, `minSoc` and `selfMinSoc` alongside
`current_id`, all with `result:0`. **That proves nothing**: the values sent were the
current ones, so "ignored" and "wrote the same value" are indistinguishable. Write-identical
is safe precisely because it is non-diagnostic here.

**`1405` re-confirmed on current firmware (2026-09-11 mutating test, prior state restored).**
Ran on `IBG_VER V12R02B30D06_260304`, one session: full 9-field block with
`selfMinSoc 0 → 12`.

```
write reply : result:0 reason:0  selfMinSoc:12   <- ECHOES the value written
read-back   : selfMinSoc 0       (unchanged)
1726        : {47522:100, 29287:15, 85232:11}    (unchanged)
1801        : unchanged          (no collateral write)
restore     : result:0, prior state verified restored
```

**The reply echoes the written value.** That is worse than a bare `result:0` — a client that
trusts the echo will report success. This is why `set_mode_soc` must read-back-verify, and
why it stays in `UNVERIFIED_WRITES` rather than being exposed.

Note the July write-up rested partly on "read-back showed `selfMinSoc` still 0" — which
proves nothing, since the block reads 0 **always**. The load-bearing evidence was, and
remains, that `1726 reserved_soc` does not move.

`1727 opt=3` was not given the same mutating test; given `1405` behaves this way and reserve
is cloud-owned, another silent discard is the expected outcome there too.

---

## INFO-LOCAL-BMS-LAYER2-ABSENT — 26 cloud BMS fields have no local equivalent

**Status:** closed by exhaustive re-sweep (2026-09-11)
**Related:** [[RESEARCH-BMS-CELL-LOCAL]], [[FEAT-CMDTYPE-RECONCILE]]

Local `1705` + `1703` together reconstruct cloud `get_bms_info()` **211 type 2** — every
local field maps across (some renamed: `inverterVolt*`→`invVolt*`,
`middleBusVolt`→`midBusVolt`, `batVol`→`pebatVolt`, `currGrp`→`batCurr`).

The reverse does not hold. **26 cloud BMS fields have no local counterpart**, and they look
like the type 3 "Layer 2" half the cloud merges in:

| group | fields |
|---|---|
| thermal | `devTemp`, `llcTemp`, `invTemp`, `buckBoostTemp` |
| hardware state | `mosState`, `switchState`, `heatState`, `fanState`, `balanState` |
| cell extremes | `maxVolPos`, `minVolPos`, `maxTempPos`, `minTempPos` |
| power | `actPwr1/2`, `reactPwr1/2`, `outCur1/2` |
| voltages | `gridVoltAN/BN`, `solarVoltAN/BN`, `gridLineVol`, `invLineVol`, `samBatVol` |

**Re-swept to be sure.** The original 1101–1909 sweep ran *before* `{"opt":0,"id":N}` was
added to the payload matrix, so an id-gated code could have been missed — which is exactly
how 1705 hid the first time. Re-ran all 405 odd codes in the band including catalogued
ones, all shapes: **68 responded, 0 not already in the catalog, 317 explicitly rejected.**
(1113/1115 appeared id-gated in the sweep output; re-checked by hand and they are not — a
transient during the run.)

**Conclusion:** the catalog is complete for 1101–1909, and the Thermal Sensors panel and
balancing indicator are **cloud-only**. A bridge wanting them must use the cloud path.

Caveat: "complete" means no code *responds* to a read in that band. A write-only code with
no read handler would still be invisible — though every write-capable code found so far
(e.g. 1721) does answer `opt=0`.

---

## INFO-CLOUD-CODES-NOT-LOCAL — cloud cmdTypes are unreachable on TCP/9000

**Status:** tested and closed (2026-09-11) — negative result, worth recording
**Related:** [[FEAT-CMDTYPE-RECONCILE]], [[DEF-RESERVED-SOC-RESEARCH]]

Natural hypothesis: the cloud's `sendMqtt` relay targets *this same aGate*, and cloud
`updateSocV2` "fans out to ~5 sendMqtt calls server-side" — so the reserve-write commands
must exist on the device, just in the cloud numbering band (203/211/310/311/…) that the
local sweep never covered. If so, a reserve write would be reachable locally after all.

**Tested, and no.** Every cloud code — 203, 211, 310, 311, 315, 317, 327, 335, 337, 339,
341, 353 — makes the gateway **close the connection** rather than answer or refuse.

This also revealed a protocol behaviour that matters for probing:

| code | aGate response |
|---|---|
| in-band (≈1101–1909), implemented | normal reply |
| in-band, not implemented | `{"opt":0,"result":1,"reason":4}` — connection stays up |
| **out-of-band** | **connection closed**; every later probe on that socket is a broken pipe |

**This silently invalidated a sweep.** Probing 101–1099 returned "500 probed, 0 responded"
— which reads like a clean negative but was 500 bogus broken-pipe errors after the session
died on the first code. `probe_codes()` now takes a `reconnect` callback, distinguishes a
dropped session from a refused request (`_is_disconnect`), and rebuilds the session mid-
sweep; the CLI wires it. Tested.

**Conclusion:** the cloud relay and the local broker are separate dispatchers. A capability
the cloud reaches via sendMqtt is not automatically reachable locally, and the local
command surface really is bounded by the ~1101–1909 band the exhaustive sweep covered.

---

## FEAT-LOCAL-RECORDER — ⛔ REVERTED: storage belongs in the bridge

**Status:** ⛔ reverted same day (2026-09-11). Protocol helpers kept; storage removed.
**Related:** [[EPIC-CLOUD-ALIGN]], [[DEF-1303-PLOAD-DUP]], [[DEF-1303-TIER-BASIS]],
[[FEAT-DOCKER]]

I built a SQLite-backed poller into this library (`recorder.py`, `record` and
`load_history` CLI commands) to fill the interval-history gap from
[[DEF-1303-PLOAD-DUP]]. **That was an architecture violation** — [[EPIC-CLOUD-ALIGN]]
already decided this library stays "thin and protocol-faithful… the library is the *local
leg* only", with services layered in the bridge. A database, a long-running polling loop,
bucketing and retention are bridge concerns (`franklinwh-local-bridge` provides DB history,
multi-gateway, UI and REST).

Removed: `franklinwh_local/recorder.py`, `tests/test_recorder.py`, the `record` and
`load_history` subcommands, and the SQLite schema.

**Kept** (in `energy.py`, stateless helpers over payload dicts — protocol semantics, not
services): `active_tier()` and `tier_transitions()`. How 1301's tier accumulators behave
(running totals, reset at midnight, the one that grew is the active tier) is knowledge
about the protocol and belongs here; sampling and persistence do not.

### Handoff to the bridge

The bridge should poll `1301` on an interval and store it. What it needs from this library
is already exposed — `LocalClient.power_flow()` plus the notes below:

- **Per sample:** `p_sun`, `p_gen`, `p_fhp`, `p_uti`, `p_load` (W), `soc`, `t_amb`,
  `run_status`, `mode`, the running daily `kwh_*` totals, and the tier accumulators.
- **Signs**, matching the gateway's own totals: `p_uti` negative = export / positive =
  import; `p_fhp` positive = discharge / negative = charge.
- **Integrate trapezoidally** over actual sample spacing, and **skip gaps** (a poller
  outage must not straight-line into invented energy). Don't round before summing.
- **Reconnect on error.** The gateway drops repeated calls on a long-lived session —
  observed during this work — so tear the connection down and rebuild rather than retrying
  on a dead socket. Poll errors must not be fatal.
- **Tier transitions:** feed ordered payloads to `energy.tier_transitions()`. Running a
  poller across an evening should settle [[DEF-1303-TIER-BASIS]].

## DEF-1303-PLOAD-DUP — `energy_history`'s p_load series is a copy of p_fhp (device bug)

**Status:** confirmed device defect — documented, no workaround possible locally
**Filed:** 2026-09-11

In `1303 energy_history`, the 96-point **`p_load` array is byte-identical to `p_fhp`** —
battery power, not home load. Confirmed on **15/15 days** sampled across the entire
retention window.

It is specific to 1303, not to the field or the library:

| source | p_fhp | p_load | distinct? |
|---|---|---|---|
| local `1301 power_flow` (live) | 4964 W | 194 W | ✅ |
| cloud `203/runtimeData` (live) | 4.95 kW | 0.19 kW | ✅ |
| local `1303 energy_history` (history) | series | **identical series** | ❌ |

Consequences: there is **no local per-interval home-load history**, and `1303` also carries
**no `p_sun` series** at all (solar appears only as the `kwh_sun` daily total, though
`1301` does report instantaneous `p_sun`). The daily `kwh_load` total is correct — only
the interval series is wrong. Anything needing load-over-time locally must derive it
(`p_load ≈ p_fhp + p_uti + p_sun + p_gen`) or poll `1301` on an interval and store it.

This also invalidates any attempt to verify tier attribution by integrating `p_load` —
see [[DEF-1303-TIER-BASIS]].

---

## DEF-1303-TIER-BASIS — what clock does the device bucket energy by? (not 1407)

**Status:** open question — mapping deliberately NOT published
**Filed:** 2026-09-11
**Related:** [[DEF-LOCAL-TOU-DISPATCH]], [[FEAT-LOCAL-ROLLUPS]]

Each `1303` channel carries a `sharp`/`peak`/`flat`/`valley` split that sums exactly to
that channel's `kwh_*` total. **Which schedule drives the split is unresolved.**

**Ruled out — the local 1407 schedule**, and the cloud's static block list
(12:00/19:00/20:00): integrating the grid series against either fails to reproduce the
reported split.

**⚠️ CORRECTION (2026-09-11).** This entry previously said the boundary "moves day to day
(14:45, 14:45, 15:15, 16:15, 18:15)". **That was wrong** — an artifact of locating the
boundary by *cumulative crossing*, i.e. asking when running export reaches the reported
`flat` total. That only identifies a boundary when export is continuous across it; on days
with intermittent or tiny daytime export it just marks when a trickle happened to reach the
threshold.

Re-done properly against the bridge's 30-second samples (vs 1303's 15-minute series), by
**fitting fixed windows** and minimising error across four days:

| boundary pair | total abs error, 4 days |
|---|---|
| 15:45 / 20:15 (best fit) | 0.714 kWh |
| 18:00 / 21:00 | 1.021 kWh |

A **fixed** schedule fits every day tested. `valley` in particular matches to ~0.0005 kWh.
But the optimum is shallow — intermittent export means many boundary pairs score alike, so
the data constrains the boundary to roughly **flat→peak 15:45–18:00, peak→valley
20:15–21:00** and no tighter. The overnight hours cannot be classified at all from export
data (there is none).

**What the buckets actually contain**, consistently across every day sampled:

| bucket | behaviour |
|---|---|
| `flat` | the solar day — ~99% of `kwh_sun`, and essentially all `kwh_fhp_chg` |
| `peak` | the evening discharge/export window — `kwh_fhp_chg` is **exactly 0** here every day; `kwh_fhp_di` ~7.9–8.2 and `kwh_uti_out` ~6.9–7.3, near-constant regardless of solar |
| `valley` | the overnight tail |

**Leading hypothesis (unproven):** the site is on dynamic pricing (Amber Electric) and the
gateway reports `effective_mode = VPP mode`, so the priced/dispatched window moves daily —
which would produce exactly this moving boundary and a near-constant commanded evening
discharge. Not confirmed; no local cmdType exposes the per-interval tariff basis.

**Consequence:** no `tier -> waveType` table is published. The tier NAMES line up with the
cloud's rate tiers conceptually (`flat` ≈ Shoulder, `valley` ≈ Valley, `peak` ≈ Peak), but
asserting the numeric mapping would be a guess contradicted by the integration evidence.
Rollups sum the tiers as-is, which is correct regardless of the basis.

**To settle it:** record the live `sharp`/`peak`/`flat`/`valley` accumulators from `1301`
and watch which one ticks — `energy.tier_transitions()` does this. Energy-fitting has now
been pushed as far as it goes; it cannot resolve the boundary further, and it cannot touch
the overnight hours at all. **The bridge now stores those arrays** (fixed 2026-09-12, [[XREF-BRIDGE-DEFECTS]] B3) —
so recording resumes from that date. Extract with
`energy.tier_transitions(store.tier_samples(start, end))` once a day or two has
accumulated; a single evening spanning the boundary should settle it.

### ✅ Resolved sub-question: the "solar on-peak residual"

Earlier I flagged ~0.19 kWh of `kwh_sun` in the `peak` bucket as unexplained, on the
assumption that `peak` meant 23:00–00:30 (1407's tier-2 window). **That assumption was
wrong** — `peak` is the *evening* window. Solar's small `peak` (0.13–0.29 kWh) and
`valley` (0.06–0.11 kWh) amounts are dusk and dawn generation falling either side of the
solar block. Physically expected; not an anomaly.

---

## INFO-TIER-SHARP-DEPRECATED — `sharp` is emitted but always zero

**Status:** observation (confirms a user hypothesis)
**Filed:** 2026-09-11

`sharp` is **0 for all seven channels on every day sampled** across the full ~105-day
retention window. franklinwh-cloud's own `TOU_TARIFF_REFERENCE.md` likewise lists "Sharp"
as an unlisted waveType ("possibly 3 or 5") that the tariff API never returns.

Reading: a legacy fourth tier (Chinese 尖/峰/平/谷 — sharp/peak/flat/valley) retained in the
wire format for compatibility but no longer assigned. Recorded as
`catalog.DEPRECATED_TIERS`; still summed, since the device still emits the array.

Caveat: "never assigned" is inferred from one site on one tariff. A site whose plan has a
critical-peak tier could still populate it.

---

## FEAT-LOCAL-ROLLUPS — ✅ week/month/year energy rollups computed locally

**Status:** ✅ DONE (2026-09-11)
**Related:** [[FEAT-CMDTYPE-RECONCILE]], [[DEF-LOCAL-TOU-DISPATCH]]

The aGate serves one day per request (1303) and has **no** rollup cmdType — local
`dayType` is echoed but ignored (tested 0-5, all return the same 96 points), so the
cloud's `get_power_details(type=2..5)` Week/Month/Year/Lifetime figures are computed
cloud-side. `franklinwh_local/energy.py` does the same arithmetic locally.

- `energy.rollup()` walks the period newest-first, one 1303 request per day.
- Periods reuse the cloud's numbering: day=1, week=2, month=3, year=4, total=5.
- **Coverage is always reported.** Retention is ~105 days, so year/total are partial by
  construction; a `Rollup` carries days_requested / days_with_data / days_missing rather
  than presenting a short sum as a full period.
- `--stop-after-empty N` (default 5) short-circuits once N consecutive days are empty —
  history is contiguous, so a year rollup need not request 260 discarded dates.
- CLI `energy_rollup --period/--date/--json`; `LocalClient.energy_rollup()`.

Verified live: week 2026-09-07..11, 5/5 days, tier splits reconciling to channel totals.

---

## DEF-LOCAL-TOU-DISPATCH — the per-block dispatch schedule is NOT on the local channel

**Status:** confirmed gap (not a defect in this library) — documented
**Filed:** 2026-09-11
**Related:** [[FEAT-CMDTYPE-RECONCILE]]

`1407 tou_schedule` carries the **tariff (wave) schedule** only: `<day>Lv` / `<day>Time[]`
/ `<day>Flag[]` for workday and weekend, decoded by `energy.decode_tou()` and exposed as
`franklinwh-local tou`. Local and cloud agree on the tier numbering
(`catalog.WAVE_TYPES` == `franklinwh_cloud.const.WaveType`).

**What is missing:** the per-block **dispatch** action (Home Loads 1 / Standby 2 / Solar
Charging 3 / Self-Consumption 6 / Grid Export 7 / Grid Charge 8) the app shows beside each
block. Evidence it is not there:
- 1407 has no sub-type carrying it — `{"opt":0}` plus `type` 1-5, `paraType` 1-2 and
  `dispatch` all return the identical key set (the cloud uses sub-types this way on
  cmdType 211, so it was worth testing).
- The exhaustive 1101-1909 sweep found no other schedule-shaped code.

So dispatch scheduling is cloud-owned (`saveTouDispatch` / `get_tou_dispatch_detail`).
Locally you can read the tariff tier by time, and the active mode (`mode_config` /
`ibgMainState`), but not the per-block dispatch programme.

**Open:** the `sharp` tier's wave code. Local energy history accounts for it as a distinct
bucket (always 0 on schedules seen so far) and franklinwh-cloud's own docs list Sharp as an
unlisted waveType, "possibly 3 or 5". Neither side has confirmed it. A schedule that
actually uses a sharp block would settle it.

---

## DEF-CLI-CATALOG-DRIFT — `catalog` advertises 32 names the CLI cannot run

**Status:** ✅ DONE (2026-09-11)
**Filed:** 2026-09-11
**Related:** [[EPIC-CLI-ALIGN]], [[FEAT-CATALOG-CLOUD-FIELD]]

### Problem
`franklinwh-local catalog` prints the protocol catalog; the CLI's live subcommands come
from a **hand-maintained** `LIVE_COMMANDS` list (`franklinwh_local/cli.py:723`). The two
have drifted:

```
catalog entries:              60
runnable subcommands:         40   (12 of which are not catalog names)
in catalog but NOT typeable:  32
```

The 32 orphans are every `grid_compliance_*` (12), every `grid_*` trip/curve/mode read
(11), `smart_circuit_schedule`, `grid_batt_access`, `device_control`, `mode_page`, and all
five `unknown_*`. So the catalog reads as a menu, and two-thirds of it is not orderable —
`franklinwh-local -i <ip> unknown_1207` fails with a 40-item argparse dump. Every cmdType
added to `CATALOG` since `LIVE_COMMANDS` was written is invisible to the CLI, and the
drift silently recurs on each catalog addition.

### Fix (no redesign needed; do this even if EPIC-CLI-ALIGN is deferred)
1. **Generate `LIVE_COMMANDS` from `catalog.CATALOG`** so the two sets cannot diverge.
   Guard the destructive/unconfirmed ones (`device_control`, `unknown_*`) behind an
   explicit opt-in flag rather than omitting them silently.
2. **Make the failure a signpost.** On unknown subcommand: `difflib` near-matches plus
   "…is a known cmdType — try `franklinwh-local call 1207`". The escape hatch exists; the
   error never mentions it.
3. **Add a regression test** asserting `{i.name for i in CATALOG.values()} <= subcommands`.

### Display defects (same command, same fix pass)
- Name column is padded to 20 (`cli.py:137`) but names run to **30** chars, so alignment
  collapses from `grid_compliance_es_voltage` onward.
- Descriptions are unwrapped: **the longest catalog line is 464 characters.** `der_comms`
  alone is a paragraph.
- No grouping, no column headers, and no flag for read/write/UNCONFIRMED/invocable.
- Pairs with [[FEAT-CATALOG-CLOUD-FIELD]] (`catalog --json` + a cloud-equivalence column):
  do both in one pass so the renderer is written once.

### Also
`--host` is global, so `franklinwh-local --host <ip> catalog` silently accepts and ignores
it. Offline commands (`catalog`, `decode`, `analyze`, `emulate`) should warn or reject.

### ✅ Resolution (2026-09-11)
All of the above landed. `live_commands()` is derived from `catalog.CATALOG`; the surface
went 40 -> 72 subcommands with **zero** unreachable catalog names, locked by
`tests/test_cli_surface.py`. `mode_page` is an alias of `mode`. `catalog` is grouped by
family with per-group column widths, wrapped descriptions, `W`/`?`/`!` flags, `--json` and
`--grep`; `CmdInfo.cloud_api` carries the cloud equivalence for 44/60 codes
(closes [[FEAT-CATALOG-CLOUD-FIELD]]). Unknown commands now get difflib suggestions plus
the `call <code>` hint; `--help` uses a grouped epilog instead of a 72-name dump; offline
commands warn on `--host`.

**Deviation from the plan above:** destructive/unconfirmed reads are **not** gated behind
an opt-in flag. Every catalog read is `opt=0`, which is safe by construction (the old
scratch prober already read all of them), so gating would have re-created the
discoverability problem this item exists to fix. They are flagged in `catalog` output
(`?` = UNCONFIRMED, `!` = maintenance) and in each subcommand's `--help` instead.

Live-read **output format** was deliberately left as-is — formatted-vs-JSON is
[[EPIC-CLI-ALIGN]]'s call and still pending the noun-vs-verb decision.

---

## FEAT-CMDTYPE-RECONCILE — full Local↔Cloud cmdType delta, both directions

**Status:** queued — research + data, precedes CLI work
**Filed:** 2026-09-11
**Related:** [[FEAT-CATALOG-CLOUD-FIELD]], [[RESEARCH-BMS-CELL-LOCAL]], [[EPIC-CLI-ALIGN]]

### Why
`docs/CLOUD_MAPPING.md` covers §1 mapped, §2 local-only, §3 cloud-only — but §3 is written
as *capabilities* (prose), not as **cloud cmdTypes**. That is the half that matters for
finding missing local reads: a cloud cmdType with no local match is either (a) genuinely
cloud-owned, or (b) **a local cmdType we simply have not found yet**. Today we cannot tell
which, because the two namespaces have never been laid side by side as codes.

### Key structural fact (document this prominently — it is easy to misread)
**The two cmdType numbering spaces are unrelated.** Cloud sendMqtt uses low codes
(`203` composite info, `211` BMS, `310/311` smart circuits, `317` network, `335/337` wifi,
`339` cloud, `341` net switches). Local uses `1101–1903`. Cloud `211` is **not** local
`211`. `CLOUD_MAPPING.md` maps them conceptually but never says the namespaces are
disjoint — a reader can easily assume otherwise.

### Deliverable
1. Enumerate **cloud** cmdTypes from `franklinwh-cloud` (`MqttCmd` enum + the mixins that
   call `_build_payload`), with their payload shapes — including parameterised ones
   (`{"fhpSn": …, "type": 2}`), not just `{opt:0}`.
2. Produce a **three-column reconciliation**: cloud code → concept → local code, with an
   explicit verdict per row: `mapped` / `local-only` / `cloud-only (owned)` /
   `cloud-only (LOCAL UNKNOWN — candidate probe target)`.
3. Land it as data (`CmdInfo.cloud_api`, per [[FEAT-CATALOG-CLOUD-FIELD]]) so the bridge
   and CLI consume it programmatically; `CLOUD_MAPPING.md` stays the human view.
4. Every `cloud-only (LOCAL UNKNOWN)` row becomes a probe target — see below.

### Coverage reality check (why "no local equivalent" is a weak claim today)
The local catalog holds **60 of the ~400 odd codes** in 1101–1909. Unprobed gaps:

```
1103–1107 (3)     1123–1199 (39)    1231–1249 (10)    1279–1299 (11)
1303–1399 (49)    1413–1699 (144)   1703–1705 (2)     1711–1719 (5)
1729–1799 (36)    1803–1819 (9)     1833–1899 (34)
```

**~342 odd codes have never been confirmed** — the whole 1500s/1600s block is untouched.
"No local equivalent" currently means "not found by a blind `{opt:0}` sweep", which is a
much weaker statement than it sounds.

---

## RESEARCH-BMS-CELL-LOCAL — ✅ RESOLVED: it's cmdType 1705, gated on an `id` selector

**Status:** ✅ RESOLVED (2026-09-11) — found, catalogued, exposed, hardware-verified
**Filed:** 2026-09-11
**Related:** [[FEAT-CMDTYPE-RECONCILE]]

### The anomaly
The cloud exposes full per-cell BMS telemetry — 16 series cell voltages + per-cell temps,
SoH, balancing state, MOS/DCDC/heater/fan states, pack V/I/Hz (rendered by the HA
Integrator's Battery tab). Locally there is **nothing** equivalent. `1831 battery_modules`
returns only `devNum` + `devMap[{id, devSN}]` — a serial list, no telemetry. That is
backwards: the local broker channel is the *device-level* channel and should be a superset
of what the cloud relays, not a subset. This repo's own README argues exactly that ("the
cloud drops structural telemetry… battery cell voltages"), yet locally we cannot read it.

### What the cloud actually does (verified in `franklinwh-cloud`)
`get_bms_info(apower_serial_no)` → `franklinwh_cloud/mixins/devices.py:177`:
- cmdType **211** (`MqttCmd.POWER_AND_RELAYS`), sent **twice**, sequentially
- payload `{"fhpSn": "<aPower serial>", "type": 2}` then `{"fhpSn": …, "type": 3}`
- must be sequential — concurrent sends make both fail (MQTT layer cannot multiplex)
- returns the richer of the two payloads; type 3 is frequently lost (known app issue)

### Hypothesis — it exists locally and our probe method could not have found it
1. **The request is parameterised by battery, not by gateway.** Every local read we issue
   is addressed to the aGate (`equipNo` = IBG_SN) with `{"opt": 0}`. The BMS read needs a
   **per-aPower selector** (`fhpSn`) and a **`type` discriminator**. `probe_gaps.py` sends
   `c.call(cmd)` → `{"opt":0}` only, so a cmdType that requires `fhpSn` would return empty,
   error, or time out — indistinguishable from "does not exist."
2. **We already hold the input.** Local `1831` returns exactly the `devSN` list that `fhpSn`
   wants, and the `1101` login manifest carries `FHP_SN` and `BMS_SN`. The addressing
   plumbing is half-built already.
3. **The likely range was never swept.** 1413–1699 (144 odd codes) is entirely unprobed.

### Probe plan (read-only, live aGate)
1. Read `1831` + `1101` to get the aPower/FHP serials.
2. Re-run the gap sweep, but **parameterised**: for each unprobed odd code try
   `{"opt":0}`, `{"fhpSn": <sn>}`, `{"fhpSn": <sn>, "type": 2}`, `{"fhpSn": <sn>, "type": 3}`.
   Record which payload shape produced a non-empty `dataArea`.
3. Also retry the five `unknown_*` codes (1207/1209/1821/1823/1825) with the `fhpSn`/`type`
   shapes — they return placeholder-looking structs (`{enable, mode}` = 111/222) under
   `{opt:0}`, which is consistent with "wrong payload shape", not "meaningless code".
   `1823 {powerOn, powerOff}` and `1825 {power}` sitting in the 1800s **battery** block,
   next to `1801 battery_inhibit` / `1827 ibg_state` / `1831 battery_modules`, is
   suggestive.
4. Grade a hit by whether the payload carries ~16 repeated voltage-shaped values.
5. **Generalise `probe_gaps.py`** — it currently hardcodes a stale 17-entry `KNOWN_REQUESTS`
   set (the catalog now has 60) and only ever sends `{opt:0}`. Make it payload-matrix
   driven and derive known codes from `catalog.CATALOG`.

### ✅ Tooling landed (2026-09-11) — the probe itself still has to be run
`franklinwh_local/probe.py` + the `probe` subcommand implement the plan above:
payload matrix per code, serial auto-discovery from 1831 + the login manifest,
catalog-derived known-set (no stale hardcoded list), `--codes`/`--range` scoping,
`--json`, and a cell-telemetry detector (>=8 numeric values inside 2.0-5.0 V or
2000-5000 mV). `tests/test_probe.py` proves the core claim in-process against the
emulator: a selector-gated code **times out under `{"opt":0}` and is found by the
matrix**. `probe_gaps.py` is superseded.

**Still to do:** run it against the live aGate and record the result here. Start narrow
(`--codes 1207,1209,1821,1823,1825`), then sweep 1413-1699. Note the caution in
docs/USAGE.md — this sends cmdTypes of unknown semantics to a real battery system.

### ⛔ Live probe result #1 (2026-09-11, aGate 192.0.2.110) — hypothesis 2 REFUTED for the five unknown_* codes

Ran `probe --codes 1207,1209,1821,1823,1825 --all-shapes`. Serial auto-discovery worked
(found `FAKEAPOWERP6KMFY7ALA`, matching the BMS SN the HA Integrator shows). **All five
codes returned byte-identical payloads under every payload shape** — `{opt:0}`,
`{fhpSn}`, `{fhpSn,type:2}`, `{fhpSn,type:3}`, `{opt:0,fhpSn}`:

| code | payload (identical for all 5 shapes) |
|------|--------------------------------------|
| 1207 | `{"enable": 111, "mode": 222}` |
| 1209 | `{"enable": 1}` |
| 1821 | `{"enable": 0}` |
| 1823 | `{"powerOn": 0, "powerOff": 0}` |
| 1825 | `{"power": 0}` |

**Conclusion:** the `fhpSn`/`type` selector has no effect on these codes — they ignore the
request payload entirely. Hypothesis 2 above ("placeholder values mean wrong payload
shape") is **refuted for these five**. 1207's 111/222 are genuinely what the device
returns, not an artefact of how we asked. These stay UNCONFIRMED but are no longer
BMS candidates.

This does **not** touch hypothesis 3 (the read lives in an unswept range) — these five
were simply the cheapest test. The 1413–1699 sweep is still the real experiment.

**Method note (found by running it):** the first run stopped at the first shape that
responded, so the selector shapes were never reached on codes that already answer
`{opt:0}`. Fixed — `--all-shapes` tries every shape and keeps the richest reply. Any
probe of an already-responding code must use it, otherwise the comparison is vacuous.

### ⛔ Live probe result #2 (2026-09-11) — 1413–1699 swept: NO BMS data, 2 new codes found

Ran `probe --range 1413-1699 --all-shapes` (144 codes x 5 payload shapes, read-only).

**No per-cell telemetry anywhere in the range.** The cell-series detector fired zero times.

**142 of 144 codes were explicitly rejected**, not silent — which is a significant method
finding in itself: the aGate answers an unimplemented cmdType with
`{"opt":0,"result":1,"reason":4}` rather than timing out. So "does this code exist?" is a
*cheap, definitive* question on this firmware (~0.1 s per call, no timeout wait), and
absence of a code can be asserted rather than inferred. The prober now classifies
`rejected` separately from `empty` (accepted, result=0, no payload).

**Two undocumented codes DID respond — a firmware/OTA block in the 1500s:**

| code | name | idle payload |
|------|------|--------------|
| 1501 | `firmware_deliver` | `{result:1, reason:5, fileName:"", order:"", operator:"", deliverResult:5}` |
| 1503 | `firmware_upgrade` | `{result:1, reason:8, fileName:"", order:"", sign:"", type:0, steps:4, upgradeResult:8}` |

Both answered the plain `{opt:0}` read; the `fhpSn` selector changed nothing. `result!=0`
here reads as "no transfer/upgrade in progress", so the fields are defaults. Added to
`CATALOG` and flagged `!` (maintenance): **reads only — an `opt=1` write to either would
push a firmware file or trigger an upgrade. Never attempted, and should not be without a
deliberate, separately-approved hardware test.** These are relevant to
[[FEAT-FIRMWARE-VERSION]].

**Status of the BMS hypotheses after two probes:**
- Hypothesis 1/2 (parameterised payload) — **refuted** on every code probed so far: no
  code has yet changed its answer based on `fhpSn`/`type`.
- Hypothesis 3 (unswept range) — **1413–1699 is now swept and clean.** Still unswept:
  1123–1199, 1231–1249, 1279–1299, 1303–1399, 1729–1799, 1803–1819, 1833–1899, plus
  1103–1107 / 1703–1705 / 1711–1719 (~200 odd codes). Now known to be cheap to sweep.
- Remaining possibility not yet tested: the read is not on the aGate's 9000 channel at
  all, and the aPower relays cell data only to the cloud (or over Modbus — cross-check
  `franklinwh-modbus`).

### ✅ RESOLVED (2026-09-11) — full sweep found it: **1705 `battery_cells`**

Swept all 343 remaining uncatalogued odd codes (1101–1909) x 5 payload shapes, read-only.
**335 explicitly rejected, 8 responded.** One of them is the answer:

```
1705 {"opt":0,"id":1} ->
  batVolt:  [3326 x16]            # mV per cell
  batTemp:  [18.8 … 19.5 x16]     # degC per cell
  batTotalVolt 53.2  batSoc 78.7  batSoh 94.9  currGrp -4.3A  alarmLevel 0
  singleHighestVolt 3326  singleLowestVolt 3325
  singleHighestTemp 19.5  singleLowestTemp 18.7
```

That is the HA Integrator's Battery page, read locally. **The premise of this item was
wrong: the local channel is not missing BMS telemetry.**

**Why it hid.** The hypothesis was right in structure (a per-device selector) and wrong on
the parameter: the local channel keys per-device reads by the small integer `id` from
`devMap[].id`, **not** the `fhpSn` serial the cloud API uses. Worse, 1705 answers a plain
`{"opt":0}` with the *same key set*, just empty — `batVolt: []`, `batSoc: 0`,
`result=1 reason=-1`. So it looks like a live-but-useless code rather than a gated one.

**Seven more codes found in the same sweep:**

| code | name | notes |
|------|------|-------|
| 1703 | `power_electronics` | per-device bus/grid/inverter V+A — the "Inverter & Power Electronics" panel. Needs `id`. |
| 1833 | `device_firmware` | per-device serials + `bms_ver`; richer than the 1101 manifest. Needs `id`. |
| 1835 | `device_states` | ibgDsp/ibgMain/pe/bms states. Needs `id`. |
| 1105 | `device_check` | devMap[{id, devSN, checkResult}] — **the source of the `id` selectors**. |
| 1103 | `device_scan` | request must carry `devNum`. |
| 1123 | `agate_serial` | returns aGate_SN but `result=1 reason=-2`; shape not understood. |
| 1303 | `energy_history` | rec_time/p_*/kwh_*/TOU buckets. Needs date params; **shape UNCONFIRMED** (a date-shaped probe timed out). |

Plus 1501/1503 (firmware OTA) from the earlier 1413–1699 sweep. Catalog: 60 -> 70.

**Landed:** all eight catalogued; `catalog.NEEDS_ID`; `LocalClient.battery_cells()` /
`power_electronics()` / `device_firmware()` / `device_states()` / `device_check()` /
`device_ids()`; CLI `--id` on the four per-device reads; `docs/CLOUD_MAPPING.md` §3b
documents the gotcha and 1705 moves out of "cloud-only".

**Two method fixes this forced, both now tested:**
1. `default_payloads` tries `{"opt":0,"id":N}` **before** the serial shapes — the local
   convention is the index, not the serial.
2. Richest-reply scoring counted *keys*. The empty shell has the same keys as the real
   payload, so the shell won on a tie and the real data was discarded. Now scores
   **filled** fields first (`payload_score`), key count only as a tiebreak.

### Follow-ups opened by this
- `1303 energy_history` request shape — local historical energy would remove a cloud
  dependency. Probe date/dayType/pointId combinations (it timed out rather than rejecting,
  so it is doing *something*).
- `1103` / `1123` request shapes.
- Re-run the reconciliation ([[FEAT-CMDTYPE-RECONCILE]]) now that 4 cloud-only rows moved.
- Multi-battery sites: everything here was verified against a **single** aPower (`id:1`).
  `device_ids()` enumerates, but the N>1 path is untested.
- 1501/1503 OTA writes remain **never attempted** and should stay that way absent a
  deliberate, separately-approved test.

### If the probe comes up empty
Then the aGate genuinely does not relay BMS cell data on TCP/9000 and the cloud path
(aPower → aGate → AWS IoT → app) is the only one — worth recording as a **confirmed**
`cloud-only (owned)` row rather than an open question. Third possibility to rule out:
the data is reachable over Modbus (cross-check `franklinwh-modbus` register map) —
if so, note it as a Modbus-only capability in the reconciliation table.

---

## OPS-BACKUP — back up all FranklinWH repos regularly

**Status:** ongoing practice (GitHub live; iCloud to set up)
**Filed:** 2026-08-02

Don't lose work. Applies to `franklinwh-local`, `franklinwh-local-bridge`,
`franklinwh-hybrid`, and the modbus/cloud bridges.
- **Primary — GitHub (private):** commit + push after every meaningful change (this repo
  already does). Don't leave work unpushed for long.
- **Secondary — iCloud:** periodically mirror repos to iCloud Drive (e.g. `git bundle` each
  into `~/Library/Mobile Documents/com~apple~CloudDocs/backups/franklinwh/`, or
  `git clone --mirror`). **TODO:** write the mirror script + pick a cadence / scheduled routine.
(Detail duplicated in franklinwh-local-bridge/BACKLOG.md.)

---

## FEAT-CATALOG-CLOUD-FIELD — machine-readable cloud-equivalence on the catalog

**Status:** ✅ DONE (2026-09-11) — landed with [[DEF-CLI-CATALOG-DRIFT]].
**Filed:** 2026-07-30

Make the local↔cloud equivalence **queryable by data**, not by parsing `docs/CLOUD_MAPPING.md`,
so the bridge's unified/routing layer can map programmatically. Keep the library thin — this
is a small structured field, **not** an abstraction (see EPIC-CLOUD-ALIGN decision).

Plan (no code): promote the inline `[cloud: …]` annotation in `CmdInfo.description` to a
first-class **`CmdInfo.cloud_api: str | None`** field; render it as a column in
`franklinwh-local catalog` (with headers) and add **`catalog --json`**. This supersedes the
old EPIC-CLOUD-ALIGN "cloud-shaped wrapper" idea — the mapping stays documentation/data; the
bridge consumes it. `docs/CLOUD_MAPPING.md` remains the human-readable reference.

---

## FEAT-PYPI — publish this library as `franklinwh-local-api` on PyPI

**Status:** packaging DONE — build/validate green; **publish held while repo is private**.
**Filed:** 2026-07-30

**Done (2026-07-30):** dist renamed to **`franklinwh-local-api`** (import stays
`franklinwh_local`, CLI stays `franklinwh-local`); metadata/URLs rounded out; `CHANGELOG.md`
added; **release CI** (`.github/workflows/release.yml`) builds + `twine check`s on every
push/PR and has a **gated publish job** (tags only, PyPI trusted publishing / OIDC).
Local build validated: `franklinwh_local_api-0.1.0` wheel+sdist, twine check PASSED, 57
tests pass. **To actually publish (when public):** make the repo public, configure PyPI
trusted publishing for `franklinwh-local-api`, then push a `vX.Y.Z` tag.

Split parallels FWHAI + energipays (`energipays-client` lib / `energipays-bridge` add-on):
this repo is the **library**, published to PyPI as **`franklinwh-local-api`** so it's reusable
independently — by `franklinwh-local-bridge`, other HA/non-HA projects, or ad-hoc — with **no
web/MQTT weight** (stays stdlib-only). Import path can remain `franklinwh_local`.

Plan (no code): finalise dist metadata in `pyproject.toml` (name `franklinwh-local-api`,
classifiers, `py.typed`, entry point), CHANGELOG/versioning, a release CI (build sdist+wheel;
publish on tag via trusted publishing) — but **while the repo is private, hold actual PyPI
publish**; build/validate only. See PLAN_docker.md §1–§2.

---

## DEF-WIFI-RECONNECT — reboot can leave the aGate on 4G; can the local API force WiFi?

**Status:** research — **PLAN ONLY, no code.**
**Filed:** 2026-07-29

After a reboot the aGate can fail over to **4G** and **not auto-reconnect to WiFi** —
observed twice; last time the owner had to switch it back to WiFi manually. **If the owner
is away (no access to the WiFi hotspot / router), a reboot that lands on 4G strands the
local API until they are physically home.** This makes unattended reboot dangerous and is
a hard gate on the reboot command.

Research (no code): can the local API bring it back to WiFi without physical access?
- `network_switches` (`1119`: `ethernet0/1NetSwitch`, `wifiNetSwitch`, `4GNetSwitch`) —
  is a **write** (opt:1) able to toggle these? (Unverified; would itself need careful
  hardware verification, and if it's cloud-reachable-only on 4G, the write must go via
  cloud not local.)
- `network_interfaces` (`1117`) — WiFi config / reconnect trigger?
- Safer pattern: **never reboot unattended**; if a reboot is unavoidable, first confirm
  WiFi is the active/priority interface and 4G failover won't strand it — or require the
  owner to be on-site.
- Interaction: this gates `reboot --wait` re-discovery (a new IP is findable via scan, but
  a 4G handoff takes it off the LAN entirely — scan won't find it).

---

## INFO-BATTERY-INHIBIT-FIELDS — what are 1801's fields for? (observation only)

**Status:** info only — **do not work.** Recorded for later correlation.
**Filed:** 2026-07-29

`battery_inhibit` (`1801`) exposes a struct that is **not surfaced in the official app or
the cloud API**. Its fields point at advanced / cold-climate / generator features:

- `topSoc` — top charge SoC cap
- `inhSocNormal` / `inhSocCold` / `InhSocExtCold` — charge-inhibit SoC at normal/cold/extreme-cold
- `normalTemp` / `coldTemp` / `extColdTemp` — temperature bands for the above
- `startHeatBatTemp` / `stopHeatBatTemp` — battery heater on/off temps
- `batMaxChFactor` — max charge-rate factor
- `delayToChTime` — delay before charging
- `blackStartOnOff` — black-start enable
- `startGenSoc` / `stopGenSoc` — generator auto start/stop SoC
- `InhUseFlag` — inhibit in-use flag

**Key observation (2026-07-29, aGate 192.0.2.110):** the returned values are **sequential
0..14 in field order** (`topSoc=0, inhSocNormal=1, … InhUseFlag=14`). That is not real
config — it looks like **placeholder / positional-index defaults**, i.e. the struct is
**unconfigured / the feature is not in use** on this unit (real SoC/temp values would be
e.g. 90/10/-5). Same placeholder tell as `1207 {enable:111, mode:222}`.

Correlation question for later: these are likely **cold-climate battery protection +
generator auto-start + black-start** — installer/region features the standard app/cloud
don't show. To decode real semantics, capture `1801` on a unit where these ARE configured
(cold-climate and/or generator install). No action now. Related: the class of "placeholder-
looking" responses (1207/1801) may all be defined-but-unpopulated structs.

---

## FEAT-DOCKER — franklinwh-local-bridge (HA add-on / REST + MQTT)

**Status:** Phase 0 DONE (2026-08-02) — scaffold built in a **separate repo**
`~/dev/franklinwh-local-bridge`. Design in **[PLAN_docker.md](PLAN_docker.md)**.
**Filed:** 2026-07-29

> **Scope correction (2026-08-02):** an *existing* hybrid-coupled bridge lives at
> `~/dev/Claude/Projects/franklinwh-local-bridge` (uses `franklinwh-hybrid`); left untouched.
> Per owner: **local API only for now** (hybrid is a future repo). So the new bridge is a
> **fresh, separate repo** `~/dev/franklinwh-local-bridge`, depends only on
> `franklinwh-local-api`.
>
> **Phase 0 (done):** energipays-modelled scaffold — pyproject (`franklinwh-local-bridge`),
> dual-target Dockerfile (slim standalone / alpine HA base), HA add-on (config.yaml ingress
> :8101 + options/schema + `mqtt:want`, build.yaml, repository.json, entrypoint), FastAPI
> `/api/health|power|der-comms|firmware` + ingress UI + OpenAPI, pydantic-settings, thin
> client adapter over the library, `read_only` default. 4 pytest pass; live health OK. Local
> git repo (no remote yet). Next: Phase 1 (fuller REST/UI) → Phase 2 (MQTT + HA discovery).

Package `franklinwh-local` as a Docker container so the local API bridge can run as a
long-lived service (continuous `health`/monitoring, scheduled reads, re-discovery after
reboots) rather than only ad-hoc CLI. Two image variants:

| Variant | Source | Purpose |
|---------|--------|---------|
| **live** | tagged release | stable/production image; pinned version |
| **dev**  | `main` (or a branch) | development image, latest changes, verbose logging |

Plan (no code yet):
- Multi-stage Dockerfile (slim Python base; `pip install .`); stdlib-only runtime so the
  image stays small.
- Entrypoint = the `franklinwh-local` CLI; a long-run mode (e.g. `health --watch` /
  monitoring loop) for the service use-case.
- Config via env / mounted file: `--host`/IP, `--timeout`, `--retries`; support
  re-discovery (`scan`) when the aGate moves IP or fails over to 4G.
- Image tags: `:live` / `:vX.Y.Z` from releases, `:dev` from `main`; document build/run.
- CI: build both images; publish on tag (live) and on `main` (dev). Keep hardware/live
  tests out of image CI (AGENT.md).
- Open questions: registry (GHCR?), whether the container also exposes an HTTP/MQTT bridge
  (ties into EPIC-CLOUD-ALIGN) or stays CLI-only for now; healthcheck directive using the
  `health` command.

---

## FEAT-FIRMWARE-VERSION — surface & track aGate firmware release (bridge is the place)

**Status:** planned — **PLAN ONLY, no code yet**
**Filed:** 2026-07-29

The local API bridge is the best place to read/track the aGate firmware release: the login
(`1101 → 1102`) manifest already returns the version block — `protocolVer`, `IBG_VER`,
`APP_VER`, `AWS_VER`, `SL_VER`, `FPGA_VER`, `DCDC_VER`, `INV_VER`, `BMS_VER`, `BL_VER`,
`TH_VER`, `SyHdVersion`, `METER_VER`. Nothing exposes it cleanly today.

Plan (no code yet):
- A `firmware` (or `version`) read command that prints the manifest version fields
  (human + `--json`); include in `health --json`.
- **Record firmware version alongside every hardware-verification result** — behaviours
  like reserved-SoC write / der_comms may be firmware-gated (see DEF-RESERVED-SOC-RESEARCH
  #5), so any "verified/unverified" claim must be stamped with the FW it was tested on.
- Optional: warn/annotate when firmware changes between runs (a bridge that runs
  continuously can detect an OTA update and flag "re-verify writes").
- Feeds the Docker service (FEAT-DOCKER) and the re-expose gate (EPIC-REEXPOSE-WRITES).

---

## EPIC-REEXPOSE-WRITES — re-implement withheld writes with real hardware verification

**Status:** in-progress — **A1 (reboot) + FEAT-FIRMWARE + A2 (der_comms) re-exposed
(2026-07-29).** Excludes reserved SoC (see DEF-RESERVED-SOC-RESEARCH).

> **A2 der_comms — DONE / re-exposed.** `der_comms --set-modbus on/off`, `--set-2030-5
> on/off`, `--and-reboot`, `--force`. Full-block RMW (`client.set_der_comms`); raises on
> non-zero result. **Interface-level verification** (not the config field), and it **polls
> `:502` over a 30s window** because the write is delayed-apply (see finding below);
> `--and-reboot` is the fallback if `:502` doesn't converge. 2030.5 reads back
> registration/`enable`. Confirmations: Modbus-OFF (strands tooling) and 2030.5-ON (DERMS)
> require `yes`/`--force`.
>
> **KEY FINDING (live test 2026-07-29, FW `IBG_VER V12R02B30D06`, instrumented via the
> franklinwh-modbus bridge REST API `192.0.2.247:8100`):** der_comms `sunsMdEn` writes
> are **DELAYED-APPLY in both directions (~seconds, NO reboot)** on this firmware — the OFF
> did not stop `:502` immediately (a fast `port_open` missed it; the bridge caught it a few
> seconds later), and writing ON self-recovered `:502` without a reboot. This **contradicts
> the 2026-07-18 model** (OFF immediate / ON needs reboot) → **firmware-dependent**
> behaviour, caught by the FW stamp. Fix applied: verification now polls `:502` over a
> window instead of checking once. **No reboot was performed** (user was away and WiFi does
> not auto-reconnect after a reboot — a hard reason never to reboot unattended; see
> DEF-WIFI-RECONNECT below). Modbus left healthy (`sunsMdEn=1`, `:502` UP, bridge polling).
> 57 unit tests pass.

> **A1 reboot — DONE / re-exposed.** `reboot` + `--wait` back, now with a pre-flight 4G
> warning (reads `1119`; warns if `4GNetSwitch=1`) and auto subnet re-discovery if it
> returns on a new IP. `firmware` read command added (login-manifest version block).
> Live-tested 2026-07-29 on FW `IBG_VER V12R02B30D06_260304` (protocolVer V1.11.03):
> firmware read OK; baseline health OK (:9000 79ms, :502 UP, sunsMdEn=on); 4G pre-warning
> fired correctly (`4GNetSwitch=1`) and the confirmation gate aborted on decline — all
> against the live aGate, no reboot triggered. The destructive down→up + Modbus-restore
> was proven live earlier (2026-07-25); not re-triggered because 4G is enabled (off-LAN
> risk). 53 unit tests pass.

**Filed:** 2026-07-29
**Governing rule:** each write ships only after a *written, executed* hardware-verification
procedure that checks the actual interface/service — not a config read-back. See
`PROTOCOL_DESIGN_REQUIREMENTS.md` R1–R3/R7. No mock-only "tests pass" as proof.

### A1. `reboot` (1721) — QUICK WIN, already proven; bring back first
**PROVEN on hardware (2026-07-25):** full-block `{reboot:1}` rebooted the aGate
(offline at t+11s, down→up confirmed) and **restored Modbus TCP** — post-reboot `health`
showed `:502` UP, `sunsMdEn=on`, sendMqtt Test OK (the aGate re-binds `:502` on boot from
the saved `sunsMdEn=1`). It was withheld for *risk* (destructive + it can trigger a 4G/IP
change), not because it fails. Re-expose is mostly adding the safety framing below.
- Payload: full-block RMW (read `{reboot,reset,update}`, set `reboot=1`, write full block).
- Verify: down→up on `:9000` + real login (the two-phase `--wait` was correct); end on
  `health`-green.
- **New — re-discovery:** if it doesn't return on the same IP within budget, auto-`scan`
  the subnet and report the new IP (reboot can land a new DHCP lease).
- **New — 4G pre-warning:** read `1119 network_switches` first; warn if 4G is enabled (the
  aGate can fail over to cellular and drop off the LAN — observed).
- Safety: confirm + `--force`.
- Ship gate: recorded live run showing down→up→health-green, plus a run where it lands on a
  new IP and re-discovery finds it. Stamp firmware version (FEAT-FIRMWARE-VERSION).

### A2. `der_comms` writes (1205) — design around the asymmetry
- **OFF (`sunsMdEn=0`)** applies immediately → verifiable now: write, confirm `:502` goes
  DOWN. Confirm prompt (it strands Modbus tooling).
- **ON (`sunsMdEn=1`)** only sets a flag applied at **boot** → cannot be truthfully
  confirmed live. Options: (a) report `pending-reboot`, never claim `:502` up, offer
  `--and-reboot` (depends on A1); or (b) don't ship ON, document "enable via app / reboot".
- **2030.5 (`enable`)**: success = *registered* (`status2030_5` / `lfdi`/`sfdi` populated),
  not `enable=1`. Strong warning + confirm (hands dispatch to a DERMS).
- Ship gate: recorded runs — OFF drives `:502` down; ON→reboot brings `:502` up; snapshot+
  revert both. Decide whether ON is worth shipping at all given it needs a reboot.

### Shared checklist (every write, before re-exposing)
1. Full-block RMW. 2. Interface/service-level verify (not config field). 3. Snapshot +
revert. 4. Confirm/`--force` for destructive. 5. Written procedure, run on hardware,
results + firmware version recorded in the commit/BACKLOG.

---

## DEF-RESERVED-SOC-RESEARCH — RESOLVED: reserved SoC is CLOUD-OWNED (read-only locally)

**Status:** RESOLVED (2026-07-29). There is **no local write path** — by design.
**Filed:** 2026-07-29

**CONFIRMED via cloud→local sync test (2026-07-29):** set Self reserve 5→8 via the
FranklinWH **cloud** API (`PATCH /api/gateways/{id}/mode/reserve {soc, work_mode}`, "Operate
success!") and the **LOCAL `1726 reserved_soc` reflected 8 within ~8 seconds**; restored to
5, local followed. So reserved SoC is a **cloud-owned setting**: the aGate keeps a
**read-only local cache** (`1726`) synced from the cloud; local writes (`1405`/`1725`/`1727`)
are accepted (`result:0`) but discarded because the cloud is authoritative. **Set reserves
via the cloud** (`franklinwh-cloud` `update_soc`, or its REST `PATCH …/mode/reserve`); read
them locally via `mode --list`. franklinwh-local exposes **no** reserve write (correct).

Below is the historical investigation that led here.

FranklinWH's two-reserve model (separate Self and TOU reserved SoC) is a signature feature.
The aGate **reads** both locally (`1726 reserved_soc`). Not 2030.5.

**Known-suspect: our earlier `1727` reserve test sent a PARTIAL frame — an R1 violation, so
it is NOT conclusive.**

**LEADING HYPOTHESIS (2026-07-29): reserved SoC is a CLOUD-OWNED setting.** The aGate keeps
a local **read-only cache** (`1726 reserved_soc`) that it syncs *from* the FranklinWH cloud;
local writes are accepted (`result:0`) but discarded because the local channel is not
authoritative for it. Fits all evidence: no local write path works; the cloud has dedicated
reserve writes (`updateSocV2`/`updateTouModeV2`); the "System Busy → cloud round-trip" note;
and SPAN PICS "reserve resets on mode change" (re-sync of a cloud value).
**Definitive test (needs the owner / app or cloud creds):** change a reserve in the app (or
via the cloud `update_soc`) and watch the LOCAL `1726 reserved_soc` reflect it — if it
updates, reserve is cloud→local synced (read-only locally), case closed. The app works
remotely over the cloud, so the owner can do this while away.

Prioritized angles (updated):
1. **Full-block `1727` mode-page RMW — TESTED NEGATIVE (2026-07-29).** Read the entire
   `1726` block, changed `reserved_soc`, wrote the whole thing back via `1727 opt:3` (full
   mode entry) AND `1725 opt:1` (full list). Both `result:0`, reserve unchanged; re-tested
   with a **60s poll** to rule out delayed-apply — still no change. Snapshot+restored. The
   "we sent a partial frame" theory is refuted; supports the cloud-owned hypothesis above.
2. **Sequence/commit hypothesis.** `1727 opt:1` is keep-alive/paging — test whether a
   reserve write must happen *inside* an active paging session, or needs a write-then-`apply`
   frame; probe opt values beyond 0/1; look for a commit/enable field in the `1405` block.
3. **proxy.py capture (definitive, with caveat).** Run `proxy.py` between the app and aGate,
   change a reserve in the app, read the exact cmdType/payload/sequence. Caveat: the app in
   Direct/HotSpot mode has no reserve UI — **open question: does the app in normal mode on
   the same LAN use the local API for reserve (capturable) or go cloud-only?** If cloud-only,
   it is genuinely cloud-gated.
4. **Session/heartbeat gate.** By analogy to the Modbus `ControllerHb` finding — check if
   local writes need a preceding session/keep-alive.
5. **Firmware capability.** Stamp FW version (FEAT-FIRMWARE-VERSION); reserve-write may be
   version-gated — retest after any OTA.

Recommended definitive sequence: #1 (full-block 1727) + #3 (proxy in normal-LAN mode).

---

## WRITES-WITHHELD — unverified write commands pulled until hardware-verified

**Status:** done (writes pulled) — restore only after real hardware verification
**Filed:** 2026-07-25

Three write surfaces were removed from the CLI **and** library because they were not
hardware-verified as safe (one broke Modbus in testing; another only ever discards):

| Write | cmdType | Why pulled | To restore |
|-------|---------|-----------|-----------|
| `der_comms --set-modbus/--set-2030-5` + `client.set_der_comms` | 1205 | Asymmetric: `sunsMdEn=0` stops `:502`, `sunsMdEn=1` only sets a flag applied at boot → left `:502` down. "Verification" checked the config field, not the service. | Verify by driving the real `:502` service down/up across a write; only re-expose if a write can be applied+confirmed without a reboot. |
| `mode --soc` + `client.set_mode_soc` | 1405 | Silently discarded (`result:0`, not persisted). Reserve is cloud-only. | Only if a working local reserve write is ever found (unlikely — cloud-gated). |
| `reboot` (+ `--wait`) + `client.reboot` | 1721 | **Works** (proven: rebooted + restored Modbus `:502`); withheld for *risk* — destructive + can trigger a 4G/IP change. | Re-expose with confirm/`--force`, 4G pre-warning, and auto re-discovery (see EPIC-REEXPOSE-WRITES A1). This is the quick win. |

Kept: reads only for `der_comms`/`mode_soc`; the **verified** writes `mode --set` (1727,
switch confirmed live) and `offgrid --set` (1723); `call --data` (caveated manual escape
hatch). See `PROTOCOL_DESIGN_REQUIREMENTS.md`; `catalog.UNVERIFIED_WRITES` documents the
withheld payloads.

---

## XREF-MODBUS-DER-WRITEPLANE — cross-repo research handoff (not local work)

**Status:** reference only — belongs to `franklinwh-modbus`, tracked here for context.
**Filed:** 2026-07-18

Speculation on why FranklinWH **Modbus/SunSpec** control writes (OnGridMode, reserve SoC
`15507/15508/15509`, Model 704 setpoints, Model 715 `OpCtl`) are accepted but ignored: the
DER stays in **SunSpec Local Control** (`LocRemCtl=1`, read-only); leaving Local requires a
sustained controller heartbeat (`ControllerHb`) and/or a **commissioned-controller
authorization** — SPAN, or a registered **IEEE 2030.5 / CSIP** controller (currently off:
`1205 der_comms` shows `sunsMdEn=1` but 2030.5 `enable=0`). Ties into this repo's finding
that reserve SoC is cloud-only locally and **coupled to mode** (mode change resets reserve;
see [DEF-RESERVED-SOC] + `docs/PROTOCOL.md`).

Full handoff doc (for the franklinwh-modbus agent): **`~/Downloads/MODBUS_HANDOFF_der_control_writeplane.md`**.
No local code implied — this repo (sendMqtt protocol) has **no** reserve/DER-control write path.

---

## EPIC-CLI-ALIGN — align the `franklinwh-local` CLI with the `franklinwh-cloud` CLI

**Status:** planned — **DO NOT START** (design for review only; plan, no code)
**Filed:** 2026-07-15 · **Re-assessed:** 2026-09-11
**Related:** [[EPIC-CLOUD-ALIGN]] (API-level alignment; this is its user-facing complement),
[[DEF-CLI-CATALOG-DRIFT]] (the concrete defect), [[FEAT-CMDTYPE-RECONCILE]] (the data this
surface should expose)

### Goal
Make the local CLI feel like the cloud CLI so muscle memory and scripts transfer:
same command names, flags, and output conventions **where a shared concept exists**,
while keeping local-only protocol tooling as-is.

### Surface comparison (today)
- **Cloud** (`franklinwh_cloud/cli_commands/`, noun-per-domain): `status`, `discover`,
  `mode`, `tou`, `sc`, `bms`, `accessories`, `monitor`, `metrics`, `diag`, `raw`,
  `schema`, `support`, `fetch`.
- **Local** (`franklinwh_local/cli.py`): control → `mode`, `offgrid`, `grid_profile`,
  `scan`; generic live reads (`power_flow`, `install_profile`, …); protocol tooling →
  `decode`, `analyze`, `proxy`, `emulate`, `catalog`.

### Proposed mapping
| Concept | Cloud | Local today | Action |
|---------|-------|-------------|--------|
| Operating mode + reserve SoC | `mode` | `mode` (`--set`, `--soc`) | ✅ align flags/output |
| Quick summary | `status` | — (only `power_flow`) | add `status` |
| TOU schedule | `tou` | read via `call 1407` | add `tou` |
| Smart circuits | `sc` | `call 1409/1411` | add `sc` |
| Live monitor | `monitor` | `--watch/--count` flags | reconcile → `monitor` |
| Device discovery | `discover` | `scan` | keep `scan`, add `discover` alias |
| Raw API call | `raw` | `call <cmdType>` | keep `call`, add `raw` alias |
| Grid profile | (part of `discover`/support) | `grid_profile` | align naming |
| Protocol tooling | — | `decode`/`analyze`/`proxy`/`emulate`/`catalog` | **local-only; leave as-is** |

### Also reconcile
- **Output conventions:** cloud uses formatted sections (`print_section`/`print_kv`);
  local is plainer. Align on a shared style + `--json` on every command.
- **Naming divergences:** `scan`↔`discover`, `call`↔`raw` (add aliases, don't break).
- **Flag parity:** mode-set flags, SoC flag naming, `--json` everywhere.
- **workMode/mode aliases** already shared with siblings (`tou`/`self`/`backup`) — extend.

### Open questions
1. Add cloud-named aliases (`discover`, `raw`, `monitor`) or rename outright (breaking)?
2. Adopt the cloud's formatted output style, or keep local terse + `--json`?
3. Scope: control/read commands only, or also a shared help/UX layer?

### Re-assessment (2026-09-11) — decision needed on surface shape

The open questions above are still open, but a real defect surfaced under them:
`LIVE_COMMANDS` is hand-maintained and has drifted 32 names from the catalog
([[DEF-CLI-CATALOG-DRIFT]]). That reframes question 1 — this is not only about cloud
name parity, it is about whether the local command surface is **generated** or **listed**.

**Two candidate shapes:**

**(a) Verb surface — generated from the catalog.**
```bash
franklinwh-local get power_flow      # any catalog name
franklinwh-local get grid_ov_trip    # the 32 orphans work for free
franklinwh-local get 1207            # by code; subsumes `call`
franklinwh-local set mode self
franklinwh-local list --grep grid    # catalog, grouped/wrapped/flagged
```
Drift becomes structurally impossible; `--help` drops from 40 items to ~8. **But it moves
*away* from the cloud CLI's noun-per-domain shape** (`status`, `mode`, `tou`, `sc`, `bms`,
`monitor`, `raw`, …), which is the stated goal of this epic. Breaking; needs a name→`get`
shim.

**(b) Noun surface — match the cloud CLI, generate the long tail.**
Keep/add cloud-named nouns for the concepts that have a domain (`status`, `mode`, `tou`,
`sc`, `bms`, `monitor`, `raw`) and auto-generate the remaining catalog reads under one
`get <name>` escape hatch. Non-breaking, hits the epic's actual goal, and confines
generation to the tail that has no cloud counterpart.

**Recommendation: (b).** It fixes the drift where it matters, keeps the muscle-memory goal,
and does not fight the sibling CLIs. (a) is cleaner in isolation but optimises for a
property (uniformity) this epic did not ask for.

Two dependencies worth noting before starting:
- A cloud-parity **`bms`** noun cannot be implemented locally today — there is no local
  cmdType for per-cell telemetry. See [[RESEARCH-BMS-CELL-LOCAL]]; it is hardware-gated.
- Output convention (open question 2) should be settled as: **formatted human default +
  `--json` on every command**, matching `franklinwh_cloud/cli_output.py`
  (`print_section`/`print_kv`). Local live reads today emit unconditional
  `json.dump(indent=2)` (`cli.py:694`), so `--json` means "emit JSON" on `decode`/`scan`
  but does not exist on live reads, which are always JSON. Inconsistent in both directions.

> Plan only. No implementation until approved. Cross-check against `EPIC-CLOUD-ALIGN`
> so CLI names track the unified API method names.

---

## DEF-RESERVED-SOC-PARTIAL-FRAME — `set_mode_soc` writes an incomplete block, aGate rejects it

**Status:** RESOLVED — reserve-write is NOT a local capability (by design) (2026-07-15).
Root cause confirmed by device-owner observation: the **official FranklinWH app in Direct
WiFi HotSpot mode offers mode switching but NO reserved-SoC setting**. So the aGate has a
local handler for mode-switch (`1727 opt:3` works) but **no local reserve-write command** —
which is exactly why every reserve write (`1405`, `1725`, `1727` with `reserved_soc` or the
cloud-shaped `soc` payload) ACKs `result:0` yet never persists. Reserve setting is
**cloud-only** (`update_soc` / `set_mode(requestedSOC)`). `set_mode_soc` now read-back-
verifies and raises on the discard, so the library reports this honestly. Downstream
reserves-write stays disabled for the local channel — correctly, permanently.
`proxy.py` capture is moot for reserves (the app has no reserve UI in HotSpot mode to capture).
**Filed:** 2026-07-15
**Severity:** high (reserved-SoC writes silently fail; disabled downstream "pending proof")
**Area:** `franklinwh_local/client.py:set_mode_soc` (cmd 1405 opt:1); CLI `mode --set … --soc`

### Problem
`set_mode_soc(self_min, self_max, tou_min, tou_max)` sends only 4 fields. The 1405/1406
SoC block actually contains **9** fields, and the aGate **rejects a partial frame**.

### Evidence — live aGate 192.0.2.110 (2026-07-15, non-mutating read-write-identical)
Full read block: `selfMinSoc, selfMaxSoc, touMinSoc, touMaxSoc, backupMinSoc,
backupMaxSoc, genStartSoc, genStopSoc, BBBackupSoc` (BBBackupSoc=20, rest 0).

| Write | Fields sent | aGate reply |
|-------|-------------|-------------|
| current `set_mode_soc()` | 4 (self/tou min+max) | ❌ `result:1, reason:-2` (rejected) |
| full 9-field block | all 9, values unchanged | ✅ `result:0, reason:0` (accepted) |

**So the write is NOT cloud-gated / not "System Busy"** — it is a partial-frame
rejection. (The "System Busy" caveat in `catalog.py` / `PROTOCOL.md` applies to the
smart-circuit SoC cut-off, a *different* setting — do not conflate.)

### Cloud comparison (`franklinwh-cloud`, read-only)
`update_soc(requestedSOC, workMode, electricityType)` POSTs a **single** value for a
**single** mode to `hes-gateway/terminal/tou/updateSocV2` — the **cloud server
assembles the full SoC block** (fans out to ~5 `sendMqtt` calls server-side). The
local API has no server, so the *client* must send the complete 9-field block itself
(root cause above). Other cloud behaviours worth mirroring locally:
- `get_all_mode_soc()` → per-mode `{workMode, name, soc, minSoc, maxSoc, editSocFlag,
  active}`. It enforces a **min/max range** and an **`editSocFlag`** (not all modes are
  editable). Local `set_mode_soc` validates neither.
- `workMode` mapping is shared: TOU=1, Self=2, Backup=3 (local `scheduling_type` ==
  cloud `workMode`, per PROTOCOL.md).
- Cloud already has the prior-state pattern the user wants: `ForceStateSnapshot`
  (`prior_work_mode`, `prior_soc`, …) persisted to disk with a `load()` restore
  (`franklinwh_cloud/force_state.py`). Reference implementation for (2) below.

### Fix
1. ✅ **DONE** — `set_mode_soc` is now **read-modify-write**: reads the full 1406 block,
   overlays only caller-supplied fields (`None` = leave), writes all 9 back. CLI
   `mode --set … --soc` simplified to pass just the changed field.
2. ⬜ (nice-to-have) cloud-ergonomic `set_reserve_soc(work_mode, soc)` wrapper mirroring
   cloud `update_soc(soc, workMode)`. The CLI already maps Self→selfMinSoc / TOU→touMinSoc.
3. ✅ **DONE** — prior block is logged before the write and returned under `prior_soc`
   for reset (models cloud `ForceStateSnapshot`).
4. ⬜ **TODO** — validate against the mode's range/editability (`minSoc`/`maxSoc`,
   `editSocFlag`) before writing. Not yet done.
5. ✅ **DONE** — non-zero `result` now raises `TransportError` (CLI catches → exit 2);
   no more false success.
6. ✅ **DONE** — unit tests: full-9-field frame + rejection-raises. Live-verified by hand
   (non-mutating write-back → `result:0`). (A marked `@pytest.mark.live` test is optional.)
7. ✅ **DONE (WONTFIX locally)** — reserves-write stays disabled downstream because the
   local broker cannot set reserves (silent discard). `set_mode_soc` now surfaces this
   honestly instead of pretending success. Reserve changes must route through the cloud.

### ✅ Post-fix finding — RESOLVED (2026-07-15 mutating test, prior-state restored)
Set Self reserve 8→12% via 1405 `selfMinSoc`: write ACKed `result:0`, but read-back
showed `selfMinSoc` **still 0** and `mode_list.reserved_soc` **still 8%**. Restored clean.
Conclusion: the local broker **silently discards** the reserved-SoC write (write plane
locked / cloud-gated — same pattern as the Modbus SPAN lock and the "System Busy" note).
`result:0` is a FALSE success; read-back is mandatory.

Follow-up (2026-07-15): searched for the *reserve setpoint* write (the app-visible
`reserved_soc`, NOT the 1405 min/max range). 1405 and 1725 don't carry it. A first `1727`
opt:3 attempt used the field `reserved_soc` and did nothing — BUT that was the WRONG shape.

**Cloud reference (how it really writes the reserve):** two REST paths, both usable —
- standalone: `update_soc(requestedSOC, workMode, electricityType)` → `updateSocV2`.
- coupled w/ mode: `set_mode(mode, requestedSOC)` → `updateTouModeV2` with params
  **`currendId, soc, oldIndex(TOU=3/Self=2/Backup=1), workMode, electricityType`**.
The reserve field is **`soc`** (not `reserved_soc`), and the mode-write carries `oldIndex`
+ `workMode`. This maps ~1:1 to the local `1727` mode-page write.

**Refined hypothesis — TESTED, NEGATIVE (2026-07-15, clean run, snapshot+restore):**
local `1727` opt:3 with the cloud-shaped payload `{current_id, soc:N, oldIndex, workMode,
electricityType}` returns `result:0` but does NOT move `reserved_soc` (Self 15→soc:20→
still 15). So `soc` on `1727` is ignored just like `reserved_soc`.

**Conclusion (FINAL, exhaustively verified):** no local write path sets the per-mode reserve
setpoint. Proven three ways: (1) mutating tests on `1405`/`1725`/`1727` (incl. cloud-shaped
`soc` payload) all ACK `result:0` but never persist; (2) an EXHAUSTIVE read-only sweep of
every odd cmdType `1103–1909` — the app-visible `reserved_soc` appears ONLY as a read field
in `1726`; no cmdType exposes it as writable (the only SoC-bearing cmdTypes are telemetry
`1301`/`1711`, the `1405` min/max block, smart-circuit cutoffs `1409`, off-grid `1723`,
charge-inhibit/gen `1801`, solar `1903` — none is the mode reserve); (3) device-owner
confirms the official app has no reserve UI in Direct/HotSpot mode. Reserve setting is
**cloud-only** and is fully documented in `franklinwh-cloud` (`update_soc`/`set_mode`,
OpenAPI JSON) — no traffic interception needed. `proxy.py` is moot here. Item CLOSED.

Consequences implemented:
- `set_mode_soc` now re-reads and **raises `TransportError` on a read-back mismatch**
  (`verify=True` default; `verify=False` to skip). Unit test `test_set_mode_soc_detects
  _silent_discard` + live-confirmed the raise.
- The effective per-mode reserve lives in `mode_list.reserved_soc` (Self=8/TOU=15/
  Backup=100); the 1405 `*MinSoc` fields are a separate quantity that also won't persist
  locally. Local API exposes no `editSocFlag`/range either — so item 4 is moot locally.
- The cloud-ergonomic `set_reserve_soc(work_mode, soc)` wrapper (item 2) is **not shipped**
  — there is no working local reserve-write to wrap. Revisit only if a working local path
  (e.g. reserve carried on the 1727 mode write) is later discovered.

---

## EPIC-CLOUD-ALIGN — SUPERSEDED: unify in the bridge, keep the library thin

**Status:** SUPERSEDED (2026-07-30) — decision below. The original "cloud-shaped wrapper
inside the library" is **dropped**.
**Filed:** 2026-07-14
**Plan (historical):** [PLAN_cloud_alignment.md](PLAN_cloud_alignment.md)

**DECISION (2026-07-30):** Do **not** add a cloud-shaped abstraction/compat wrapper to the
`franklinwh-local-api` library. Keep it **thin and protocol-faithful** — named methods over
the sendMqtt protocol (`power_flow`, `mode_list`, `der_comms`, `set_mode`, shared
`tou`/`self`/`backup` aliases), honestly representing what the local channel can/can't do
(e.g. no reserve write; delayed-apply). Rationale:
- **Single responsibility** — the library is the *local leg* only; unification across
  local/Modbus/cloud belongs in the **bridge's `integrations/registry`** (energipays-style
  common model each poller maps into), not the library.
- **Honesty** — a unified in-library wrapper would paper over real local limits (the exact
  confusion behind the write-safety saga).
- **Reuse** — a thin library is maximally reusable on PyPI; consumers add their own adapters.
- The equivalence **seam is documentation/data**, not code: `docs/CLOUD_MAPPING.md` (+ the
  optional structured `cloud_api` field, see below), consumed by the bridge to route.

Kept from the original epic: the `catalog` cloud-equivalent column and a machine-readable
mapping (now FEAT-CATALOG-CLOUD-FIELD). Dropped: the in-library compat wrapper and the
`franklinwh-unified` fork (the **bridge** is the unification layer).

---

## DEF-GRID-PROFILE-NAMING — describe grid-compliance cmdTypes as profile-agnostic

**Status:** done (descriptions neutralized); optional profile-name accessor still queued (hardware-gated)
**Filed:** 2026-07-14
**Area:** `franklinwh_local/catalog.py` — cmdTypes 1211–1229 and 1251–1277

### Problem
These cmdTypes had names/descriptions that framed them as a specific grid standard.
They are just **settings** — the local API is grid-profile-agnostic; a cmdType's values
reflect whatever grid profile the site has loaded. The naming should describe the
*setting* (OV trip, OF trip, Q(V) curve, …), not editorialize about a standard.

### Fix
1. ✅ **DONE** — cmdType names are functional (`grid_*` / `grid_compliance_*`), numeric
   codes unchanged. Descriptions/comments/docstrings now describe the setting only, with
   no region/standard framing. Field names (e.g. `*_AS`) are the device's own raw JSON
   keys and are left verbatim. `ComplianceRuleType` is documented neutrally as "the loaded
   profile id". No behaviour change; tests green.
2. ⬜ **QUEUED (hardware-gated)** — optional client accessor to surface the loaded
   profile via 1203/1251; confirm the exact local field on hardware first.

### Note (live probe of aGate, read-only)
The local API returns only the numeric `ComplianceRuleType` (the loaded profile id),
not a human-readable name. cmd 1251 is a superset block (~90 raw device keys) that also
carries interop flags (`IEEE_2030_5_EVAL`, `SUNSPEC_MODBUS_*`, `UI_CAPABILITY_ER`), i.e.
the cmdType is generic across profiles — reinforcing the agnostic framing above.
