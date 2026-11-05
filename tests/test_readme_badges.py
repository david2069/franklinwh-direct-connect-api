"""README badges must point at things that exist.

A badge that 404s or shows red is worse than no badge: it reads as "the build is
broken" to anyone skimming. These checks are static — no network — so they fail in
CI the moment a workflow is renamed or the distribution name changes.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
# Everything above the first prose paragraph. `split("\n\n")` would stop at the
# blank line after the title and catch no badges at all -- which it did, and the
# licence assertion failed against an empty block rather than against the README.
BADGES = README[:README.index("This library is a")]


def test_every_workflow_badge_points_at_a_real_workflow():
    """The check the Bridge's own badge test makes, and the one that actually rots:
    a renamed workflow leaves a badge rendering a permanent red 'no status'."""
    referenced = set(re.findall(r"actions/workflows/([A-Za-z0-9_.-]+\.yml)/badge\.svg",
                                README))
    assert referenced, "no workflow badges found"
    present = {p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")}
    missing = sorted(referenced - present)
    assert not missing, f"badges point at workflows that do not exist: {missing}"


def test_every_workflow_has_a_badge():
    """The other direction — a new workflow should show up, or be deliberately left out."""
    present = {p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")}
    referenced = set(re.findall(r"actions/workflows/([A-Za-z0-9_.-]+\.yml)/badge\.svg",
                                README))
    assert not sorted(present - referenced), (
        f"workflows with no badge: {sorted(present - referenced)}")


def test_pypi_badges_name_the_real_distribution():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        dist = tomllib.load(fh)["project"]["name"]
    for kind in ("pypi/v", "pypi/dm", "pypi/pyversions"):
        assert f"img.shields.io/{kind}/{dist}" in README, (
            f"{kind} badge missing or names the wrong distribution (expected {dist})")


def test_the_licence_badge_is_a_fixed_label_not_a_github_lookup():
    """GitHub detects this LICENSE as 'Other' because of the Additional Terms, so an
    automatic `github/license` badge would render 'Other' rather than MIT. A fixed
    label is accurate; the link still goes to the real text."""
    assert "img.shields.io/github/license" not in README, (
        "an automatic licence badge renders 'Other' for this repo — use a fixed label")
    assert "license-MIT" in README
    assert "](LICENSE)" in BADGES, "the licence badge must link to the licence itself"


def test_the_ci_badge_reports_pull_request_runs():
    """`ci.yml`'s push trigger is muted, so the default badge shows the last run on
    main -- a failure from 2026-09-19, frozen there ever since. Pinning the badge to
    `event=pull_request` makes it report the runs that actually happen.

    If the push trigger is restored, drop the `?event=` and delete this test."""
    import re
    from pathlib import Path
    ci = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    pushes_on_main = re.search(r"^\s*push:", ci.read_text(), re.M)
    if pushes_on_main:
        assert "ci.yml/badge.svg?event=pull_request" not in README, (
            "ci.yml runs on push again -- drop ?event=pull_request from the badge")
    else:
        assert "ci.yml/badge.svg?event=pull_request" in README, (
            "ci.yml does not run on push, so an unpinned badge shows a stale result")


def test_no_release_badge_without_releases():
    """A `github/v/release` badge renders red 'no releases' on a repo with none.
    This repo has them, so the rule is only that the badge must not be a bare
    lookup that can regress to red — the PyPI version badge is the source of truth."""
    assert "img.shields.io/github/v/release" not in README


def test_badges_sit_above_the_prose():
    """They belong at the top, before the proof-of-concept framing, or they read as
    decoration rather than status."""
    first_prose = README.index("This library is a")
    assert README.index("img.shields.io") < first_prose
