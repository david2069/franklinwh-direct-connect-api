# Go-Public Runbook — `franklinwh-local` + `franklinwh-local-bridge`

Formal procedure for open-sourcing both repos with a hard requirement: **no PII in
the public repos — current tree *or* history.** Written 2026-09-20. Execute the
checklists *after* the pending updates/fixes are merged, in the order below.

> Keep the existing repo names/URLs: `github.com/david2069/franklinwh-local` (the PyPI
> package `franklinwh-local-api` and the public `franklinwh-cloud` repo both link to it)
> and `github.com/david2069/franklinwh-local-bridge`.

---

## 1. Audit summary (what's clean, what must be scrubbed)

Full-history audit run 2026-09-20.

**Clean — no action (verified):**
- **No credentials were ever committed** to either repo — the cloud password, Home-
  Assistant long-lived tokens, `.env`, and the `data/` volume (SQLite `metrics.db`,
  `overrides.json`) are all gitignored and absent from all history.

**Must be scrubbed before public (device-identifying PII):**
| Item | franklinwh-local | franklinwh-local-bridge |
| --- | --- | --- |
| Real aGate / aPower **serials** | history only — bundled captures **removed** from the tree | 2 history commits |
| Real **LAN IPs** (the home subnet, esp. the aGate's address) | tree + history (code/tests/docs) | tree + history (README, `docker-compose.yml` default, a design doc, tests) |
| Real **Wi-Fi MAC** address | — | one test fixture |
| **Location / model hint** (e.g. country + model code) | — | one design doc |
| **LICENSE** file | present (MIT) ✅ | **missing — add MIT** |

> The `franklinwh-local` working tree is now fully PII-clean: the bundled captures
> (`writes.pcap`, `fwh.pcap`, `fhp_wifi_ap.pcap`) were **removed** — the emulator is
> synthetic-only and captures are recreated on demand (see below). Only *history* still
> carries the old serials, which the squash baseline collapses.

---

## 2. Recommended approach — clean-history baseline, same URL

Because history carries PII across many commits (including the now-removed capture blobs,
which hold the serial in a form grep can't see), the reliable "no PII, ever" guarantee is
to **publish from a clean baseline** rather than expose the full private history:

**Primary (recommended): squash to a single clean root commit, in place.**
1. Fully scrub the working tree (steps 3–4).
2. Replace history with one clean commit on a fresh orphan branch, force-push to `main`.
3. Verify zero PII across **all** blobs (step 6), then flip visibility (step 5).

This keeps the repo URL, guarantees no PII in public history (there is no old history),
and — because both repos have only ever been **private** (no forks/external clones) — the
only residual is GitHub's internal object cache, which is low-risk and can be purged via
GitHub Support if desired.

**Alternative: `git filter-repo` (preserves granular history).**
Surgically rewrite every blob (`--replace-text` for the IPs/MAC/serials, plus regenerate
or drop the pcaps), then force-push. Preserves history but is fiddly and harder to *prove*
exhaustive; if chosen, back up with a bundle first and request a Support cache purge after.

*If preserving history isn't important for a reverse-engineering project, prefer the
squash — keep the private repo as the full-history archive.*

---

## 3. Pre-flip checklist — `franklinwh-local`

- [x] **Bundled captures removed** — `writes.pcap` / `fwh.pcap` / `fhp_wifi_ap.pcap` are
      gone from the tree; the emulator is synthetic-only and the tests no longer need a
      fixture. Recreate a capture on demand when needed via `franklinwh-local proxy` or
      `tcpdump -w`. (Done 2026-09-20 — the tree is now PII-clean.)
- [ ] **Scrub real LAN IPs** in `franklinwh_local/` (`cli.py`, `discover.py`, `proxy.py`)
      and `tests/` → a documentation placeholder (e.g. `192.0.2.x`, the RFC 5737 doc range,
      or the hotspot default `10.100.1.1`). Keep `127.0.0.1` (loopback, fine).
- [ ] Confirm README/CHANGELOG read well for a public audience; LICENSE already MIT.
- [ ] Restore the `push:` CI trigger (muted 2026-09-20) once the Actions budget resets
      (2026-10-01) — public repos get unlimited Actions.
- [ ] Squash to a clean baseline (step 2) and run the verification sweep (step 6).

## 4. Pre-flip checklist — `franklinwh-local-bridge`

- [ ] **Add a LICENSE** (MIT, matching the library).
- [ ] **Scrub the real aGate IP and other real LAN IPs** → placeholders in: `README.md`,
      `docker-compose.yml` (the `FWH_HOST` default), `docs/SMART_CIRCUITS_DESIGN.md`,
      `templates/tabs/settings.html` (input placeholder), and the `tests/` fixtures.
- [ ] **Scrub the real Wi-Fi MAC** in the cloud-compat test fixture → a fake MAC.
- [ ] **Remove the location/model hint** (country + model code) from the design doc, or
      generalise it.
- [ ] Scrub the real serial from the 2 history commits (handled by the squash baseline).
- [ ] Confirm `.env` and `data/` remain gitignored and untracked (already verified).
- [ ] Add CI workflows if wanted (free once public) — reuse the library's trimmed ones.
- [ ] Squash to a clean baseline (step 2) and run the verification sweep (step 6).

---

## 5. The flip (per repo, after steps 3–6 pass)

1. Make public: repo **Settings → General → Danger Zone → Change visibility → Public**
   (or `gh repo edit <repo> --visibility public --accept-visibility-change-consequences`).
2. **GitHub Pages** (docs) is now free — enable Pages (Settings → Pages → GitHub Actions)
   and trigger the `docs.yml` deploy (`workflow_dispatch`). The docs are also served by the
   bridge at `/guide`, so this is optional.
3. **Actions**: public repos have unlimited minutes — restore the `push:` triggers.
4. **PyPI**: the library is publish-ready (`franklinwh-local-api`); a `v*` tag runs the
   release workflow (trusted publishing). Only tag once the tree is scrubbed.

## 6. Verification sweep (must all return zero before flipping)

Run in each repo. Fill in your own real values locally; **do not commit them.**

```bash
# real serials (text AND binary), across ALL history:
git rev-list --all | while read c; do git grep -lI '' "$c" >/dev/null; done   # sanity
git log --all -S '<REAL_AGATE_SERIAL>'  --oneline | wc -l    # want 0
git log --all -S '<REAL_APOWER_SERIAL>' --oneline | wc -l    # want 0
# real LAN IPs / MAC (adjust to your values):
git log --all -S '<REAL_LAN_PREFIX>'      --oneline | wc -l    # want 0 (or only doc-range)
git log --all -S '<REAL_WIFI_MAC>'      --oneline | wc -l    # want 0
# binary (pcap) check on the current tree:
python3 - <<'PY'
import pathlib
BAD=[b"<REAL_AGATE_SERIAL>", b"<REAL_APOWER_SERIAL>"]
for p in pathlib.Path('.').rglob('*'):
    if '.git' in p.parts or not p.is_file(): continue
    d=p.read_bytes()
    for b in BAD:
        if b in d: print("PII in", p)
print("scan done")
PY
# credentials never present (should already be 0):
git log --all -S 'FWH_CLOUD_PASSWORD' --oneline | wc -l
git rev-list --all | while read c; do git grep -lE 'eyJ[A-Za-z0-9_-]{20,}' "$c" 2>/dev/null; done | sort -u
```

Only when every sweep is clean, in both repos, proceed to the flip (step 5).

---

*Note: this runbook intentionally contains no real serials, IPs, or MACs — fill them in
locally when running the verification sweep.*
