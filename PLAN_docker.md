# PLAN — franklinwh-local bridge (Home Assistant add-on + standalone)

> **PLAN ONLY. No code.** FEAT-DOCKER. **Modelled on `energipays-bridge`** (David's HA
> add-on for Energipays), which is the agreed reference for structure, Docker, MQTT/HA, and
> UI. Companion to `AGENT.md` / `PROTOCOL_DESIGN_REQUIREMENTS.md`.

## 0. Reference: energipays-bridge

`~/dev/Claude/Projects/energipays-bridge` is a mature HA add-on (+ standalone Docker) that
does exactly what we want. We copy its shape rather than invent one. (FWHAI/Homey is **not**
the model — its UI is bloated/unresolved.) What we take from it:

- **Dual-target Dockerfile** — `ARG BUILD_FROM=python:3.12-slim` default (standalone), HA
  supervisor overrides `BUILD_FROM` with arch-specific **alpine** bases (`build.yaml`). The
  Dockerfile supports both `apt-get` and `apk`. → resolves slim-vs-alpine: **both**.
- **HA add-on packaging**: `config.yaml`, `build.yaml`, `repository.json`, `icon.png`,
  `docker-entrypoint.sh`, ingress UI.
- **`integrations/` registry + pollers** — pluggable data sources (rest/modbus/sunspec/…).
  This *is* the hybrid-unified-API pattern.
- **Separate bridge package depending on a client lib** (energipays-bridge →
  energipays-client). We mirror: **`franklinwh-local-bridge` → `franklinwh-local-api`**.
- MQTT/HA discovery, `mqtt:want` broker auto-discovery, HA **notifications** (non-actionable
  — see non-goals), `read_only` option, PWA web UI.

### Two packages (parallels FWHAI + energipays)

| Package | Role | Distribution |
|---------|------|--------------|
| **franklinwh-local-api** | the library — `LocalClient`, transport, catalog, CLI (this repo). stdlib-only. | **PyPI** — reusable independently by the bridge, other HA/non-HA projects, or ad-hoc |
| **franklinwh-local-bridge** | HA add-on + standalone Docker; FastAPI/UI + MQTT/HA. depends on the published API. | private repo / HA add-on store (later PyPI/registry if made public) |

Publishing the API to PyPI is the point of the split: **max flexibility** — anyone can
`pip install franklinwh-local-api` and build on it without the bridge's web/MQTT weight.

## 1. What it is — the local leg of a hybrid unified API

A **Home Assistant add-on** (and standalone Docker image) named **`franklinwh-local-bridge`**
that polls the aGate over sendMqtt and exposes: a **FastAPI REST API + web UI** (via ingress)
and **MQTT with HA discovery**. It is the **local leg** of a hybrid unified API over
local + Modbus + cloud — each op routed to the channel that can do it (local: mode/off-grid/
reads; Modbus: power control; cloud: reserved SoC/TOU/VPP). The `integrations/` registry lets
the same bridge later add Modbus and cloud pollers → full unification.

**Packaging rule:** the **`franklinwh-local-api`** library/CLI stays **stdlib-only** and is
**published to PyPI** so it can be used independently (this repo, other HA/non-HA projects).
The bridge is a **separate package** (`franklinwh-local-bridge`) that `pip install`s the
published API — like energipays-bridge/energipays-client. Web/MQTT/UI deps live only in the
bridge.

## 2. Repo / package layout (mirrors FWHAI + energipays split)

**franklinwh-local-api** — the library (this repo, `franklinwh_local`): `LocalClient`,
transport, catalog, CLI. stdlib-only. Published to **PyPI** as `franklinwh-local-api`
(package/dist name; import path can stay `franklinwh_local`). No web/MQTT deps.

**franklinwh-local-bridge** — NEW separate repo (mirrors energipays-bridge):
```
franklinwh-local-bridge/
  Dockerfile                        # ARG BUILD_FROM=python:3.12-slim (HA overrides→alpine)
  build.yaml                        # HA arch bases: ghcr.io/home-assistant/{arch}-base-python:3.12-alpine…
  config.yaml                       # HA add-on manifest (ingress, options/schema, mqtt:want)
  repository.json / icon.png        # HA add-on store metadata
  docker-entrypoint.sh              # /data/options.json → env; then exec the app
  docker-compose.yml (+ .dev.yml)   # standalone run
  pyproject.toml                    # depends on franklinwh-local-api (from PyPI)
  src/franklinwh_local_bridge/
    cli.py            main.py       # entrypoint + FastAPI app
    config/settings.py              # pydantic-settings (env + HA options)
    ha_options.py  ha_supervisor.py # HA add-on options + supervisor API (mqtt + notify)
    poller.py                       # periodic reads via franklinwh-local-api LocalClient
    integrations/  registry.py …    # local poller now; modbus/cloud later (unified API)
    publish/mqtt_publisher.py entities.py   # MQTT + HA discovery
    static/  templates/             # web UI (jinja2 + PWA)
```

## 3. Base image — RESOLVED (dual-target)

- **Standalone Docker**: `python:3.12-slim` (glibc/manylinux — reliable wheels).
- **HA add-on**: alpine arch bases via `build.yaml` (`…-base-python:3.12-alpine3.20`), chosen
  by the HA supervisor. The Dockerfile installs build prerequisites conditionally
  (`apt-get` vs `apk`) and uses musllinux wheels; skip `uvloop`.
