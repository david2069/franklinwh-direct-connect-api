# Changelog

All notable changes to `franklinwh-direct-connect-api` are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); this project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **`electricSupply` is the supply/service amperage, and `airSwitchCur` is the air-switch
  rating — the catalogue had it backwards.** It described `electricSupply` as an undecoded
  capability bitfield (`63 = 0b111111`) and treated `airSwitchCur` as the service amps. The
  owner confirmed on 2026-09-27 that his site is a **63 A supply**, reading
  `electricSupply=63` with `airSwitchCur=100`: 63 is simply 63 amps. The two differ
  whenever the supply is smaller than the air switch can carry, so substituting one for the
  other misreports the service rating. `docs/PROTOCOL.md` now names both fields in the
  `1701` row instead of listing only `airSwitchCur`.

### Fixed

- **`__version__` no longer reports a release behind the one you installed.** It was a
  hand-maintained literal reading `0.4.0` while the published distribution was `0.5.0`,
  so anything logging the library version — a bridge recording its dependency, a bug
  report, `health` output — named the wrong release. `pyproject.toml` is now the single
  source and the package reads it back from its installed distribution metadata, with a
  test that fails if the two ever diverge again.

- **The deprecation notices no longer promise a removal that already passed.** The
  `franklinwh_local` import shim, the `franklinwh-local` command and the `LocalClient`/
  `LocalTransport` class aliases were all documented as "removed in 0.5.0" — but 0.5.0
  shipped with every one of them still in place, and two README lines stated the removal
  as a past event. The date is now **0.6.0** in all **nine** places that carried it (the
  shim's docstring, its runtime `DeprecationWarning`, two `pyproject.toml` comments, the
  test module, three README lines, and the `LocalClient`/`LocalTransport` alias comments
  in `client.py` and `transport.py` — the last two found only by grepping for the stale
  string after believing the job was done), and each says the date moved rather than letting
  the earlier promise disappear. **Nothing was removed** — the aliases still work and
  still return the same objects.

### Documentation

- **The comparison document no longer claims the bridge's features as this library's.**
  Two rows credited this package with a Home Assistant integration and a "reference
  application" — both belong to the separate Direct Connect Bridge, and were a leftover of
  an abandoned plan to ship everything in one package. The table also had the PyPI-names
  note spliced into the middle of it, splitting it in two. Every number left in it (54
  client methods, 70 cmdTypes, 87 CLI subcommands, 59 docstring blocks, 6 writes) is now
  checked against the code by a test.

- **The disclaimer, warnings and licence terms now match the Direct Connect Bridge's.**
  `LICENSE` gains Additional Terms (unofficial / no affiliation, compliance &
  anti-circumvention, intent & risk, notice), scoped to the Direct Connect protocol on
  TCP/9000. The README gains a full **Disclaimer** section — folding in the note about the
  "Direct Connect" name — a stronger warning on **Control (live writes)** pointing at the
  compliance terms and telling people to confirm every change in the official app, and a
  redaction warning on the **Security note**: captures, `.pcap` files and `--raw` / `proxy`
  / `probe` output carry WiFi credentials, serials and location in clear.

## [0.5.0] — 2026-10-15

