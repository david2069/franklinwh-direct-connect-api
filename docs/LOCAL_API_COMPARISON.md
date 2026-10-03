# FranklinWH Local (Direct Connect) API — the two Python implementations

There are two independent, open Python libraries for the FranklinWH aGate's
**local** protocol — the cloudless TCP service the official app uses for
installation and its "Direct Connect" menu. This document compares them by what
matters functionally: **what you can actually do with the aGate** through each,
how far each covers the device's capabilities, and how their documentation
differs. They are **not** forks of each other.

| | **`franklinwh-local`** (this repo) | **`voidstarr/franklinwh_local`** |
| --- | --- | --- |
| Repo | `david2069/franklinwh-direct-connect-api` | `github.com/voidstarr/franklinwh_local` |
| PyPI | `franklinwh-direct-connect-api` | — (source only) |
| License | MIT | MIT |
| Focus | full data layer + control + tooling + emulator | transport + command table |
| Client methods | 52 | ~10 |
| Device capabilities covered | 70 cmdTypes, with hardware-verified semantics | 44-command table (names/opcodes) |
| Reads (battery cells, PE, energy, TOU, generator…) | ✅ deep | ⚠️ a few high-level queries |
| Writes / control (mode, circuits, generator, off-grid, DER) | ✅ with read-back verification | ⚠️ SunSpec-Modbus enable only |
| Emulator / mock aGate | ✅ dynamic, multi-aPower | ❌ |
| LAN discovery / scan | ✅ | ❌ |
| CLI (~20 subcommands) | ✅ | ❌ |
| Docstrings & worked examples | ✅ rich (79 docstrings in the client alone) | ✅ README example |
| **Reference application** (real-world) | ✅ full-stack bridge (~16k LOC) | ❌ |
| Home-Assistant integration | ✅ MQTT discovery + REST | ❌ |
| Documentation | layered (usage/API/mapping) + verified catalog | one excellent protocol README |

**TL;DR** — this library is a complete functional stack for *operating* the aGate;
voidstarr's is a compact, well-documented transport core. The protocol itself is
solved by both and is not a differentiator (see the footnote).

---

## 1. What you can do with the aGate

This is the part that matters — the protocol is just the pipe; the functionality is
what reaches through it.

### Reads
| Capability | This library | voidstarr |
| --- | --- | --- |
| Live power flow / SoC / mode | ✅ | ✅ (`query_mode`, device info) |
| Login/firmware manifest | ✅ | ✅ |
| Solar / EMS | ✅ | ✅ |
| **Per-cell BMS** (voltages, temps, pack health) | ✅ | ❌ |
| **Power electronics / DC bus, device states** | ✅ | ❌ |
| **Multi-aPower rosters** (per-unit) | ✅ | ❌ |
| **Energy history** (96 quarter-hour points + kWh totals + TOU tiers) | ✅ | ❌ |
| **Energy rollups** (week/month/year/total, computed locally) | ✅ | ❌ |
| **TOU tariff schedule** as readable blocks | ✅ | ❌ |
| **Generator** status/config | ✅ | ❌ |
| **Grid-compliance profile** (fans out ~25 cmdTypes) | ✅ | ❌ |
| SunSpec-Modbus / IEEE-2030.5 settings | ✅ | ✅ (read) |

### Writes / control (this is where the gap is widest)
| Control | This library | voidstarr |
| --- | --- | --- |
| Set operating mode (Self-Consumption / TOU / Backup) | ✅ | ❌ |
| Smart-circuit on/off | ✅ (RMW + read-back verify) | ❌ |
| Off-grid on/off + hold SoC | ✅ | ❌ |
| Generator settings (windows / exercise / SoC thresholds) | ✅ | ❌ |
| DER comms (enable SunSpec Modbus / 2030.5) | ✅ | ✅ (SunSpec enable) |
| Reboot | ✅ | ❌ |

Every write here is a full-block **read-modify-write with read-back verification**
(the aGate rejects partial frames and a `result:0` ack does not prove the change
applied) — so `set_smart_circuit`, `set_mode`, etc. only report success when a
re-read confirms it.

### Tooling around the API
* **Emulator** — a deterministic per-seed synthetic aGate + N aPowers, wire-faithful
  for any serial, serving live telemetry, energy history, smart circuits, and
  **persisting writes** (toggle a mock circuit and it sticks). No hardware needed to
  develop against.
* **Discovery** — LAN scan for gateways on TCP 9000 with a real login handshake.
* **Proxy / pcap decode / analyze** — a transparent decoding relay and offline capture
  tooling.
* **CLI** — ~20 subcommands (`battery`, `mode`, `tou`, `energy_rollup`, `grid_profile`,
  `der_comms`, `scan`, `health`, `emulate`, …).
