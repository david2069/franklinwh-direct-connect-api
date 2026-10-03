# AP-3: Virtual Environment Policy

> All Python execution in this repository **must** use the project's dedicated
> virtual environment. This applies to agents, developers, and CI alike.

## The Rule

```
CORRECT:   /Users/davidhona/dev/franklinwh-local/.venv/bin/python
FORBIDDEN: /opt/homebrew/bin/python3
FORBIDDEN: /usr/bin/python3
FORBIDDEN: any python not inside .venv/
```

## Setup (one-time)

```bash
cd /Users/davidhona/dev/franklinwh-local

# Create the venv (if not already present):
python3 -m venv .venv

# Activate:
source .venv/bin/activate

# Install the package in editable mode + test dependencies:
pip install -e ".[test]"

# Optionally install docs dependencies:
pip install -e ".[docs]"
```

## Verification

Before running any Python command, verify the active interpreter:

```bash
which python    # → .../franklinwh-local/.venv/bin/python
which pytest    # → .../franklinwh-local/.venv/bin/pytest
python -c "import sys; print(sys.prefix)"  # → .../franklinwh-local/.venv
```

## Agent Enforcement

| Situation | Required Action |
|-----------|-----------------|
| `which python` does not show `.venv` | Activate the venv before proceeding. Do NOT run tests or install packages. |
| `pytest` not found | Run `pip install -e ".[test]"` inside the activated venv. |
| Asked to `pip install` a package globally | Refuse. Install inside the venv only. |
| System Python returned from `python3` shebang | Check `PATH`; ensure `.venv/bin` is first. |

## Why .venv Is Not in .gitignore (already excluded)

The `.venv/` directory is excluded from git via `.gitignore`. It is never
committed. Each developer/agent creates their own local venv from `pyproject.toml`.

## Test Commands (venv must be active)

```bash
# Full test suite (no hardware needed):
pytest tests/ -v --tb=short

# Explicitly skip live-hardware tests:
pytest tests/ -v --tb=short -m "not live"

# Single file:
pytest tests/test_client.py -v
pytest tests/test_protocol.py -v
pytest tests/test_emulator_scan.py -v
```

## CLI Commands (venv must be active)

After `pip install -e ".[test]"`, the CLI is on PATH:

```bash
franklinwh-local --help
franklinwh-local catalog
franklinwh-local -i 192.0.2.110 power_flow
franklinwh-local emulate --port 9000
```
