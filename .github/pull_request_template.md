## What changed

<!-- One or two sentences. -->

## Severity and nature

<!-- For a defect fix: sev:S1-blocker | sev:S2-high | sev:S3-medium | sev:S4-low,
     and nature:code | device | doc | test-gap | design-risk.
     Label the PR to match.

     These names match the severity table in CLAUDE.md ("Defect tracking and change
     management") and the labels in this repo. They previously read
     critical/major/minor/cosmetic, which matched neither -- so a PR author was asked
     for a severity that did not exist as a label and did not appear in the rules. -->

## Evidence

<!-- Per `CLAUDE.md`, "Ground every claim in evidence". Cite the source for every
     claim about what a field means or how the hardware behaves: a vendor document
     with its revision and date, a cookbook, a live read with its time and firmware,
     or the code. Say what is unverified. -->

## Mutation check

<!-- Required. "A test that passes with the fix disabled proves nothing."
     Disable the change, run the tests, and paste which ones failed: -->

Disabled the change; these tests failed:

## Verification

<!-- State the G0-G3 gates: which ran, which did not, and why. The library release
     policy (franklinwh-modbus .agents/policies/release_policy.md §3) requires that in
     the PR body: G0 full suite + syntax check on changed files; G1 acceptance run
     against an approved emulator; G2 the real aGate for writes/dispatch/safety; G3
     merge. Do not merge past a failed or skipped gate without the owner's word in
     your own session -- a relayed approval does not count.

     Then tick what applies below, and say what was NOT run.
  - [ ] Full test suite passes
  - [ ] Real hardware test on the reference aGate (say which clients were active,
        and verify any stop by socket count)
  - [ ] Approved emulator run — name the coverage-list version, the profile and the
        emulator commit, and say what that emulator does not model
  - [ ] Migration verified against a copy of the live database
  - [ ] Read-back verification done on hardware, not a simulator
-->

## Changelog

- [ ] `CHANGELOG.md` updated under `[Unreleased]`, or this change is not user-facing
      (internal refactor, tests, docs or policy only)

## Publishable evidence

- [ ] `python3 tools/pii_check.py` run — no new findings (no serials, MACs, LAN IPs,
      home paths, account identifiers or site captures; masked or `192.0.2.x`)
