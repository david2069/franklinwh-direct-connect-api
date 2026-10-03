"""
Payload-matrix cmdType prober.

Discovers *undocumented* request ``cmdType`` codes by sweeping a code range and,
for each code, trying several request payload shapes.

Why a matrix and not just ``{"opt": 0}``
----------------------------------------
Every local read this library performs is addressed to the aGate itself with
``{"opt": 0}``. But the cloud API's per-cell BMS read (``get_bms_info``) sends
its request cmdType with ``{"fhpSn": "<aPower serial>", "type": 2|3}`` — the
request is parameterised *per battery*, not per gateway. A code that requires
such a selector answers an ``{"opt": 0}`` probe with silence or an empty
envelope, which is indistinguishable from "this code does not exist".

The earlier one-shot ``probe_gaps.py`` scratch script only ever sent
``{"opt": 0}``, so it could not have found a parameterised read. This module
sweeps a payload matrix instead and reports *which shape* produced data.

This found the real thing: cmdType **1705** returns per-cell voltages and
temperatures, but only when the request carries ``{"id": N}``. Called with the
usual ``{"opt": 0}`` it returns the same key set with *empty arrays* — which
reads as "this code has no data" unless you happen to try the selector. The
selector turned out to be the small integer device ``id``, not the serial the
cloud API uses, so the shape matters more than the value.

See BACKLOG: RESEARCH-BMS-CELL-LOCAL, FEAT-CMDTYPE-RECONCILE.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from . import catalog
from .client import LocalClient
from .transport import TransportError

#: Keys every reply carries; data beyond these is a real payload.
ENVELOPE = frozenset({"opt", "result", "reason"})

#: Plausible per-cell voltage bands, as (low, high) in volts and in millivolts.
_CELL_BANDS = ((2.0, 5.0), (2000.0, 5000.0))

#: A cell series has at least this many members (aPower packs show 16).
_CELL_MIN_SERIES = 8

_SUFFIXED_KEY = re.compile(r"^(.*?)(\d+)$")

#: Markers that the session is gone rather than the request being refused.
_DISCONNECT_HINTS = ("closed by peer", "broken pipe", "reset by peer",
                     "not connected", "bad file descriptor")


def _is_disconnect(exc: Exception) -> bool:
    """True when the gateway dropped the session (vs refusing one request).

    The aGate closes the connection outright for cmdTypes outside the band it
    implements (roughly 1101-1909). In-band codes it does not implement are
    answered with ``result=1, reason=4`` on a healthy connection.
    """
    if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in _DISCONNECT_HINTS)


@dataclass
class ProbeResult:
    """Outcome of probing one ``cmdType`` with one or more payload shapes."""

    cmd_type: int
    #: hit      - reply carried data beyond the opt/result/reason envelope
    #: empty    - accepted (result=0) but no payload
    #: rejected - explicitly refused (result!=0); the aGate answers unimplemented
    #:            cmdTypes with {"opt":0,"result":1,"reason":4} rather than silence
    #: timeout  - no reply at all
    #: error    - transport/protocol failure
    status: str
    payload: dict | None = None       # the request shape that produced `data`
    data: dict | None = None          # the reply dataArea
    error: str | None = None
    attempts: list[dict] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.cmd_type in catalog.CATALOG

    @property
    def name(self) -> str:
        info = catalog.CATALOG.get(self.cmd_type)
        return info.name if info else f"cmdType {self.cmd_type}"

    @property
    def keys(self) -> list[str]:
        return sorted(set(self.data or {}) - ENVELOPE)

    @property
    def cell_series(self) -> list[str]:
        """Labels of numeric series in the reply that look like cell telemetry."""
        return find_cell_series(self.data) if self.data else []

    def summary(self) -> str:
        if self.status == "hit":
            shape = ",".join(sorted(self.payload or {})) or "-"
            cells = f"  CELL-LIKE:{','.join(self.cell_series)}" if self.cell_series else ""
            tag = "" if self.known else "  <-- NEW"
            rc = (self.data or {}).get("result")
            if rc not in (0, None):
                # Data came back, but the device still flagged an error — usually
                # "nothing in progress", so the fields are defaults, not live values.
                tag += f"  [result={rc} reason={(self.data or {}).get('reason')}]"
            return (f"{self.cmd_type:<6} HIT      [{shape}]  "
                    f"{len(self.keys)} keys: {', '.join(self.keys[:8])}"
                    f"{' …' if len(self.keys) > 8 else ''}{cells}{tag}")
        if self.status == "rejected":
            return f"{self.cmd_type:<6} rejected ({self.error}) — cmdType not implemented"
        if self.status == "empty":
            return f"{self.cmd_type:<6} accepted, no data (result=0, empty payload)"
        if self.status == "timeout":
            return f"{self.cmd_type:<6} timeout"
        return f"{self.cmd_type:<6} error    {self.error}"


def _numeric_series(data: dict) -> dict[str, list[float]]:
    """Numeric series in a payload: list values, and keys sharing a numeric suffix."""
    series: dict[str, list[float]] = {}
    for key, value in data.items():
        if isinstance(value, list) and len(value) >= _CELL_MIN_SERIES:
            nums = [v for v in value if isinstance(v, (int, float))
                    and not isinstance(v, bool)]
            if len(nums) >= _CELL_MIN_SERIES:
                series[key] = nums
    grouped: dict[str, list[float]] = {}
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        m = _SUFFIXED_KEY.match(key)
        if m and m.group(1):
            grouped.setdefault(m.group(1), []).append(float(value))
    for prefix, nums in grouped.items():
        if len(nums) >= _CELL_MIN_SERIES:
            series[f"{prefix}*"] = nums
    return series


def payload_score(data: dict | None) -> tuple[int, int]:
    """Rank a reply: (fields carrying real content, fields present).

    Key count alone is not enough. A per-device read called *without* its ``id``
    returns the SAME keys as a correct call, just empty — ``batVolt: []``,
    ``batSoc: 0``. Scoring on key count would rank the empty shell equal to the
    real payload and, being first, keep it. So count fields whose value is
    actually populated, and fall back to key count to break ties.
    """
    if not data:
        return (0, 0)
    keys = set(data) - ENVELOPE
    filled = 0
    for key in keys:
        value = data[key]
        if value in (0, "", None) or value == [] or value == {}:
            continue
        filled += 1
    return (filled, len(keys))


def find_cell_series(data: dict | None) -> list[str]:
    """Labels of series whose values all sit in a plausible cell-voltage band.

    A 16-member series of values clustered in 2.0–5.0 V (or 2000–5000 mV) is the
    signature of per-cell telemetry — the payload shape we are hunting for.
    """
    if not data:
        return []
    hits = []
    for label, nums in _numeric_series(data).items():
        lo, hi = min(nums), max(nums)
        if any(low <= lo and hi <= high for low, high in _CELL_BANDS):
            hits.append(label)
    return sorted(hits)


#: Device-index selectors to try. The aGate's own per-device reads (1703/1705/
#: 1833/1835) are keyed by this small integer ``id`` from devMap[].id — NOT by
#: the serial the cloud API uses. Finding 1705 (per-cell BMS telemetry) turned
#: on exactly this: it answers {"opt":0} with empty arrays and only fills them
#: in when the request names a device.
DEFAULT_IDS: tuple[int, ...] = (1, 2)


def default_payloads(serials: Sequence[str] = (),
                     ids: Sequence[int] = DEFAULT_IDS) -> list[dict]:
    """The payload matrix: plain read, per-device ``id``, then serial selectors.

    Order matters only for ``stop_on_hit``; with ``--all-shapes`` every shape is
    tried. ``id`` shapes come before the serial shapes because that is the
    convention the local channel actually uses.
    """
    shapes: list[dict] = [{"opt": 0}]
    for dev_id in ids:
        shapes.append({"opt": 0, "id": dev_id})
    for sn in serials:
        shapes.append({"fhpSn": sn})
        shapes.append({"fhpSn": sn, "type": 2})
        shapes.append({"fhpSn": sn, "type": 3})
        shapes.append({"opt": 0, "fhpSn": sn})
    return shapes


#: Token substituted with each discovered/supplied battery serial in --payload.
SERIAL_TOKEN = "%fhpSn%"


def expand_payloads(templates: Sequence[dict], serials: Sequence[str]) -> list[dict]:
    """Expand payload templates, substituting ``%fhpSn%`` with each serial.

    A template with no token is used verbatim. A template containing the token
    is emitted once per serial, so ``{"opt":0,"fhpSn":"%fhpSn%"}`` becomes one
    payload per battery.
    """
    out: list[dict] = []
    for tpl in templates:
        if SERIAL_TOKEN not in json.dumps(tpl):
            out.append(dict(tpl))
            continue
        for sn in serials or [""]:
            raw = json.dumps(tpl).replace(SERIAL_TOKEN, sn)
            out.append(json.loads(raw))
    return out


def discover_serials(client: LocalClient) -> list[str]:
    """aPower/FHP serials to use as ``fhpSn`` selectors.

    Sourced from 1831 ``battery_modules`` (devMap[].devSN) and the 1101 login
    manifest (FHP_SN / BMS_SN) — the local side already holds exactly the
    identifiers the cloud's BMS read wants.
    """
    serials: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value and value not in serials:
            serials.append(value)

    try:
        modules = client.battery_modules()
        for entry in modules.get("devMap") or []:
            if isinstance(entry, dict):
                _add(entry.get("devSN"))
    except (TransportError, OSError, TimeoutError, ValueError):
        pass

    try:
        manifest = client.firmware()   # re-logs in; returns the serial/version block
    except (TransportError, OSError, TimeoutError, ValueError):
        manifest = {}
    for key in ("FHP_SN", "BMS_SN"):
        _add(manifest.get(key))
    return serials


def gap_codes(start: int = 1101, end: int = 1909, *, include_known: bool = False) -> list[int]:
    """Odd request codes in ``[start, end]``; unconfirmed ones by default.

    Known codes are derived from ``catalog.CATALOG`` rather than hardcoded, so
    this cannot go stale as the catalog grows.
    """
    first = start if start % 2 else start + 1
    codes = range(first, end + 1, 2)
    if include_known:
        return list(codes)
    return [c for c in codes if c not in catalog.CATALOG]


def probe_codes(
    client: LocalClient,
    codes: Iterable[int],
    payloads: Sequence[dict],
    *,
    stop_on_hit: bool = True,
    reconnect: Callable[[], LocalClient] | None = None,
    on_result: Callable[[ProbeResult], None] | None = None,
) -> list[ProbeResult]:
    """Probe each code with each payload shape.

    ``stop_on_hit`` (default) returns as soon as a shape yields data — fastest
    when the question is merely "does this code exist?".

    Set it to ``False`` to try **every** shape and keep the richest reply. That
    is the mode that matters when a code already answers ``{"opt": 0}`` with a
    thin or placeholder-looking payload: the question is then not *whether* it
    responds but whether a different shape makes it respond with **more**.
    (Mirrors the cloud's own BMS read, which sends type 2 and type 3 and keeps
    whichever came back richer.)

    ``reconnect`` is required for any sweep that may leave the recognised band:
    the aGate **closes the connection** on an out-of-band cmdType rather than
    rejecting it, so without reconnecting every subsequent probe fails with a
    broken pipe and the whole run is silently worthless. With it, the sweep
    rebuilds the session and carries on.

    Read-only: every shape here is a read (``opt=0`` or a selector). No ``opt=1``
    write is ever sent.
    """
    results: list[ProbeResult] = []
    for cmd in codes:
        result = ProbeResult(cmd_type=cmd, status="timeout")
        best_score = (-1, -1)
        for shape in payloads:
            try:
                data = client.call(cmd, dict(shape))
            except TimeoutError:
                result.attempts.append({"payload": shape, "status": "timeout"})
                continue
            except (TransportError, OSError, ValueError) as exc:
                result.attempts.append({"payload": shape, "status": "error",
                                        "error": str(exc)})
                if result.status == "timeout":
                    result.status, result.error = "error", str(exc)
                if reconnect is not None and _is_disconnect(exc):
                    try:
                        client = reconnect()
                    except Exception:  # noqa: BLE001 - keep sweeping
                        pass
                continue
            keys = set(data or {}) - ENVELOPE
            rejected = (data or {}).get("result") not in (0, None)
            status = "hit" if keys else ("rejected" if rejected else "empty")
            result.attempts.append({"payload": shape, "status": status,
                                    "keys": sorted(keys),
                                    "result": (data or {}).get("result"),
                                    "reason": (data or {}).get("reason"),
                                    "data": data})
            if keys:
                score = payload_score(data)
                if score > best_score:
                    best_score = score
                    result.status, result.payload, result.data = "hit", dict(shape), data
                if stop_on_hit:
                    break
            elif result.status in ("timeout", "rejected"):
                # An accepted-but-empty reply outranks an explicit rejection.
                result.status = "rejected" if rejected else "empty"
                if rejected:
                    result.error = f"result={data.get('result')} reason={data.get('reason')}"
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results
