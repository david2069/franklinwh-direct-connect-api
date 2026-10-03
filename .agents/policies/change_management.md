# AP-1: Change Management Policy

> Consistent with franklinwh-cloud AP-1. Prevents cascading defects from
> reactive break-fix cycles and cross-repo contamination.

## AP-0: No Autonomous Code Changes (read first)

Before any code is written, the agent must have one of:

1. **Explicit request** — the user's message directly asks for the change.
2. **Express permission** — the user approved an implementation plan.
3. **Informed consent** — the agent described the change and the user did not object.

Analysis, reading files, and writing artifacts do **not** require permission.
Any write to a source file, test, or config does. **When in doubt: ask first.**

## Core Rule: Queue → Plan → Execute

**Never react to a new issue by immediately writing code.**

```
1. QUEUE   — acknowledge the request; log it
2. PLAN    — describe what will change and why
3. EXECUTE — make the change, verify, commit
```

## Anti-Arbitrary Change Mandate

Agents **MUST NOT** make arbitrary code or test changes not backed by explicit
requirements or concrete evidence. When in doubt: **STOP AND ASK THE USER.**

If a test fails, verify against the source of truth (pcap fixture, PROTOCOL.md,
or live hardware) before changing test expectations. Do not delete assertions
just to force a pass.

## Agent Enforcement

| Situation | Required Action |
|-----------|-----------------|
| User raises new issue during active fix | "Noted — queuing for after current fix." Do NOT switch context. |
| Multiple issues reported at once | Triage and sequence. Fix one completely before the next. |
| Fix introduces a new failure | Stop — resolve the regression before continuing. |
| Architectural change needed | Write an implementation plan; wait for explicit approval. |
| User proposes immediate ad-hoc change | Confirm scope; apply AP-1 reminder if needed. |

## Verification Cycle (Non-Negotiable)

Every code change must complete this cycle **in full** before starting the next:

```
1. Make change
2. Syntax check all modified .py files:
   python -c "import ast; ast.parse(open('<file>').read()); print('OK')"
3. Run tests (venv must be active):
   pytest tests/ -v --tb=short -m "not live"
4. Confirm zero new failures
5. Commit with a descriptive message (see AGENT.md commit format)
```

## Commit Discipline

- Commit after every meaningful change or phase
- Format: `type(scope): summary` (see AGENT.md for types)
- Never leave modified files uncommitted before starting the next task
- Local commit first; push to remote after local commit is clean
