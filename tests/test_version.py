"""The package version must match the distribution version, and not drift.

`__version__` was a hand-maintained literal and sat at 0.4.0 while the published
distribution was 0.5.0 (DEF-VERSION-DRIFT), so anything reporting the library
version -- a bridge logging its dependency, a bug report, `health` output -- was a
release behind with nothing to catch it. `pyproject.toml` is now the single source
and the package reads it back through the installed metadata.
"""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

try:                                  # tomllib is stdlib only from 3.11
    import tomllib
except ModuleNotFoundError:           # pragma: no cover - exercised on 3.10 CI
    tomllib = None

import pytest

import franklinwh_direct_connect_api as pkg

DIST = "franklinwh-direct-connect-api"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _declared_version() -> str:
    """The version declared in pyproject.toml.

    `tomllib` arrived in Python 3.11 and this package supports 3.10, so a bare
    `import tomllib` here broke collection of the WHOLE suite on 3.10 -- the
    failure CI caught and a 3.14 dev venv could not. The regex fallback avoids
    taking a `tomli` dependency just to read one string in one test.
    """
    raw = PYPROJECT.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(raw)["project"]["version"]
    match = re.search(r'^version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
    assert match, "no version found in pyproject.toml"
    return match.group(1)


@pytest.mark.skipif(not PYPROJECT.exists(), reason="installed without the source tree")
def test_version_matches_pyproject():
    """The reported version is the declared one.

    A failure here means either the literal drifted again or this environment's
    editable install is stale -- reinstall with `pip install -e .` and re-run.
    """
    assert pkg.__version__ == _declared_version()


def test_version_comes_from_distribution_metadata():
    """Not a literal: it is whatever the installed distribution says it is."""
    assert pkg.__version__ == metadata.version(DIST)


def test_version_is_not_the_unknown_fallback():
    """The fallback is for an uninstalled source tree, not for normal runs."""
    assert pkg.__version__ != "0.0.0+unknown"
    assert pkg.__version__[0].isdigit()
