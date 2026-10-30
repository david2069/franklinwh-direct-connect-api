# Policy sources that bind this repository

*Adopted 2026-10-31, on the owner's instruction to keep this library in lockstep with the
Direct Connect Bridge and the FranklinWH Gateway Emulator, which his changes materially affect.*

**This file is a register, not a copy.** Every policy below lives in another repository and
is read from there. Nothing is vendored here, deliberately: the shared texts have **already
forked** (see [Known divergences](#known-divergences)), and a copy in this repo would be a
fifth version nobody reconciles. `CLAUDE.md` carries this repo's *reading* of these policies
— where the two disagree, **the source wins and `CLAUDE.md` is wrong and must be fixed.**

**Re-verify before relying on a clause.** Each row records the commit or date this repo last
checked. A row older than the work in hand is a claim about the past, not current policy.

## The register

| Policy | Source | Binds this repo | Last verified here |
|---|---|---|---|
| Change management (queue-first, S1–S4, batches) | `franklinwh-modbus` `.agents/policies/change_management.md`, effective 2026-03-18, branch `develop` | **Yes** — named as the source by `CLAUDE.md` | 2026-10-31 |
| Library release rules (changelog, traceability, commit IDs, PR checklist) | `franklinwh-modbus` `.agents/policies/release_policy.md`, branch `develop` | **Yes** — this is a library, and the Bridge's `CLAUDE.md` names this file as "the library's release rules" | 2026-10-31 |
| Hardware test protocol (never-write list, read-only default, results retention) | `franklinwh-gateway-emulator` `.agents/policies/hardware_test_protocol.md`, Rule 2 since commit `32a7af7`, 2026-10-13 | **Yes** — its own scope is "every read or write an agent makes against the owner's aGate (Modbus TCP, **Direct Connect**, or the bridges in front of them)" | 2026-10-31 |
| Issue policy (labels, milestones, `Refs #N`, lifecycle) | `franklinwh-modbus-bridge` `docs/issue-policy.md`, accepted 2026-10-16 | **Partly** — it scopes itself to "both bridges" and names them, so it does not govern this library's queue. `BACKLOG.md` is the queue here, as `in_flight_work.md` is in `franklinwh-modbus`. Its **`Refs #N` rule and its "defects always get an issue when found"** are followed when this repo files or references an issue | 2026-10-31 |
| Emulator coverage scope (what an emulator run verifies) | `franklinwh-gateway-emulator` `CLAUDE.md`, "Critical changes need real verification" | **Yes**, and it is **that repo's to state, not ours to copy** — ask it rather than trusting any copy | 2026-10-31 |
| PII / evidence standard | `franklinwh-cloud` and `franklinwh-gateway-emulator` `.agents/policies/pii_policy.md` (`AP-3`) and `evidence_standard.md` (`AP-14`) | **Unsettled** — see divergences. `CLAUDE.md`'s "What evidence can be published" and "Ground every claim in evidence" are this repo's operative rules meanwhile, and are at least as strict | 2026-10-31 |

## Known divergences

Recorded rather than resolved; resolving them is the owner's call, not this session's.

1. **Change management exists as two different texts.** The `AP-1` version is byte-identical
   in `franklinwh-cloud` and `franklinwh-gateway-emulator`. `franklinwh-modbus`'s version —
   the one this repo and the Bridge both name as *the* source — **differs from both** and
   carries no `AP` number.
2. **`AP-3` (PII) and `AP-14` (evidence standard) differ** between `franklinwh-cloud` and
   `franklinwh-gateway-emulator` despite identical filenames and `AP` numbers.
3. **The Bridge's citation for how the bridges learn of a library release does not resolve.**
   Its `CLAUDE.md` cites `release_policy.md` "§4 step 7" for this. That file has no numbered
   sections and no mention of a bridge, a notification, or telling anyone: its "Release
   Process" step 7 is `git push && git push --tags`. **There is therefore no written
   mechanism** by which this library tells the Bridge or the Emulator that something
   changed. `CLAUDE.md` "Lockstep with the Bridge and the Emulator" defines this repo's
   side of it; the shared policy still needs one.
4. **The Bridge records that `release_policy.md` did not exist** in
   `franklinwh-modbus` `.agents/policies/` on `develop` when it checked on 2026-10-17. It
   **does** exist there as of 2026-10-31 (verified on `develop`, alongside
   `change_management.md`). The Bridge's note is stale, not wrong for its date.
