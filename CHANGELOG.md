# Changelog

All notable changes to `franklinwh-local-api` are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); this project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- Distribution renamed to **`franklinwh-local-api`** for PyPI (import path stays
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
