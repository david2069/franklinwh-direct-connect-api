"""The comparison document may only claim what THIS package does.

Owner, 2026-10-30: "some features claimed belong to the DC Bridge repo (originally it was
going to be all in one but was never built)". Two rows credited this library with a Home
Assistant integration and a "reference application" that are a separate project's — a
leftover of the abandoned single-package plan.

Every number in that table is checked here against the code rather than trusted, because a
comparison with someone else's project is exactly where an inflated claim does damage.
"""
import ast
import inspect
import pathlib

from franklinwh_direct_connect_api import WRITES, catalog, cli
from franklinwh_direct_connect_api.client import DirectConnectClient

DOC = pathlib.Path(__file__).resolve().parents[1] / "docs/LOCAL_API_COMPARISON.md"


def _table_claims() -> list[str]:
    """Rows where the 'this repo' column claims a capability."""
    out = []
    for line in DOC.read_text().splitlines():
        if line.startswith("|") and "✅" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and "✅" in cells[1]:
                out.append(cells[0])
    return out


def test_no_bridge_feature_is_claimed_as_this_librarys():
    """HA entities, MQTT discovery, a REST API and a web UI belong to the Direct Connect
    Bridge. This package has no such code — claiming them here is how a reader ends up
    installing the wrong thing."""
    for claim in _table_claims():
        low = claim.lower()
        for foreign in ("home-assistant", "home assistant", "mqtt", "rest api", "web ui",
                        "reference application"):
            assert foreign not in low, f"comparison claims {claim!r} for this library"


def test_the_bridge_is_named_as_a_separate_project():
    t = DOC.read_text()
    assert "franklinwh-direct-connect-bridge" in t
    assert "separate" in t.lower()


def test_the_counts_in_the_table_are_real():
    t = DOC.read_text()
    methods = len([n for n, _ in inspect.getmembers(DirectConnectClient, inspect.isfunction)
                   if not n.startswith("_")])
    assert f"{methods} public methods" in t, methods

    assert f"{len(catalog.CATALOG)} cmdTypes catalogued" in t, len(catalog.CATALOG)

    sub = next(a for a in cli.build_parser()._actions if getattr(a, "choices", None))
    assert f"{len(sub.choices)} subcommands" in t, len(sub.choices)

    src = (pathlib.Path(DirectConnectClient.__module__.replace(".", "/") + ".py"))
    tree = ast.parse((pathlib.Path(__file__).resolve().parents[1] / src).read_text())
    blocks = sum(1 for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and ast.get_docstring(n)) + (1 if ast.get_docstring(tree) else 0)
    assert f"{blocks} docstring blocks" in t, blocks


def test_the_write_count_matches_the_writes_table():
    assert f"{len(WRITES)} writes" in DOC.read_text().replace("six writes", "6 writes") \
        or "six writes" in DOC.read_text() and len(WRITES) == 6


def test_every_claimed_read_has_a_client_method():
    """Spot-check the capability rows against real methods, by the name the row implies."""
    names = {n for n, _ in inspect.getmembers(DirectConnectClient, inspect.isfunction)}
    for meth in ("power_flow", "login", "solar_pv", "battery_cells", "power_electronics",
                 "device_check", "energy_history", "energy_rollup", "tou_schedule",
                 "generator", "grid_profile", "der_comms"):
        assert meth in names, meth