* **Home-Assistant bridge** — the companion `franklinwh-local-bridge`.

voidstarr provides `LocalClient` with ~10 query helpers plus `set_sunspec_modbus`, and
raw `request()` for anything else — a solid base to build on, but the functional
surface stops at the transport plus a handful of reads.

---

## 2. Command coverage

This library documents **70 cmdTypes** with prose semantics — often the date and
method each was hardware-verified, and explicit "what is NOT established" caveats. Its
value is knowing *what each command means and whether it is safe to write.*

voidstarr documents the **44-entry `CommunicationCmd` enum** exactly as the app names
it (`index / name / req_code / resp_id`), lifted from the app binary. Its value is
**canonical naming and opcodes** — a useful cross-check against this library's
capture-derived catalog. (Tracked as a cross-reference in `BACKLOG.md`.)

One correction this comparison settled: voidstarr's table carries an `optType` field
per command, but that is an **internal app field, not a wire key** — captures never
send it; the real requests use plain `opt`. This library correctly omits it.

---

## 3. Documentation

**This repo** ships layered docs — `README.md`, `docs/USAGE.md` (how-to),
`docs/API.md` (reference), `docs/CLOUD_MAPPING.md` (local↔cloud command mapping) — plus
a large `BACKLOG.md` of open questions and hardware-verification results, and the
catalog itself, which doubles as per-command documentation.

**voidstarr** ships a single, unusually good `README.md`: a precise protocol spec with
an envelope field table and a per-item "verified against the capture" ledger. For its
scope it is excellent; it is a *protocol* document more than an *API* one.

---

## 4. Developer experience & the reference application

For a library, the code you read is as important as the code that runs. This is where
the difference is largest, and it is what most developers actually feel.

**Docstrings.** Every public method here carries a real docstring — what it reads or
writes, the cmdType, the payload shape, the sign conventions, and the caveats (`client.py`
alone has 79 docstring blocks). Writes document their read-modify-write recipe and how
success is verified. voidstarr's code is clean and typed with a solid README example, but
the per-call documentation is lighter.

**Examples.** A quick-start in the README, a how-to in `docs/USAGE.md`, and — uniquely —
a **CLI of ~20 subcommands** that is itself a set of worked examples: every command is a
call into the library you can read, run offline against the emulator, or point at real
hardware.

**The reference application — the Local Bridge, real-world example writ large.**
The companion **`franklinwh-local-bridge`** is not a toy demo; it is a complete
application built on this library, and the best documentation of what the library can do:

* **~8,000 lines of Python** — a FastAPI service exposing **103 REST endpoints**, a
  per-gateway polling supervisor, an in-process mock-aGate manager, and a metrics store.
* **Publishes to Home Assistant over MQTT** (discovery + state), so the aGate shows up as
  native HA entities — with the synthetic/mock path gated off by default.
* **~9,000 lines of HTML + JavaScript** — a **rich optional web UI** (Alpine.js +
  Chart.js, 13 tabs: dashboard, battery/per-cell, solar, smart circuits, generator,
  scheduler, logs, settings, Home-Assistant, …) with live charts, a Sankey energy flow,
  a real-time watch-live mode, and a full Gateways manager.
* Runs as a Docker container or a Home-Assistant add-on.

So a developer evaluating this library doesn't have to imagine what it enables — they can
run a production-grade app that exercises nearly the entire surface (reads, verified
writes, MQTT, REST, and a web UI) against real hardware **or** the built-in emulator.

voidstarr's library ships no application, UI, MQTT, or REST layer — it is a transport
core to build those things *on*, not an example *of* them.

---

## 5. When to use which

* **Building an integration, dashboard, automation, or HA setup** → this library: it
  has the reads, the verified control surface, the emulator, discovery, and the bridge.
* **You want a tiny, dependency-free base to build your own client on** → voidstarr's.
* **Both** → this library already took voidstarr's seed formula; its canonical command
  enum remains a handy naming cross-check.

---

## Footnote — the protocol is not a differentiator

Both libraries implement the same obfuscated framing (a per-byte additive cipher over
the payload, a CRC-32 envelope, `response = request + 1`, one frame per segment). It is
technically interesting, but functionally it is **solved, fixed plumbing** — FranklinWH
is not going to change it, and once decoded it never needs thinking about again. The
one wire-level detail with any functional consequence was the **seed**, which is derived
from the serial: this library previously hardcoded it (correct only for its own gateway)
and adopted voidstarr's per-serial formula so it can talk to *any* gateway. Beyond that,
the framing is invisible to everything above it.

---

*Credit: the per-serial seed formula and the `CommunicationCmd` enum are the work of
`voidstarr/franklinwh_local` (MIT). Written 2026-09-19; both libraries evolve, so
re-check the repos for current coverage.*
