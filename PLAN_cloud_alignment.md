# PLAN — Aligning `franklinwh-local` to the `franklinwh-cloud` OpenAPI

> **Status: PLAN ONLY. Do not implement.** Queued as `EPIC-CLOUD-ALIGN` in
> [BACKLOG.md](BACKLOG.md). This document is a design proposal for review,
> not an approved work order. No code changes follow from it until explicitly
> approved.

## 1. Goal

Make the **local** (Direct-Connect / sendMqtt, TCP 9000, cmdType RPC) and the
**cloud** (HTTPS REST) APIs usable **interchangeably** — ideally the same method
names and the same response shapes regardless of which backend serves the call —
so a consumer (Home Assistant, Homey/FWHAI, scripts) can switch transports without
rewriting integration code. The cloud API is treated as the **canonical vocabulary**
because it already has an OpenAPI document and broader coverage.

## 2. Why this is not a 1:1 mapping

| Dimension | Local (this repo) | Cloud (`franklinwh-cloud`) |
|-----------|-------------------|----------------------------|
| Transport | Sync TCP 9000, encrypted JSON frames | Async HTTPS REST |
| Addressing | Integer `cmdType` (odd=req, even=rsp) | Named REST endpoints / method names |
| Contract | `CATALOG` dict + `PROTOCOL.md` (no formal spec) | `docs/franklinwh_openapi.json` |
| Granularity | Fine — one cmdType = one register block | Coarse — one endpoint may aggregate several |
| Values | Enums only (e.g. `ComplianceRuleType=9`) | Enum **+ resolved name** (`complianceRuleTypeName`, `country`) |
| Field casing | Mixed (`gridPowerUP`, `ES_V_LOW_AS`) | camelCase |

**Concrete non-1:1 examples:**
- Cloud `get_grid_profile_info(requestType=2)` ≈ local fan-out over
  `1211,1213,…,1229` **and** `1251–1277` (≈14+ cmdTypes).
- Cloud returns `complianceRuleTypeName`; local returns only `ComplianceRuleType`
  (int) — name must be synthesized client-side (see `DEF-GRID-PROFILE-REGION-LOCK`).
- Some local cmdTypes (e.g. `event_block` 1829, `ibg_state` 1827) have no obvious
  cloud endpoint; some cloud endpoints (utility-company search, geography lists)
  have no local equivalent (they are account/portal features, not device reads).

So alignment is a **semantic mapping with fan-out/fan-in**, not a rename.

## 3. Options considered

### Option A — Shared abstract interface (`FranklinWHClient` Protocol) in a new package
A transport-agnostic interface + normalized models, with `CloudClient` and
`LocalClient` implementations behind it.
- ➕ Cleanest interchangeability; consumers code to one interface.
- ➖ Needs a **shared models package** both repos depend on → cross-repo coupling.
  AGENT.md forbids editing sibling repos, so this must be a *new* standalone repo,
  not edits to cloud/local. Higher coordination cost.

### Option B — Cloud-shaped wrapper **inside** `franklinwh-local` (recommended core)
A new module `franklinwh_local/compat_cloud.py` exposing methods **named exactly
like the cloud client's** (`get_grid_profile_info`, `get_mode`, `power_flow`, …),
each orchestrating one-or-more local cmdTypes and **normalizing output to the cloud
OpenAPI response schema** (including synthesizing `complianceRuleTypeName` from a
local enum table). Raw `call()` and existing named methods stay untouched.
- ➕ Fully self-contained in this repo (AGENT.md-compliant, no sibling edits).
- ➕ Delivers "call it like the cloud" immediately; cloud OpenAPI becomes the test oracle.
- ➖ Duplicates method names; must track cloud API drift (mitigated by contract tests).

### Option C — Author a **local OpenAPI 3.1 spec** (recommended companion)
Describe the local API as logical operations in an OpenAPI document, using a
synthetic path scheme and **vendor extensions** to capture the cmdType fan-out:
```yaml
paths:
  /grid-profile:
    get:
      operationId: get_grid_profile_info      # matches cloud method name
      x-franklinwh-cmdtypes: [1203, 1211, 1213, 1251, 1253, 1255, 1257, 1259,
                              1261, 1263, 1265, 1267, 1269, 1271, 1273, 1275, 1277]
      x-franklinwh-transport: sendmqtt-tcp-9000
      responses:
        '200': { content: { application/json: { schema: { $ref: '#/…/GridProfile' } } } }
```
- ➕ Gives us the missing machine-readable contract (see §6); formally documents the
  non-1:1 mapping; enables generated docs, typed clients, and contract testing.
- ➖ OpenAPI is HTTP-shaped; the local protocol is RPC — the paths are synthetic.
  Acceptable: `operationId` + `x-franklinwh-*` carry the real semantics.

## 4. Recommendation

**Do C then B, keep A as a future north-star.**

1. **Author the local OpenAPI spec (C)** — `docs/franklinwh_local_openapi.json`.
   `operationId`s mirror cloud method names where a semantic equivalent exists;
   `x-franklinwh-cmdtypes` records the fan-out; schemas mirror the cloud schemas so
   the two specs can be diffed. Independently valuable as documentation.
2. **Build the cloud-shaped wrapper (B)** — `franklinwh_local/compat_cloud.py`,
   validated against BOTH OpenAPI specs (its output must satisfy the cloud response
   schema). Enum→name lookups (e.g. `ComplianceRuleType`) live in a small
   `franklinwh_local/enums.py`.
