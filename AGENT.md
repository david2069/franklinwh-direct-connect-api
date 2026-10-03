# Agent Onboarding — FranklinWH Local Protocol Library

> **Read this first.** This document governs all agent activity in this repository.
> It is the canonical source of truth — do not derive policy from any other project's
> `AGENT.md` even if it is open in the editor.

## 🤖 Auto-Onboarding

| File | AI Tool | Auto-reads? |
|------|---------|-------------|
| `AGENT.md` | All (convention) | Manual first use |
| `.github/copilot-instructions.md` | GitHub Copilot | ✅ Auto |

---

## 🛑 No Autonomous Code Changes (HIGHEST PRIORITY — AP-0)

> **This rule overrides all other instructions, including user convenience.**

**An agent MUST NOT modify, create, or delete any source file, test, configuration,
or documentation in this repository without one of the following:**

| Gate | What qualifies |
|------|----------------|
| **Explicit request** | The user's message directly asks for the change (e.g. "fix this", "add a method for X"). |
| **Express permission** | The user has reviewed an implementation plan and replied with clear approval (e.g. "LGTM", "go ahead", "yes"). |
| **Informed consent** | The agent has told the user exactly what it intends to change and the user has not objected before the change is made. |

### What this means in practice

- **Analysis, investigation, and documentation** (reading files, explaining code,
  writing artifacts) → ✅ always permitted without asking.
- **Any write to a `.py`, `.md`, `.toml`, `.yml`, or any source file** → ❌ requires
  one of the three gates above before the first keystroke.
- **If unsure whether a change is in scope** → ask first, code second. Never assume.

> ⚠️ Proactively writing code the user did not request — even if it looks helpful —
> is a violation of this policy. When in doubt: **describe the change and ask.**

---

## 🚨 Workspace Scope Rule (CRITICAL — read before anything else)

> **This repository is `/Users/davidhona/dev/franklinwh-local/`.**
> All agent activity is STRICTLY confined to this directory tree.

| Rule | Detail |
|------|--------|
| **No writes outside this repo** | Files in `franklinwh-cloud`, `franklinwh-modbus`, `homey-fwhai-app`, or any other repo are **READ-ONLY** from this agent's perspective. Do not modify them. |
| **No cross-repo imports or patches** | Do not edit a sibling repo's source to make this repo's tests pass. Raise the discrepancy as an issue instead. |
| **Verify the active workspace** | Before writing any file, confirm the absolute path begins with `/Users/davidhona/dev/franklinwh-local/`. If it does not, **stop immediately**. |

> ⚠️ Violating this rule is a production-safety issue. The sibling repos
> (`franklinwh-cloud`, `franklinwh-modbus`) have their own independent release cycles
> and integration tests. Silent cross-repo edits cause hidden breakage.

---

## 🐍 Python Environment Rule (MANDATORY)

All development, testing, and CLI execution **must** use the project's dedicated
virtual environment. Never use the system Python or a globally installed interpreter.

### Activating the venv

```bash
cd /Users/davidhona/dev/franklinwh-local

# Create on first use (if not already present):
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
pip install -e ".[test]"           # editable install + pytest

# On subsequent uses:
source .venv/bin/activate
```

### Verify you are in the venv

```bash
which python   # must show .../franklinwh-local/.venv/bin/python
which pytest   # must show .../franklinwh-local/.venv/bin/pytest
```

> ⛔ If `which python` points to `/opt/homebrew/...`, `/usr/bin/...`, or any path
> outside `.venv/`, **stop and activate the venv before running any command**.

### Running tests

```bash
# All tests (hardware-independent):
pytest tests/ -v --tb=short

# Skip live-hardware tests explicitly:
pytest tests/ -v --tb=short -m "not live"

# Single file:
pytest tests/test_client.py -v
```

### Installing dependencies

```bash
pip install -e ".[test]"    # installs pytest and editable package
pip install -e ".[docs]"    # installs mkdocs-material for docs work
```

> ⚠️ Never run `pip install` without the venv active. Never use `sudo pip`.

