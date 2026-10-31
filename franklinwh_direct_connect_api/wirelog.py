"""Request/response wire logging — redacted, truncated, size-capped and rotating.

Every ``cmdType`` frame this library sends or receives can be written to a log, to
answer "what did we actually put on the wire, and what came back?" without asking
anyone to trust a reconstruction.

**It logs what was actually on the wire — nothing is hidden by default.** A debug log that
quietly alters the payload is worse than none, because the one field you are chasing is the
one that got starred out. Full fidelity is the default.

**Redaction is available when it is needed, with ``redact=True``** (CLI:
``--wire-log-redact``). Use it when the log is going to leave the machine — an issue, a
gist, a hand to someone else. These payloads carry **WiFi passwords** (``wifi_Pw``,
``ap_Pw``), device **serials**, **MAC addresses** and the site's **latitude, longitude and
postcode**, and the redacting form keeps each value's **length and container shape** so the
log still answers "one per aPower, or a single value?" without the values themselves. The
field list is derived from the catalogue's own documented payloads, not guessed.

A log written without redaction holds those secrets in clear. It is a local diagnostic
file: read it, use it, delete it. Do not attach it, commit it, or paste it. This package's
``.gitignore`` refuses ``*.jsonl`` so it cannot be committed by accident.

**It truncates.** Long arrays (per-cell ``batVolt`` and friends) and long strings are
clipped, with a marker saying what was dropped, so one frame cannot produce a megabyte.

**It is bounded, and cannot grow without limit.** Each file has a byte cap; when it is
reached the file rotates and the oldest is deleted. ``max_bytes * (backups + 1)`` is a
hard ceiling on total disk use — 4 MB by default. Left on for a month, it still occupies
4 MB.

Off unless asked for. Enable it from the CLI with ``--wire-log PATH``, or in code::

    from franklinwh_direct_connect_api import WireLog, DirectConnectClient

    with WireLog("wire.jsonl") as wl, DirectConnectClient(host, wire_log=wl) as c:
        c.login()
        c.power_flow()

Each line is one JSON object, so the log is greppable and ``jq``-able while being
appended to.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

__all__ = ["WireLog", "SENSITIVE_FIELDS", "SENSITIVE_PATTERNS", "SENSITIVE_TOKENS",
           "redact", "set_default", "get_default"]

#: Process-wide wire log, used by any transport not given one explicitly.
#:
#: This exists for the CLI: ``--wire-log PATH`` must capture every subcommand without
#: threading a parameter through dozens of call sites. Library callers should pass
#: ``wire_log=`` to the client instead -- an explicit log is clearer and cannot surprise
#: a second consumer sharing the process.
_default: Any | None = None


def set_default(log: Any | None) -> None:
    """Install (or clear, with ``None``) the process-wide wire log."""
    global _default
    _default = log


def get_default() -> Any | None:
    """The process-wide wire log, or ``None``."""
    return _default

#: Fields replaced with ``<redacted:N>`` unless raw logging is requested. Derived from
#: the payloads the catalogue documents (``catalog.CATALOG[*].description``) rather than
#: from guesswork: credentials (1111 wifi_config), serials (1101 login, 1123
#: agate_serial), network identity (1117 network_interfaces), site location (1201
#: time_location) and the 2030.5 device identifiers (1205 der_comms).
#:
#: Matching is case-insensitive, and any field **ending** in ``_SN`` or ``_sn`` is treated
#: as a serial, so a serial field this list has never heard of is still redacted. That
#: direction of error is the safe one.
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    # credentials -- 1111/1112
    "wifi_pw", "ap_pw", "wifi_ssid", "ap_ssid", "wifi_safety",
    # serials -- 1101/1102, 1123/1124, and the per-device reads
    "ibg_sn", "fhp_sn", "bms_sn", "pe_sn", "agate_sn", "devsn", "fhpsn",
    # network identity -- 1117/1118
    "mac", "ip", "dns", "gateway", "routerip",
    # site location -- 1201/1202
    "latitude", "longitude", "postcode",
    # IEEE 2030.5 device identifiers -- 1205/1206
    "lfdi", "sfdi", "pin",
})

#: Substring patterns that redact a field whatever it is called. Exact names are not
#: enough on this protocol: the aGate spells latitude **"laitude"**, which
#: ``SENSITIVE_FIELDS`` matched exactly and therefore missed, so a redacted log leaked the
#: site's latitude while still being stamped ``"redacted": true``. A vendor typo must not
#: be able to defeat redaction, and this protocol has several.
#:
#: Over-redaction is harmless in a log whose purpose is to be shareable; under-redaction
#: is a disclosure. These patterns are therefore deliberately broad, and matched as
#: substrings of the lower-cased field name.
SENSITIVE_PATTERNS: tuple[str, ...] = (
    "itude",        # latitude, longitude, laitude, altitude -- and future typos
    "postcode", "postal", "zipcode",
    "passw", "pwd", "_pw",
    "ssid",
    "serial",
    "lfdi", "sfdi",
)

#: Whole-token matches, for names too short to use as substrings safely ("mac" would
#: otherwise redact "machine", "ip" would redact "clipping").
SENSITIVE_TOKENS: frozenset[str] = frozenset({
    "mac", "ip", "dns", "gateway", "pin", "routerip",
})

_REDACTED = "<redacted:{}>"


def _cmd_name(cmd_type: int) -> str | None:
    """Catalogue name for a cmdType, or None for one we have no name for."""
    from . import catalog
    info = catalog.CATALOG.get(cmd_type)
    if info is not None:
        return info.name
    # Responses are request+1 and are not themselves catalogue keys.
    info = catalog.CATALOG.get(cmd_type - 1)
    return f"{info.name} (reply)" if info is not None else None


def _is_sensitive(key: str) -> bool:
    """Whether a field's VALUE must be hidden in a redacted log.

    Four ways to match, deliberately generous -- see ``SENSITIVE_PATTERNS`` for why an
    exact-name list alone was not safe:

    1. the exact documented name (``SENSITIVE_FIELDS``);
    2. a serial suffix (``*_SN``), so an unknown serial field is still caught;
    3. a substring pattern, which survives vendor misspellings;
    4. a whole token, for names too short to match as substrings.
    """
    low = key.lower()
    if low in SENSITIVE_FIELDS or low.endswith("_sn"):
        return True
    if any(pat in low for pat in SENSITIVE_PATTERNS):
        return True
    tokens = {t for t in low.replace("-", "_").split("_") if t}
    return bool(tokens & SENSITIVE_TOKENS)


def redact(value: Any, *, _key: str = "") -> Any:
    """Return ``value`` with sensitive fields replaced, recursively.

    The replacement keeps the original **length** (``<redacted:20>``) because length is
    often the diagnostic point — a serial that arrived truncated, a password field that
    came back empty — while the value itself is not written to disk.
    """
    if isinstance(value, dict):
        return {k: (_hide(v) if _is_sensitive(str(k)) else redact(v, _key=str(k)))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if _is_sensitive(_key):
            return [_hide(v) for v in value]
        return [redact(v) for v in value]
    return value


def _hide(value: Any) -> Any:
    """Replace a sensitive value, **keeping its container shape**.

    Shape has to survive redaction or the log cannot answer the question it is most
    often opened for: is this field one value per aPower, or a single value? Collapsing
    a one-element list to ``<redacted:1>`` makes a list of one indistinguishable from a
    one-character string, so a list stays a list of markers and a dict stays a dict.
    """
    if isinstance(value, (list, tuple)):
        return [_hide(v) for v in value]
    if isinstance(value, dict):
        return {k: _hide(v) for k, v in value.items()}
    return _REDACTED.format(_measure(value))


def _measure(value: Any) -> int:
    """Length of the hidden value, for the ``<redacted:N>`` marker."""
    try:
        return len(value) if isinstance(value, (str, bytes, list, tuple, dict)) else len(str(value))
    except TypeError:                       # pragma: no cover - defensive
        return 0


def truncate(value: Any, *, max_items: int, max_chars: int) -> Any:
    """Clip long arrays and long strings, recording what was dropped.

    A clipped list keeps its first ``max_items`` entries and appends
    ``"...+N more"``; a clipped string keeps ``max_chars`` and appends ``"...(+N)"``.
    The marker matters: a reader must be able to tell a short payload from a clipped one,
    or the log quietly lies about what the device sent.
    """
    if isinstance(value, dict):
        return {k: truncate(v, max_items=max_items, max_chars=max_chars)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        clipped = [truncate(v, max_items=max_items, max_chars=max_chars)
                   for v in list(value)[:max_items]]
        dropped = len(value) - len(clipped)
        if dropped > 0:
            clipped.append(f"...+{dropped} more")
        return clipped
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"...(+{len(value) - max_chars})"
    return value


class WireLog:
    """A bounded, rotating, redacted JSON-lines log of wire traffic.

    Parameters
    ----------
    path:
        Log file. Rotated files are ``path.1``, ``path.2``, ….
    max_bytes:
        Rotate once the file reaches this size. Total disk use is bounded by
        ``max_bytes * (backups + 1)``.
    backups:
        How many rotated files to keep. ``0`` means truncate in place and keep none,
        which still bounds disk use.
    redact:
        ``False`` (the default) logs the payload **exactly as it went over the wire**,
        secrets included — which is what a debug log is for. ``True`` replaces sensitive
        values with ``<redacted:N>``, keeping their length and container shape; use it for
        a log that is going to leave this machine.
    max_items / max_chars:
        Truncation limits per array and per string.
    """

    def __init__(self, path: str | os.PathLike[str], *, max_bytes: int = 1_048_576,
                 backups: int = 3, redact: bool = False,
                 max_items: int = 24, max_chars: int = 512) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive -- an unbounded log is the bug this class exists to prevent")
        if backups < 0:
            raise ValueError("backups cannot be negative")
        self.path = Path(path)
        self.max_bytes = int(max_bytes)
        self.backups = int(backups)
        self.redact = bool(redact)
        self.max_items = int(max_items)
        self.max_chars = int(max_chars)
        self._lock = threading.Lock()
        self._fh: Any = None
        self.records = 0
        self.rotations = 0

    # -- lifecycle -----------------------------------------------------------
    def open(self) -> WireLog:
        if self._fh is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")
        return self

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None

    def __enter__(self) -> WireLog:
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writing -------------------------------------------------------------
    def log(self, direction: str, cmd_type: int, data_area: Any, *,
            equip_no: str | None = None, name: str | None = None,
            elapsed_ms: float | None = None, error: str | None = None) -> None:
        """Append one frame. Never raises: a broken log must not break a device call."""
        try:
            self._write(self._record(direction, cmd_type, data_area, equip_no,
                                     name, elapsed_ms, error))
        except (OSError, ValueError, TypeError):
            pass          # a logging failure is not worth losing the caller's request over

    def _record(self, direction: str, cmd_type: int, data_area: Any,
                equip_no: str | None, name: str | None,
                elapsed_ms: float | None, error: str | None) -> dict[str, Any]:
        from . import catalog
        payload = redact(data_area) if self.redact else data_area
        payload = truncate(payload, max_items=self.max_items, max_chars=self.max_chars)
        rec: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "dir": direction,                       # "req" or "resp"
            "cmdType": int(cmd_type),
            "name": name or _cmd_name(cmd_type),
            "dataArea": payload,
        }
        if equip_no is not None:
            rec["equipNo"] = _REDACTED.format(len(equip_no)) if self.redact else equip_no
        if elapsed_ms is not None:
            rec["ms"] = round(elapsed_ms, 1)
        if error is not None:
            rec["error"] = error
        # Mark the redacted form, not the full one: a reader who finds an unmarked file
        # must assume it holds secrets, which is the safe default assumption.
        if self.redact:
            rec["redacted"] = True
        return rec

    def _write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False) + "\n"
        blob = line.encode("utf-8")
        with self._lock:
            if self._fh is None:
                self.open()
            # Rotate BEFORE writing, so max_bytes is never exceeded rather than
            # merely noticed afterwards.
            if self._fh.tell() + len(blob) > self.max_bytes and self._fh.tell() > 0:
                self._rotate_locked()
            self._fh.write(line)
            self._fh.flush()
            self.records += 1

    def _rotate_locked(self) -> None:
        self._fh.close()
        self._fh = None
        if self.backups == 0:
            self.path.unlink(missing_ok=True)        # keep nothing; stay bounded
        else:
            oldest = self.path.with_suffix(self.path.suffix + f".{self.backups}")
            oldest.unlink(missing_ok=True)           # drop the oldest, never accumulate
            for n in range(self.backups - 1, 0, -1):
                src = self.path.with_suffix(self.path.suffix + f".{n}")
                if src.exists():
                    src.replace(self.path.with_suffix(self.path.suffix + f".{n + 1}"))
            self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))
        self.rotations += 1
        self.open()

    # -- introspection -------------------------------------------------------
    def total_bytes(self) -> int:
        """Bytes currently on disk across the live file and its rotations."""
        total = 0
        for p in [self.path] + [self.path.with_suffix(self.path.suffix + f".{n}")
                                for n in range(1, self.backups + 1)]:
            if p.exists():
                total += p.stat().st_size
        return total

    @property
    def max_total_bytes(self) -> int:
        """The hard ceiling on disk use: nothing can exceed this."""
        return self.max_bytes * (self.backups + 1)

    def __repr__(self) -> str:
        return (f"WireLog({str(self.path)!r}, max_bytes={self.max_bytes}, "
                f"backups={self.backups}, redact={self.redact}, records={self.records})")