The emulator gained a live site clock, an install profile and an explicit timezone. Cut as
a release because a consumer installing this library from PyPI could not use any of it —
the Direct Connect Bridge's add-on hit `TypeError: unexpected keyword argument
'tz_offset_hours'` against 0.4.0 and failed to create a mock gateway.

> Entries below start on 2026-10-13, when this section was first kept current. Earlier
> releases are recorded under their own headings; nothing before that point is
> reconstructed here.

### Added

- **The emulator answers the site clock, the install profile and the grid measurements.**
  1201/1202 `time_location` now returns the site's real wall-clock instead of falling
  through to the capture's date — a consumer deriving the site's UTC offset from it used to
  get hundreds of days, which is not a timezone. 1701/1702 `install_profile` is synthesised
  (with `fhpRatePower`/`genRatePower` left at 0, as the real firmware reports them), and
  1708 now carries `gridVol1`/`gridVol2`/`gridLineVol`/`gridFreq`.

- **One site, one timezone.** `SyntheticSite(..., tz_offset_hours=)`,
  `Emulator(tz_offset_hours=)` and `franklinwh-direct-connect emulate --tz-offset` set the
  site's UTC offset explicitly (fractional for the half-hour zones). Omitted, the per-seed
  random offset is unchanged — pass it when several mocks model ONE site, which otherwise
  disagree about what hour it is.

- **Held sessions.** `connect()`, `close()`, `connected`, `ensure_session()` and a `connects`
  counter on `DirectConnectClient`. Every call used to open a TCP connection *and* perform a
  login before closing it again; a caller can now hold one session across many commands.
  Existing `with`-block usage is unchanged. (#6)

### Changed

- **Requests are serialised.** The transport takes an `RLock` around a request and around
  login, so two threads sharing a client can no longer interleave frames on one socket.
  Measured on a 5-thread run: 1 connection with the lock, 5 without. (#6)

## [0.4.0] — 2026-10-08

Renamed the import package and CLI to match the distribution name, so the project has
**one** name instead of three. Nothing is removed in this release — the old spellings keep
working and warn.

### Changed
- Import package `franklinwh_local` → **`franklinwh_direct_connect_api`**.
- CLI `franklinwh-local` → **`franklinwh-direct-connect`**.
- `LocalClient` / `LocalTransport` → **`DirectConnectClient`** / **`DirectConnectTransport`**.
- `--version` and usage text now take the program name from `argv[0]`, so they read
  correctly under either entry point.
- `[project.urls]` pointed at the pre-rename repo, which is what PyPI renders; repointed,
  with Documentation now going to the published site rather than a blob link.

### Deprecated
Removal in **0.5.0**:
- importing `franklinwh_local` (any submodule) — emits `DeprecationWarning`;
- the `franklinwh-local` console script;
- the `LocalClient` / `LocalTransport` names.

### Migration
```python
from franklinwh_local import LocalClient                        # before
from franklinwh_direct_connect_api import DirectConnectClient    # after
```
The alias re-exports the **same module objects**, not copies — `franklinwh_local.CATALOG is
franklinwh_direct_connect_api.CATALOG`, and `isinstance` holds across both spellings — so
you can migrate a file at a time. `PYTHONWARNINGS=error::DeprecationWarning` locates what
is left.

### Why
"Direct Connect" is FranklinWH's own term for this protocol, and the distribution was
renamed to match in 0.3.0 — but the import package and CLI kept the older `local`
spelling. Three names for one library meant the README had to carry a paragraph
explaining which was which. A distribution name differing from its import name is normal
Python (`pillow`/`PIL`, `beautifulsoup4`/`bs4`); carrying a *superseded brand* in the
import name is not the same thing, and is what this fixes.

## [0.3.0] — 2026-09-13

### Added
- **`battery` (alias `bms`)** — Battery Management view: per-cell voltages and
  temperatures, pack SoC/SoH, grid/DC-bus rails and hardware states, from `1705` +
  `1703` + `1835` + `1833` in one session. Local only; works on the Direct-Connect
  hotspot.
  - `--watch [SECONDS]` · `--for 90|30s|5m|2h` · `--count N` to monitor continuously,
    Ctrl-C to stop. Repaints in place on a terminal, appends when piped.
  - `--id N` for multi-aPower, `--json` per sample, `--no-colour`; colour auto-disables
    off-TTY and honours `NO_COLOR`.
  - Cell extremes (`↓`/`↑`/`*`) are derived from the arrays, so nothing is lost against
    the cloud's `minVolPos`/`maxVolPos`.
- `franklinwh_local.bms` — pure render helpers (`render`, `cell_grid`, `cell_stats`,
  `parse_duration`), testable without hardware.

### Notes
- Rows the local channel cannot fill — thermal sensors, cell balancing, MOS/fan/heater
  state — are **omitted rather than blanked**, so the view is not presented as a degraded
  copy of the cloud's. They remain cloud-only (`docs/CLOUD_MAPPING.md` §3e).

## [0.2.0] — 2026-09-12

Protocol discovery release. An exhaustive read sweep of the 1101–1909 band (every odd
code, multiple payload shapes) grew the catalog **60 → 70 cmdTypes** and closed several
open questions. Backwards compatible: no command or method was removed.

### Added — cmdTypes
- **`1705 battery_cells`** — per-cell BMS telemetry: `batVolt[]` (mV/cell), `batTemp[]`
  (°C/cell), pack totals, SoC/SoH, `alarmLevel`. The local equivalent of the cloud's
  `get_bms_info()`, previously believed absent.
- **`1703 power_electronics`** — per-device inverter and DC-bus detail.
- **`1833 device_firmware`** / **`1835 device_states`** — per-device serials/versions and
  DSP/PE/BMS states.
- **`1303 energy_history`** — one day of 96 quarter-hour points plus seven `kwh_*` totals
  and per-tariff splits. Stored on the gateway, rolling ~105-day window.
- **`1105 device_check`**, **`1103 device_scan`**, **`1123 agate_serial`**,
  **`1501 firmware_deliver`**, **`1503 firmware_upgrade`** (OTA status — read-only).

### Added — API
- `LocalClient`: `battery_cells()`, `power_electronics()`, `device_firmware()`,
  `device_states()`, `device_check()`, `device_ids()`, `energy_history()`,
  `energy_rollup()`, `tou_blocks()`, `agate_serial()`.
- `franklinwh_local.energy` — week/month/year/total rollups over daily history (the
  gateway has no rollup call), TOU schedule decoding, and stateless tier-accumulator
  helpers (`active_tier`, `tier_transitions`).
- `franklinwh_local.probe` — payload-matrix cmdType prober with a cell-telemetry detector.
- `catalog`: `CmdInfo.cloud_api` (53/70 mapped), `NEEDS_ID`, `NEEDS_DATE`, `UNCONFIRMED`,
  `MAINTENANCE`, `TIERS`, `DEPRECATED_TIERS`, `ENERGY_CHANNELS`, `WAVE_TYPES`, `family()`,
  `writes_for()`.

### Added — CLI
- `probe`, `tou`, `energy_rollup`, and one subcommand per catalog entry.
- `--id` on the four per-device reads; `--date` on `energy_history`.
- `catalog` regrouped with `--json` and `--grep`; grouped `--help`; unknown commands now
  suggest near matches and point at `call <code>`.

### Fixed
- **Command surface is now derived from the catalog.** `LIVE_COMMANDS` was hand-maintained
  and had drifted 32 names behind, so `catalog` advertised commands that could not be run.
- Offline commands warn instead of silently ignoring `--host`.

### Documentation — corrections
Several descriptions were wrong and are corrected; if you rely on them, re-read:
- **`1405 mode_soc`** reads all zeros except `BBBackupSoc` — it is **not** a usable reserve
  read (use `1726 reserved_soc`), and writes are accepted, echoed back, and discarded.
  Reserve is cloud-owned; re-confirmed by a mutating hardware test.
- **`1801 battery_inhibit`** reads back the sequential integers 0–14 — field position, not
  data. Treat as unpopulated.
- **`1701` / `1903`** carry the grid power plane (`kwRatePower`, `gridSoftLimit`,
  `gridHardLimit`, `gridExportEnable`, `isPcsDischgEn`, `grid_feed_max`) — never previously
  documented.
- **`1727`** implements only `opt=3`; the claimed `opt=1` keep-alive draws no reply.
- **`1725`** `id` is a per-gateway GUID bound to `scheduling_type`; ids are not portable.
- `docs/CLOUD_MAPPING.md` gains a full two-direction reconciliation (§0) and sections on
  per-device `id` gating, energy reporting, TOU, and the 211 fan-out.

### Known limits
- `1303`'s `p_load` series is a byte-identical copy of `p_fhp`, and there is no `p_sun`
  series — so per-interval load and solar history are unavailable locally. Poll `1301`
  instead (storage belongs in the bridge).
- Reserve SoC, per-block TOU dispatch, and BMS "Layer 2" (thermal sensors, `balanState`)
  remain cloud-only.


### Packaging
- Distribution renamed to **`franklinwh-direct-connect-api`** for PyPI (import path stays
  `franklinwh_local`; CLI command stays `franklinwh-local`).
- Rounded out project metadata/URLs; added a build-and-validate release workflow
  (publishing is held while the repository is private).

### Notes
- The library is intentionally **thin and stdlib-only** — a faithful client for the local
  sendMqtt protocol, not a cloud-shaped abstraction. Cross-channel unification belongs in a
  separate bridge (see `PLAN_docker.md`); cloud equivalence is documented in
  `docs/CLOUD_MAPPING.md`.

## [0.1.0]

Initial library + CLI for the FranklinWH aGate local broker protocol (TCP/9000 sendMqtt
`cmdType` frames):

- `LocalClient` / `LocalTransport` — login, request/response, reconnect-retry for flaky wifi.
- Command **catalog** with cloud-API annotations; pcap decode/analyze; discovery `scan`;
  in-process emulator for hardware-free tests.
- CLI: reads (`power_flow`, `mode`, `der_comms`, `firmware`, `health`, `grid_profile`, …),
  verified writes (`mode --set`, `offgrid --set`), and `reboot` (with 4G warning + verify).
- Documented findings: reserved SoC is cloud-owned (read-only locally); write apply-timing
  is firmware-dependent; interface-level verification for writes.
