"""The `franklinwh_local` import alias kept for 0.4.x.

Removal is scheduled for 0.5.0 — delete this file and the shim package together.
"""
import importlib
import sys
import warnings

import pytest

import franklinwh_direct_connect_api as new

OLD = "franklinwh_local"


def _fresh_import():
    """Import the alias from cold, so the module-level warning actually fires."""
    for name in [m for m in sys.modules if m == OLD or m.startswith(OLD + ".")]:
        del sys.modules[name]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = importlib.import_module(OLD)
    return mod, caught


def test_importing_the_old_name_warns_and_names_the_new_one():
    _, caught = _fresh_import()
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "importing the alias must raise DeprecationWarning"
    msg = str(dep[0].message)
    assert "franklinwh_direct_connect_api" in msg
    assert "0.5.0" in msg, "the warning must say when the alias goes"


def test_alias_exports_the_same_objects_not_copies():
    old, _ = _fresh_import()
    # Identity, not equality: two separately-loaded copies would give distinct
    # CATALOG dicts and break isinstance across the two spellings.
    assert old.LocalClient is new.DirectConnectClient
    assert old.LocalTransport is new.DirectConnectTransport
    assert old.CATALOG is new.CATALOG
    assert old.__version__ == new.__version__


def test_alias_covers_the_whole_public_surface():
    old, _ = _fresh_import()
    missing = [n for n in new.__all__ if not hasattr(old, n)]
    assert not missing, f"alias is missing: {missing}"


@pytest.mark.parametrize("sub", ["catalog", "protocol", "transport", "client", "emulator"])
def test_submodule_imports_resolve_to_the_same_module(sub):
    _fresh_import()
    old_sub = importlib.import_module(f"{OLD}.{sub}")
    new_sub = importlib.import_module(f"franklinwh_direct_connect_api.{sub}")
    assert old_sub is new_sub


def test_canonical_import_does_not_warn():
    for name in [m for m in sys.modules if m.startswith("franklinwh_direct_connect_api")]:
        del sys.modules[name]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("franklinwh_direct_connect_api")
    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]
