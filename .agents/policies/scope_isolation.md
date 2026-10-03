# AP-2: Scope Isolation Policy

> Prevents cross-repository contamination. Every agent working in
> `franklinwh-local` is bound by this policy for the lifetime of the session.

## The Boundary

```
WRITE PERMITTED:   /Users/davidhona/dev/franklinwh-local/**
READ  PERMITTED:   anywhere (for reference/cross-check)
WRITE FORBIDDEN:   anything outside the above path
```

## Sibling Repositories

The following repositories exist on disk and may be consulted for reference.
They are **strictly read-only** from the perspective of this agent session:

| Repo | Absolute path | Permitted operations |
|------|---------------|----------------------|
| `franklinwh-cloud` | `/Users/davidhona/dev/franklinwh-cloud/` | Read docs + source only |
| `franklinwh-modbus` | (separate path) | Read only |
| `homey-fwhai-app` | `/Users/davidhona/dev/homey-fwhai-app/` | Read only |

## Enforcement Checklist (run before every file write)

1. Does the target path start with `/Users/davidhona/dev/franklinwh-local/`?
   - YES → proceed
   - NO  → **STOP. Do not write. Raise the conflict with the user.**

2. Am I modifying a sibling repo's source to work around an incompatibility?
   - YES → **STOP. Document the incompatibility and raise it as an issue instead.**
   - NO  → proceed

3. Is the change backed by an explicit user request or approved implementation plan?
   - YES → proceed
   - NO  → **STOP. Queue the change and apply AP-1.**

## Why This Exists

The sibling repos have independent:
- Release cycles and changelogs
- Test suites and CI pipelines
- Users who consume them independently of this repo

Silent cross-repo edits cause hidden breakage that is extremely difficult to
trace. The only safe path is to treat sibling repos as third-party libraries:
read their documentation, but never write to their source.