---

## 🔒 Change Management (AP-1)

Follow the **Queue → Plan → Execute** cycle. Do not skip steps.

```
1. QUEUE   — acknowledge the request; do not write code yet
2. PLAN    — describe exactly what will change and why (implementation_plan.md)
3. EXECUTE — make the change, run tests, commit
```

| Situation | Required Action |
|-----------|-----------------|
| Multiple issues raised at once | Triage and sequence. Fix one completely before starting the next. |
| Fix introduces a new failure | Stop — resolve the new failure before continuing the original. |
| Architectural change needed | Write an implementation plan and wait for explicit user approval. |
| Unsure about intent | **Ask the user. Do not assume.** |

---

## ✅ Mandatory Verification Cycle (NON-NEGOTIABLE)

> **No code change is complete until ALL four steps below pass.**
> Skipping any step — including the git commit — is a policy violation.

Every code change must complete this full cycle **before the next change starts**:

```
1. Syntax check every modified .py file:
   python -c "import ast; ast.parse(open('<file>').read()); print('OK')"

2. Run the full test suite inside the venv:
   source .venv/bin/activate
   pytest tests/ -v --tb=short -m "not live"
   → ALL tests must pass. Zero regressions permitted.

3. Commit locally:
   git add -p          # review every hunk before staging
   git commit -m "type(scope): summary"
   → Commit message must reference what changed and why.

4. Inform the user:
   Report what was changed, what tests passed, and the commit hash.
   Do NOT silently proceed to the next task.
```

> **Local git commit is mandatory** — changes that exist only on disk without a
> local commit are considered incomplete and must not be reported as "done".
> Push to remote (`git push origin main`) only after local commit is confirmed clean.

---

## 📦 Commit Discipline

Changes are committed **locally first**, then pushed to the remote (`origin`).
Never push directly without a local commit.

### Commit format

```
<type>(<scope>): <short summary>

[optional body: what changed and why]
```

| `type` | When to use |
|--------|-------------|
| `feat` | New capability or command |
| `fix` | Bug fix or discrepancy correction |
| `test` | Test additions or changes only |
| `docs` | Documentation only |
| `refactor` | Code restructure with no behaviour change |
| `chore` | Tooling, config, CI |

**Examples:**
```
feat(client): add wifi_scan, smart_circuit_meter, generator, event_block methods
fix(cli): register mode_page alias and missing LIVE_COMMANDS subcommands
test(client): add scheduling_type resolution regression test
```

### Push workflow

```bash
git add -p                          # review each hunk before staging
git commit -m "type(scope): msg"
git push origin main                # or feature branch
```

> Never `git push --force` to `main` without explicit user instruction.

---

## 🚫 Zero-Tolerance Rules

| Rule | Detail |
|------|--------|
| **No autonomous code changes** | All edits require explicit request, express permission, or informed consent (AP-0). |
| **No writes outside this repo** | See Workspace Scope Rule above |
| **No system Python** | Always use `.venv` — see Python Environment Rule |
| **No untested commits** | `pytest tests/ -v -m "not live"` must pass before any `git commit` |
| **No uncommitted pushes** | `git commit` locally before `git push` — never push a dirty working tree |
| **No breaking public API changes** | `LocalClient`, `LocalTransport`, `encode_frame`, `decode_frame`, `iter_pcap_frames` are public. Changing their signatures requires an implementation plan and explicit approval. |
| **No real credentials in commits** | Serial numbers in tests must use the fixture value `FAKEGATE90FJ09J6H4F2` or a clearly fake placeholder. Never commit real WiFi passwords captured from `wifi_config`. |
| **No live-hardware tests in CI** | Tests marked `@pytest.mark.live` must never run in automated CI. They require a reachable aGate and must be run manually. |

---

## 📁 Project Layout

