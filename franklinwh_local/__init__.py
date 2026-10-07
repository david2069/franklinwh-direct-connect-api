"""Deprecated alias of :mod:`franklinwh_direct_connect_api`.

The import package was renamed in 0.4.0 to match the distribution name and
FranklinWH's own term for this protocol, "Direct Connect". Importing
``franklinwh_local`` still works and returns the *same* module objects, so
``isinstance`` checks, subclassing and ``is`` comparisons across the two
spellings all hold.

This alias is scheduled for removal in **0.5.0**. To migrate::

    from franklinwh_local import LocalClient          # before
    from franklinwh_direct_connect_api import DirectConnectClient   # after

Set ``PYTHONWARNINGS=error::DeprecationWarning`` to find remaining uses.
"""
from __future__ import annotations

import importlib
import sys
import warnings

_NEW = "franklinwh_direct_connect_api"

warnings.warn(
    f"'franklinwh_local' was renamed to '{_NEW}' in 0.4.0 and will be removed in "
    f"0.5.0. Replace 'import franklinwh_local' with 'import {_NEW}' "
    "(and 'LocalClient' with 'DirectConnectClient').",
    DeprecationWarning,
    stacklevel=2,
)

_target = importlib.import_module(_NEW)

# Re-export the public surface, so `from franklinwh_local import X` works for
# every name the new package exports.
globals().update({n: getattr(_target, n) for n in _target.__all__})
__all__ = list(_target.__all__)
__version__ = _target.__version__

# Alias the submodules too, so `from franklinwh_local.catalog import CATALOG`
# and `import franklinwh_local.transport` resolve to the SAME module objects
# rather than loading a second copy (a second copy would give two distinct
# CATALOG dicts and break identity checks).
_SUBMODULES = (
    "bms", "catalog", "cli", "client", "discover", "emulator", "energy",
    "probe", "protocol", "proxy", "synthetic", "transport",
)
for _name in _SUBMODULES:
    _mod = importlib.import_module(f"{_NEW}.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
    globals()[_name] = _mod

del _name, _mod, importlib