- One Dockerfile, both targets — exactly the energipays-bridge pattern.

## 4. HA add-on manifest (config.yaml) — modelled fields

- `ingress: true`, `ingress_port: 8101` — web UI + REST served through HA ingress (sidebar
  panel; `panel_icon`/`panel_title`). Also `ports: 8101/tcp` for standalone.
- `services: ["mqtt:want"]` + `hassio_api: true` — **auto-discover the Mosquitto broker**
  (no manual MQTT typing). `homeassistant_api: true` for notifications.
- `map: [data:rw]` — persistent `/data` (cache, sqlite).
- `arch`: aarch64/amd64/armhf/armv7/i386.
- **options / schema**: `fwh_host`, `fwh_port` (9000), `poll_interval` (30), `timeout`/
  `retries`, `mqtt_enabled/host/port/username/password`, `log_level`, **`read_only` (true)**,
  `allow_writes` (false). Same shape as energipays-bridge's options block.

## 5. REST + UI — parity floor = FWHAI + FranklinWH Cloud API

FastAPI (auto OpenAPI `/docs`) + jinja2/PWA UI, served via ingress. Endpoints mirror the CLI
reads (`/api/health`, `/power`, `/mode`, `/der-comms`, `/firmware`, `/grid-profile`,
`/raw/{cmd}`). **Exposed surface (REST + HA entities) must be ≥ what FWHAI and the FranklinWH
Cloud API expose** (parity is the floor). Parity set to enumerate before the MQTT phase:
power/energy (grid/solar/battery/load/generator W + kWh), battery (SoC/SoH/capacity/limits/
temp), mode + per-mode reserve (read), status/health (run_status, relays, grid, :502,
firmware, availability), smart circuits, off-grid state.

## 6. MQTT + Home Assistant

- Publish periodic reads to `MQTT_PREFIX/…`; emit `homeassistant/.../config` discovery so
  entities auto-create (as energipays-bridge does), with an availability topic.
- Broker: reuse the **shared `fwhbridge-mosquitto`** broker the franklinwh-modbus-bridge uses
  (energipays-bridge's compose already points at it, host port 1886); in HA, auto-discovered
  via `mqtt:want`.
- **HA notifications** (via `homeassistant_api`, like energipays-bridge): simple push
  notifications on notable events (e.g. aGate unreachable / off-LAN, Modbus down). Zero
  user-supplied URL/token — routed through the add-on's own HA instance.

### Non-goals (avoid feature creep)

- **No actionable notifications** (buttons/reply). energipays-bridge deliberately skipped
  these to keep setup simple — we do the same. Plain notifications only.
- No cloud credentials in the local bridge (reserve routing to the cloud leg is a
  unified-API concern, Phase 5 — not part of the local bridge's own setup).
- No new conventions for mode/off-grid — reuse FWHAI + cloud CLI as-is.

## 7. Writes — read-only default; existing conventions only

`read_only: true` by default (add-on option). When `allow_writes` is set, only the
hardware-verified writes — **mode switch + off-grid** — exposed, **following existing FWHAI +
FranklinWH Cloud CLI conventions unchanged** (shared `tou`/`self`/`backup` aliases, same
shapes), with the same interface-level verification. **Reserve routes to the cloud leg.**
`reboot` is **never** exposed unattended (`DEF-WIFI-RECONNECT`: 4G-strand risk).

## 8. Dependencies (bridge package only)

`fastapi`, `uvicorn[standard]`, `jinja2`, `pydantic` + `pydantic-settings`, `paho-mqtt`,
`aiosqlite` (optional, local history), and **`franklinwh-local-api`** (from PyPI). The API
library itself gains **no** deps (stdlib-only) so it stays independently reusable.

## 9. CI & distribution (private repo)

- **No public registry** while private. Standalone via `docker-compose`; HA add-on installed
  from the private repo (`repository.json`). CI is **build-only** (validate build across
  arches); no publish. Keep `@pytest.mark.live` tests out of image CI.

## 10. Phased delivery (when approved)

| Phase | Deliverable |
|-------|-------------|
| 0 | `franklinwh-local-bridge` skeleton (mirror energipays layout); Dockerfile + compose + HA config.yaml/build.yaml; depends on franklinwh-local |
| 1 | FastAPI `/api/health` + read endpoints + OpenAPI; ingress web UI (jinja2/PWA) |
| 2 | Poller + MQTT publish + HA discovery (parity entity set); availability |
| 3 | Re-discovery, firmware/OTA-change detection, structured logs |
| 4 | (Optional) gated verified writes (mode/off-grid) per existing conventions |
| 5 | (Unified API) add Modbus + cloud pollers under `integrations/registry` |

## 11. Open items

- **Publish `franklinwh-local-api` to PyPI** (this repo) — packaging/name/dist metadata,
  release CI. Prereq for the bridge to `pip install` it. (Tracked separately as FEAT-PYPI.)
- New repo **`franklinwh-local-bridge`** to be created (separate from the API library).
- Enumerate the exact parity entity set from FWHAI + cloud (Phase 2 input).
