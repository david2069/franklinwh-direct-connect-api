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
| Library release and test gates (G0–G3, release procedure, changelog) | `franklinwh-modbus` `.agents/policies/release_policy.md` — **"Release and Test Gates Policy", effective 2026-10-17**, on `origin/develop` (verified at `4fa2b06`; the file itself last changed in `a090539`) | **Yes** — this is a library, and the Bridge's `CLAUDE.md` names this file as "the library's release rules" | 2026-10-31, **after a stale-checkout correction — see note below** |
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
3. ~~The Bridge's citation for how the bridges learn of a library release does not
   resolve.~~ **WITHDRAWN 2026-10-31 — this was my error, not a divergence.** I read
   `release_policy.md` from a **stale local checkout** (`HEAD` at `8af8301`) and reported
   its contents as current. `origin/develop` was at `4fa2b06`, and the file there is a
   different document: *"Release and Test Gates Policy"*, effective 2026-10-17, with
   numbered sections 1–5. **§4 step 7 exists and reads:** "**Tell the dependants.** Message
   the bridge sessions with the version and the upgrade notes. They decide when to move
   their pin." So the mechanism was written all along, it binds this repo, and the Bridge's
   citation was correct. Corrected after the Direct Connect Bridge session challenged the
   claim and named the commit; verified against `origin/develop` here before withdrawing.

   **The lesson, which is the point of keeping this note:** a path that exists is not a
   file you have read. `git fetch` first, and record the **ref** a policy was read at, not
   just its date — which is why the register column now names a commit.
4. **The Bridge records that `release_policy.md` did not exist** in
   `franklinwh-modbus` `.agents/policies/` on `develop` when it checked on 2026-10-17. It
   **does** exist there as of 2026-10-31 (verified on `develop`, alongside
   `change_management.md`). The Bridge's note is stale, not wrong for its date.


## Superseded text, and what this repo wrongly adopted from it

The version of `release_policy.md` at the stale checkout above was an earlier, different
document ("Agent Release Policy") carrying a **"Traceability — Mandatory Rules"** section
that required `fix(DEF-<AREA>-<NAME>): …` commit subjects and `Tests: N passed` in the body.
**The current policy has no such section**, so those are *not* inherited requirements.

This repo keeps both as **its own local convention** — a defect ID in the subject makes a
`BACKLOG.md` entry traceable to the commit that closed it, and the test count is cheap to
write and useful to a reader. They are recorded in `CLAUDE.md` as this repo's convention,
**not** as a rule imposed by the library release policy, because claiming the latter would
be citing a superseded file.

## What the current policy actually requires of this repo

Read §3 and §4 there; in brief, and binding:

- **G0** — the full test suite and a syntax check on every changed file, every PR, with
  results in `tests/results/` (gitignored here too).
- **G1** — an acceptance run against an approved emulator, for changes touching connection,
  reads, dispatch or modes. Unlike `franklinwh-modbus`, **this repo does have an in-process
  `Emulator`**, which `CLAUDE.md` already treats as approved; the external FranklinWH
  Gateway Emulator remains the stronger form. Do not substitute a mock written for the test
  in hand.
- **G2** — the real aGate, coordinated with the owner, for anything that writes, changes
  dispatch, or alters safety behaviour.
- **G3** — merge, and *"the agent does not merge past a failed or skipped gate without the
  owner's word in this session. A relayed approval from another session does not count."*
- **Say which gates ran and which did not in the PR body.** This repo was not doing that
  before 2026-10-31.
- **§4 step 7 — tell the dependants** on every release: message the bridge sessions with the
  version and the upgrade notes; they decide when to move their pin.
