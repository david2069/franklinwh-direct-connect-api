"""
Energy history aggregation and TOU-schedule decoding.

The aGate serves **one day at a time** (cmdType 1303): 96 quarter-hour points
plus seven daily ``kwh_*`` totals, split across tariff tiers. It has no
week/month/year call — the cloud's ``get_power_details(type=2..5)`` rollups are
computed cloud-side, and local ``dayType`` is echoed but ignored.

So we roll up locally: fetch the constituent days and sum them. The only real
constraint is retention — the gateway keeps a rolling window of roughly 105
days, so a year rollup is necessarily partial. Every result therefore reports
its own **coverage** (days requested, days with data, days missing) rather than
silently presenting a short sum as a full period.

See BACKLOG: FEAT-LOCAL-ROLLUPS.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from . import catalog

#: Rollup periods, using the same numbering as the cloud's `get_power_details`
#: `type` parameter so the two vocabularies line up.
PERIODS: dict[str, int] = {"day": 1, "week": 2, "month": 3, "year": 4, "total": 5}

#: Tariff-tier arrays carried by each daily payload, in device order.
#: Re-exported from the catalog, which documents what is and is not known about
#: how the device assigns them (``sharp`` looks deprecated — always zero).
TIERS: tuple[str, ...] = catalog.TIERS

#: A day with no stored history comes back with sno=0 and empty arrays.
def has_data(day: dict) -> bool:
    """True when the gateway actually had history for this day."""
    return bool(day.get("sno")) and bool(day.get("rec_time"))


@dataclass
class Rollup:
    """Aggregated energy over a date range, with explicit coverage."""

    period: str
    start: dt.date
    end: dt.date
    totals: dict[str, float] = field(default_factory=dict)
    tiers: dict[str, dict[str, float]] = field(default_factory=dict)
    days_with_data: list[dt.date] = field(default_factory=list)
    days_missing: list[dt.date] = field(default_factory=list)

    @property
    def days_requested(self) -> int:
        return len(self.days_with_data) + len(self.days_missing)

    @property
    def complete(self) -> bool:
        return not self.days_missing

    def summary(self) -> str:
        span = f"{self.start.isoformat()} .. {self.end.isoformat()}"
        cover = f"{len(self.days_with_data)}/{self.days_requested} days"
        flag = "" if self.complete else "  (PARTIAL — gateway retention ~105 days)"
        return f"{self.period} {span}   {cover}{flag}"

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "totals": self.totals,
            "tiers": self.tiers,
            "coverage": {
                "days_requested": self.days_requested,
                "days_with_data": len(self.days_with_data),
                "days_missing": [d.isoformat() for d in self.days_missing],
                "complete": self.complete,
            },
        }


def period_range(period: str, date: dt.date, *, today: dt.date | None = None
                 ) -> tuple[dt.date, dt.date]:
    """Inclusive date range for a period containing ``date``.

    ``week`` is the ISO week (Monday-Sunday). ``month`` and ``year`` are calendar
    periods. ``total`` walks back a generous window and lets retention truncate
    it. Ranges are clipped so we never request future days.
    """
    today = today or dt.date.today()
    if period == "day":
        start = end = date
    elif period == "week":
        start = date - dt.timedelta(days=date.weekday())
        end = start + dt.timedelta(days=6)
    elif period == "month":
        start = date.replace(day=1)
        nxt = (start + dt.timedelta(days=32)).replace(day=1)
        end = nxt - dt.timedelta(days=1)
    elif period == "year":
        start = date.replace(month=1, day=1)
        end = date.replace(month=12, day=31)
    elif period == "total":
        # Comfortably wider than the observed retention window.
        start, end = date - dt.timedelta(days=400), date
    else:
        raise ValueError(f"unknown period {period!r}; "
                         f"expected one of {', '.join(PERIODS)}")
    return start, min(end, today)


def aggregate(days: Iterable[tuple[dt.date, dict]], *, period: str,
              start: dt.date, end: dt.date) -> Rollup:
    """Sum daily payloads into a :class:`Rollup`."""
    roll = Rollup(period=period, start=start, end=end)
    roll.totals = {ch: 0.0 for ch in catalog.ENERGY_CHANNELS}
    roll.tiers = {t: {ch: 0.0 for ch in catalog.ENERGY_CHANNELS} for t in TIERS}

    for day_date, payload in days:
        if not has_data(payload):
            roll.days_missing.append(day_date)
            continue
        roll.days_with_data.append(day_date)
        for channel in catalog.ENERGY_CHANNELS:
            value = payload.get(channel)
            if isinstance(value, (int, float)):
                roll.totals[channel] += value
        for tier in TIERS:
            series = payload.get(tier) or []
            for idx, channel in enumerate(catalog.ENERGY_CHANNELS):
                if idx < len(series) and isinstance(series[idx], (int, float)):
                    roll.tiers[tier][channel] += series[idx]

    roll.totals = {k: round(v, 4) for k, v in roll.totals.items()}
    roll.tiers = {t: {k: round(v, 4) for k, v in ch.items()}
                  for t, ch in roll.tiers.items()}
    return roll


def rollup(fetch_day: Callable[[str], dict], period: str, date: dt.date, *,
           today: dt.date | None = None,
           on_day: Callable[[dt.date, dict], None] | None = None,
           stop_after_empty: int | None = None) -> Rollup:
    """Fetch and aggregate a period, newest day first.

    ``fetch_day`` takes a ``YYYY-MM-DD`` string and returns the 1303 payload.
    ``stop_after_empty`` short-circuits once that many consecutive days come back
    empty — history is contiguous, so for ``total`` this avoids walking a year of
    dates the gateway has already discarded.
    """
    start, end = period_range(period, date, today=today)
    collected: list[tuple[dt.date, dict]] = []
    empty_run = 0
    cursor = end
    while cursor >= start:
        payload = fetch_day(cursor.isoformat())
        collected.append((cursor, payload))
        if on_day is not None:
            on_day(cursor, payload)
        if has_data(payload):
            empty_run = 0
        else:
            empty_run += 1
            if stop_after_empty is not None and empty_run >= stop_after_empty:
                start = cursor
                break
        cursor -= dt.timedelta(days=1)
    collected.reverse()
    return aggregate(collected, period=period, start=start, end=end)


# ── TOU schedule (1407) ──────────────────────────────────────────────────

@dataclass
class TouBlock:
    """One tariff block: a start/end time and its tariff tier."""

    start: str
    end: str
    wave: int

    @property
    def wave_name(self) -> str:
        return catalog.WAVE_TYPES.get(self.wave, f"wave {self.wave}")


def decode_tou(payload: dict, day_type: str = "workday") -> list[TouBlock]:
    """Turn 1407's parallel flag/time arrays into ordered tariff blocks.

    The device stores the schedule as ``<day>Time`` (block start times) and
    ``<day>Flag`` (tariff tier per block), with ``<day>Lv`` giving the count.
    Each block runs until the next block's start, the last wrapping to 24:00.
    """
    times = payload.get(f"{day_type}Time") or []
    flags = payload.get(f"{day_type}Flag") or []
    count = min(len(times), len(flags))
    blocks: list[TouBlock] = []
    for i in range(count):
        end = times[i + 1] if i + 1 < count else "24:00"
        blocks.append(TouBlock(start=times[i], end=end, wave=flags[i]))
    return blocks


# ── live tariff-tier accumulators (1301) ─────────────────────────────────
# 1301 carries the same sharp/peak/flat/valley arrays as 1303, but as RUNNING
# accumulators that tick up through the day and reset at midnight. Reading which
# one grew between two samples is the only way to observe when the device
# changes tier (see BACKLOG DEF-1303-TIER-BASIS) — daily totals show the split
# but never when it moved.
#
# These are stateless helpers over payloads. Sampling on an interval and storing
# the result is a BRIDGE concern, not this library's — see EPIC-CLOUD-ALIGN.


def active_tier(payload: dict, previous: dict) -> str | None:
    """Which tariff tier accumulated between two 1301 payloads, if any.

    Returns ``None`` across a day boundary (every accumulator resets) or when
    nothing moved.
    """
    best, best_delta = None, 1e-9
    for tier in catalog.TIERS:
        before = previous.get(tier) or []
        after = payload.get(tier) or []
        if not before or not after or len(before) != len(after):
            continue
        delta = sum(b - a for a, b in zip(before, after))
        if delta < -1e-6:            # accumulators reset -> new day
            return None
        if delta > best_delta:
            best, best_delta = tier, delta
    return best


def tier_transitions(samples: Sequence[dict]) -> list[tuple[int, str, str]]:
    """Points where the active tier changed, from consecutive 1301 payloads.

    ``samples`` is an ordered sequence of ``{"ts": <epoch>, **payload}`` dicts.
    Returns ``(ts, from_tier, to_tier)``.
    """
    out: list[tuple[int, str, str]] = []
    current = None
    for previous, payload in zip(samples, samples[1:]):
        tier = active_tier(payload, previous)
        if tier is None:
            continue
        if current is not None and tier != current:
            out.append((payload.get("ts", 0), current, tier))
        current = tier
    return out