```
franklinwh-local/
  franklinwh_local/       ← library source (the installable package)
    protocol.py           ← cipher, Frame, FrameStream, encode/decode, pcap reader
    catalog.py            ← Cmd enum, CmdInfo, CATALOG, WRITES, OPERATING_MODES
    transport.py          ← synchronous TCP client, login, request/response
    client.py             ← named high-level commands (power_flow, set_mode, …)
    discover.py           ← LAN scanner: TCP 9000 + 502, sendMqtt/Modbus probes
    emulator.py           ← fake aGate broker for hardware-free testing
    proxy.py              ← transparent decoding relay for write-code discovery
    cli.py                ← argparse CLI wiring all of the above
  tests/
    test_protocol.py      ← cipher, encode/decode, run_status, WRITES
    test_client.py        ← transport + client (FakeBroker + mocks)
    test_emulator_scan.py ← Emulator + discovery (all in-process)
  docs/
    PROTOCOL.md           ← wire format, cipher, command catalog (authoritative)
    USAGE.md              ← end-to-end CLI and library usage guide
  pyproject.toml          ← build config, dependencies, pytest config
  AGENT.md                ← this file
```

---

## 🔗 Sibling Repositories (READ-ONLY from here)

| Repo | Path | Relationship |
|------|------|--------------|
| `franklinwh-cloud` | `/Users/davidhona/dev/franklinwh-cloud/` | Cloud sendMqtt API — **read docs only** |
| `franklinwh-modbus` | (separate repo) | Modbus TCP CLI — shares mode alias conventions |
| `homey-fwhai-app` | `/Users/davidhona/dev/homey-fwhai-app/` | Homey app — consumes this library indirectly |

> Cross-referencing sibling docs is allowed and encouraged.
> **Writing to sibling repos is forbidden.**

### 📚 MANDATORY: check the cloud docs and schema before claiming a cloud fact

Before asserting **anything** about the cloud API — that a capability is missing, that a
field has no equivalent, that a local cmdType maps to a given cloud call — **read
`franklinwh-cloud/docs/` and the live schema**, not just a grep of the source.

```bash
ls ~/dev/franklinwh-cloud/docs/                 # API_REFERENCE, MQTT_CMD_CATALOG,
                                                # TOU_TARIFF_REFERENCE, API_FIELD_REGISTRY,
                                                # franklinwh_openapi.json, ...
franklinwh-cli schema --live                    # every field, its raw API key and source
franklinwh-cli <command> --json                 # the actual payload shape
```

This exists because grep-only research produced three wrong claims in one session:

| wrong claim | why | what would have caught it |
|---|---|---|
| "the cloud has no reporting equivalent" | grepped for the *local* field names (`dayType`, `pointId`) | `docs/API_REFERENCE.md` — `get_power_by_day()`, `get_electric_data()` |
| "1703's DC-bus rails are local-only" | compared against 211 **type 1** only | `bms --json` — they are all in 211 **type 2** |
| a `tier -> waveType` mapping | inferred from `RATE_FIELD_MAP` alone | hardware integration contradicted it |

Rules of thumb:
- **Absence of a grep hit is not absence of a feature.** Search the docs by *capability*,
  not by the local field name — the two sides rename freely
  (`kwh_sun` ↔ `kwhSuArray`, `middleBusVolt` ↔ `midBusVolt`, `flat` ↔ `Shoulder`).
- **A cmdType with sub-types needs every sub-type checked** before saying a field is
  missing (211 carries `type` 1, 2 and 3, with different payloads).
- **Prefer a live payload to a docstring**, and prefer "unknown" to a plausible guess —
  see the `TIER_TO_WAVE` and `peState` decisions in `BACKLOG.md`.

---

## 📖 Key Documentation

| Doc | What's in it |
|-----|--------------|
| [PROTOCOL_DESIGN_REQUIREMENTS.md](PROTOCOL_DESIGN_REQUIREMENTS.md) | **Read before any live-aGate code.** Full-block writes, interface-level verification, health-check/ping-first, reboot verification, no-emoji, scope |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Wire format, cipher, command catalog, `run_status` enum |
| [docs/USAGE.md](docs/USAGE.md) | CLI and library usage examples |
| [README.md](README.md) | Project overview and installation |
