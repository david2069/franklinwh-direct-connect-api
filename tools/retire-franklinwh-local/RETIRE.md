# Retiring the `franklinwh-local` distribution on PyPI

Run these yourself — they need your PyPI token. **Order matters.**

## Background

`franklinwh-local` on PyPI only ever shipped **`0.1.0a0`**, a pre-release, so
`pip install franklinwh-local` has never resolved it without `--pre`. Nothing can be
depending on it. The point of this exercise is a correct landing page for anyone who finds
the old name, not rescuing installs.

`franklinwh-local-api` on PyPI is **not ours** — it belongs to `hAr1x` and is an async
Modbus TCP client. Leave it alone.

## Why a pointer release and not a delete

| | Effect |
|---|---|
| **Delete** | Irreversible. The version number is burned forever — you can never re-upload `0.1.0a0` — and pins, lockfiles and hashes break. PyPI also blocks re-registering deleted project names in many cases. |
| **Yank** | Reversible. `pip` skips a yanked release when resolving a range, but still honours an exact `==` pin. This is the mechanism designed for "don't use this any more". |
| **Pointer release** | A final version whose only job is to depend on the new package and say so on its PyPI page. |

So: **never delete.** Pointer first, then yank.

## Step 1 — publish the library 0.4.0

Merge the rename PR, then from the repo root:

```bash
rm -rf dist
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
.venv/bin/python -m twine upload dist/*
```

This also refreshes the PyPI page's URLs, which still point at the pre-rename repo.

Then tag it:

```bash
git tag -a v0.4.0 -m "0.4.0 — rename import package and CLI to Direct Connect"
git push origin v0.4.0
```

## Step 2 — publish the pointer

**Only after 0.4.0 is live**, otherwise the pointer's dependency cannot resolve.

```bash
cd tools/retire-franklinwh-local
rm -rf dist
../../.venv/bin/python -m build
../../.venv/bin/python -m twine check dist/*
../../.venv/bin/python -m twine upload dist/*
```

It ships **no modules** deliberately: `franklinwh-direct-connect-api` 0.4.0 already provides
the `franklinwh_local` shim, and two distributions owning the same import package would
conflict on install.

Verify in a throwaway venv:

```bash
python3 -m venv /tmp/t && /tmp/t/bin/pip install franklinwh-local
/tmp/t/bin/python -c "import franklinwh_direct_connect_api as m; print(m.__version__)"   # 0.4.0
```

## Step 3 — yank the alpha

```bash
# Web UI: pypi.org → franklinwh-local → Manage → Releases → 0.1.0a0 → Yank
# Reason: "Renamed to franklinwh-direct-connect-api"
```

After this, `pip install franklinwh-local` (with or without `--pre`) resolves to `0.1.0`,
the pointer, which installs the real library.

## Do not

- Delete either distribution or any release.
- Touch `franklinwh-local-api` — not ours.
- Free up the GitHub repo names `franklinwh-local` or `franklinwh-direct-connect`: they
  currently redirect to `franklinwh-direct-connect-api`, and that redirect dies the moment
  another repo claims the name. Same for `franklinwh-local-bridge`.