3. **Later, if true cross-backend swapping is wanted (A)** — extract the shared
   `Protocol` + models into a new `franklinwh-unified` repo that depends on both
   `franklinwh-local` and `franklinwh-cloud`. Recommended over coupling either base
   library. **This is the "new fork" the request asks us to consider** (see §5).

## 5. Deprecation / sunset / fork policy

Per the request, we do **NOT** deprecate the original cmdType endpoints now.

- **Additive, non-breaking:** the compat layer and OpenAPI are new surfaces; the raw
  `call(cmdType, …)` API and existing named methods (`power_flow`, `set_mode`, …)
  remain first-class and unchanged.
- **Sunset (only if we ever converge on the compat layer):** announce in `CHANGELOG`
  + emit `DeprecationWarning` for ≥2 minor releases before any removal; never remove
  in a patch release. No sunset clock starts without an explicit decision.
- **Fork option (recommended for interchangeability):** rather than sunsetting local's
  native API, publish the unified interface as a **separate package** (`franklinwh`
  or `franklinwh-unified`). Base libraries stay pure and independently released; the
  unified package owns the "interchangeable" promise. This avoids bloating either
  base library and sidesteps the AGENT.md workspace-isolation constraint.

**Suggestion:** favor the **new-package fork** for Option A over an in-place sunset —
it isolates churn, lets local/cloud keep their own release cadence, and gives
consumers a clear opt-in.

## 6. Sub-item: `catalog` CLI — add a Cloud-API-equivalent column

Today `franklinwh-local catalog` (`cli.py:_cmd_catalog`) prints, with **no headers**:
```
  1203  -> 1204   grid_policy          Grid compliance policy: … [cloud: get_grid_profile_info(requestType=1)]
```
The cloud equivalent is buried **inline in the description string**. Plan:
1. Promote it to a first-class field on `CmdInfo` — `cloud_api: str | None` (e.g.
   `"get_grid_profile_info(requestType=1)"`, `"(fan-out)"`, or `None`).
2. Print a real table **with headers** and a dedicated column:
   ```
   LOCAL_REQ  LOCAL_RSP  NAME                 CLOUD_API_EQUIVALENT              DESCRIPTION
   1203       1204       grid_policy          get_grid_profile_info(type=1)    Grid compliance policy: …
   1251       1252       grid_compliance_main get_grid_profile_info(type=2) *  ComplianceRuleType(9=AU/NZ) …
   ```
   `*` = many-local-to-one-cloud (fan-out); `—` = no cloud equivalent.
3. Add `catalog --json` so the mapping is machine-readable (feeds §3-C generation).

> **Design note answering the request's question:** `catalog` is a **CLI-only view**
> over the `CATALOG` dict in `catalog.py`. There is no separate "local API definition"
> object — `CATALOG` (the dict) + `docs/PROTOCOL.md` (the wire format) ARE the local
> API's definition. The CLI subcommand merely renders that dict. That is exactly why
> no OpenAPI exists yet (see §7).

## 7. Do we have OpenAPI/Swagger for the local API? (No — why, and the fix)

**No local OpenAPI exists** (`find -iname '*openapi*'` → only the cloud's). Reasons:
1. The local API is an **RPC binary protocol over TCP 9000** (encrypted JSON frames
   keyed by integer `cmdType`), not HTTP/REST — OpenAPI is HTTP-oriented, so it was
   never the natural description format.
2. The protocol was **reverse-engineered incrementally** from pcaps; the `CATALOG`
   dict became the de-facto machine-readable source of truth instead of a formal spec.
3. The cloud repo got an OpenAPI cheaply because it IS real HTTP (HAR → OpenAPI).

**Why we should have one anyway** and how (this is §3-Option C):
- A machine-readable contract unlocks generated docs, typed clients, and — crucially
  for this epic — **contract tests that diff local responses against the cloud
  schema**, which is the mechanism that keeps the two APIs aligned over time.
- Feasible via OpenAPI 3.1 with synthetic paths + `x-franklinwh-cmdtypes` /
  `x-franklinwh-transport` vendor extensions to encode the RPC/fan-out reality.
- The `catalog --json` output (§6-3) is the natural seed for generating it.

## 8. Phased delivery (when approved — not now)

| Phase | Deliverable | Depends on |
|-------|-------------|------------|
| 0 | `CmdInfo.cloud_api` field + `catalog` headers/column + `--json` (§6) | — |
| 1 | `docs/franklinwh_local_openapi.json` seeded from `catalog --json` (§3-C, §7) | 0 |
| 2 | `franklinwh_local/enums.py` (ComplianceRuleType→name, etc.) + resolve `DEF-GRID-PROFILE` accessor | 1 |
| 3 | `franklinwh_local/compat_cloud.py` cloud-shaped wrapper (§3-B) | 1, 2 |
| 4 | Contract tests: compat output validated against cloud OpenAPI schema | 3 |
| 5 | (Optional) `franklinwh-unified` fork exposing Option-A Protocol | 3, 4 |

## 9. Open questions for the user

1. Confirm the **canonical vocabulary** is the cloud method names (assumed yes).
2. Interchangeability scope: response-shape parity only, or also **writes**
   (`set_mode`, reserves, off-grid) mapped through the same facade?
3. Option-A fork: greenlight a **new `franklinwh-unified` repo**, or keep the compat
   layer inside `franklinwh-local` only for now?
4. How closely must the local OpenAPI **schema names** mirror the cloud spec (exact
   field-name parity vs. documented mapping)?
