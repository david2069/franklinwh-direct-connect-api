"""Local energy rollups and TOU-schedule decoding (no hardware)."""

from __future__ import annotations

import datetime as dt

import pytest

from franklinwh_direct_connect_api import catalog, energy


def _day(sno: int, load: float, *, peak=0.0, flat=0.0, valley=0.0) -> dict:
    """A 1303-shaped payload with kwh_load split across tiers."""
    idx = catalog.ENERGY_CHANNELS.index("kwh_load")
    def _arr(v):
        a = [0.0] * len(catalog.ENERGY_CHANNELS)
        a[idx] = v
        return a
    return {
        "opt": 0, "result": 0, "reason": 0, "sno": sno,
        "rec_time": ["00:15"], "kwh_load": load,
        "sharp": _arr(0.0), "peak": _arr(peak),
        "flat": _arr(flat), "valley": _arr(valley),
        **{ch: 0.0 for ch in catalog.ENERGY_CHANNELS if ch != "kwh_load"},
    }


EMPTY = {"opt": 0, "result": 1, "reason": -1, "sno": 0, "rec_time": []}


# -- period ranges -----------------------------------------------------------
def test_week_is_the_iso_week_containing_the_date():
    start, end = energy.period_range("week", dt.date(2026, 9, 9),
                                     today=dt.date(2026, 12, 31))
    assert start == dt.date(2026, 9, 7)      # Monday
    assert end == dt.date(2026, 9, 13)       # Sunday


def test_month_covers_the_calendar_month():
    start, end = energy.period_range("month", dt.date(2026, 2, 15),
                                     today=dt.date(2026, 12, 31))
    assert (start, end) == (dt.date(2026, 2, 1), dt.date(2026, 2, 28))


def test_ranges_never_ask_for_future_days():
    _, end = energy.period_range("year", dt.date(2026, 9, 11),
                                 today=dt.date(2026, 9, 11))
    assert end == dt.date(2026, 9, 11)


def test_unknown_period_is_rejected():
    with pytest.raises(ValueError, match="unknown period"):
        energy.period_range("fortnight", dt.date(2026, 9, 11))


def test_periods_match_the_cloud_type_numbering():
    assert energy.PERIODS == {"day": 1, "week": 2, "month": 3, "year": 4, "total": 5}


# -- aggregation -------------------------------------------------------------
def test_totals_and_tiers_sum_across_days():
    days = [
        (dt.date(2026, 9, 9), _day(1, 10.0, peak=6.0, flat=3.0, valley=1.0)),
        (dt.date(2026, 9, 10), _day(2, 5.0, peak=1.0, flat=3.0, valley=1.0)),
    ]
    roll = energy.aggregate(days, period="week", start=dt.date(2026, 9, 9),
                            end=dt.date(2026, 9, 10))
    assert roll.totals["kwh_load"] == 15.0
    assert roll.tiers["peak"]["kwh_load"] == 7.0
    assert roll.tiers["flat"]["kwh_load"] == 6.0
    assert roll.complete


def test_tier_split_reconciles_with_the_channel_total():
    """The invariant verified on hardware: tiers sum to the channel total."""
    days = [(dt.date(2026, 9, 9), _day(1, 10.0, peak=6.0, flat=3.0, valley=1.0))]
    roll = energy.aggregate(days, period="day", start=dt.date(2026, 9, 9),
                            end=dt.date(2026, 9, 9))
    parts = sum(roll.tiers[t]["kwh_load"] for t in energy.TIERS)
    assert parts == pytest.approx(roll.totals["kwh_load"])


def test_missing_days_are_reported_not_silently_dropped():
    days = [
        (dt.date(2026, 9, 9), _day(1, 10.0, peak=10.0)),
        (dt.date(2026, 9, 10), EMPTY),
    ]
    roll = energy.aggregate(days, period="week", start=dt.date(2026, 9, 9),
                            end=dt.date(2026, 9, 10))
    assert roll.totals["kwh_load"] == 10.0
    assert not roll.complete
    assert roll.days_missing == [dt.date(2026, 9, 10)]
    assert "PARTIAL" in roll.summary()
    assert roll.as_dict()["coverage"]["days_with_data"] == 1


def test_has_data_rejects_the_empty_shell():
    assert not energy.has_data(EMPTY)
    assert energy.has_data(_day(1, 1.0))


# -- fetch loop --------------------------------------------------------------
def test_rollup_walks_back_and_aggregates():
    store = {"2026-09-11": _day(3, 1.0), "2026-09-10": _day(2, 2.0),
             "2026-09-09": _day(1, 4.0)}
    seen = []

    def fetch(d):
        seen.append(d)
        return store.get(d, EMPTY)

    roll = energy.rollup(fetch, "week", dt.date(2026, 9, 11),
                         today=dt.date(2026, 9, 11))
    assert seen[0] == "2026-09-11"          # newest first
    assert roll.totals["kwh_load"] == 7.0


def test_rollup_stops_after_consecutive_empty_days():
    """Retention is contiguous, so don't walk a year of discarded dates."""
    calls = []

    def fetch(d):
        calls.append(d)
        return _day(1, 1.0) if d == "2026-09-11" else EMPTY

    energy.rollup(fetch, "year", dt.date(2026, 9, 11),
                  today=dt.date(2026, 9, 11), stop_after_empty=3)
    assert len(calls) == 4      # the good day, then 3 empties


# -- TOU decoding ------------------------------------------------------------
SCHEDULE = {
    "touStrategy": 1,
    "workdayLv": 5,
    "workdayFlag": [2, 1, 0, 1, 2],
    "workdayTime": ["00:00", "00:30", "02:00", "04:00", "23:00"],
    "weekendLv": 1, "weekendFlag": [0], "weekendTime": ["00:00"],
}


def test_blocks_run_until_the_next_start_and_wrap_to_midnight():
    blocks = energy.decode_tou(SCHEDULE, "workday")
    assert [(b.start, b.end) for b in blocks] == [
        ("00:00", "00:30"), ("00:30", "02:00"), ("02:00", "04:00"),
        ("04:00", "23:00"), ("23:00", "24:00"),
    ]


def test_wave_codes_are_named_from_the_shared_vocabulary():
    blocks = energy.decode_tou(SCHEDULE, "workday")
    assert [b.wave_name for b in blocks] == [
        "On-Peak", "Mid-Peak", "Off-Peak", "Mid-Peak", "On-Peak",
    ]


def test_weekend_single_block_covers_the_day():
    blocks = energy.decode_tou(SCHEDULE, "weekend")
    assert len(blocks) == 1
    assert (blocks[0].start, blocks[0].end) == ("00:00", "24:00")
    assert blocks[0].wave_name == "Off-Peak"


def test_wave_vocabulary_matches_the_cloud():
    """Local and cloud agree on tariff-tier NUMBERING (1407 flags)."""
    assert catalog.WAVE_TYPES == {0: "Off-Peak", 1: "Mid-Peak",
                                  2: "On-Peak", 4: "Super Off-Peak"}


def test_no_tier_to_wave_table_is_published():
    """Hardware evidence contradicts a tier->wave mapping; don't ship a guess.

    The 1303 tier split does not reproduce under 1407's fixed blocks — the
    implied boundary moves day to day. See BACKLOG DEF-1303-TIER-BASIS.
    """
    assert not hasattr(catalog, "TIER_TO_WAVE")


def test_sharp_is_flagged_deprecated():
    assert "sharp" in catalog.DEPRECATED_TIERS
    assert "sharp" in catalog.TIERS          # still emitted, still in the sum


def test_unknown_wave_code_is_labelled_not_crashed():
    blocks = energy.decode_tou({"workdayTime": ["00:00"], "workdayFlag": [9]})
    assert blocks[0].wave_name == "wave 9"


# -- live tier accumulators (1301) -------------------------------------------
def _tiers(ts: int, **per_tier) -> dict:
    p = {"ts": ts}
    for tier in catalog.TIERS:
        p[tier] = [0.0] * len(catalog.ENERGY_CHANNELS)
    for tier, value in per_tier.items():
        p[tier] = [value] * len(catalog.ENERGY_CHANNELS)
    return p


def test_active_tier_is_the_accumulator_that_grew():
    assert energy.active_tier(_tiers(2, flat=2.0), _tiers(1, flat=1.0)) == "flat"


def test_active_tier_is_none_when_nothing_moved():
    assert energy.active_tier(_tiers(2, flat=1.0), _tiers(1, flat=1.0)) is None


def test_day_rollover_is_not_a_tier_change():
    """All accumulators reset at midnight; that is not a transition."""
    assert energy.active_tier(_tiers(2, peak=0.0), _tiers(1, peak=9.0)) is None


def test_tier_transition_is_detected():
    """The observation DEF-1303-TIER-BASIS needs: WHEN the boundary moved."""
    samples = [_tiers(100, flat=1.0), _tiers(160, flat=2.0),
               _tiers(220, flat=2.0, peak=1.0), _tiers(280, flat=2.0, peak=2.0)]
    assert energy.tier_transitions(samples) == [(220, "flat", "peak")]


def test_payloads_without_tier_arrays_yield_no_transitions():
    assert energy.tier_transitions([{"ts": 1}, {"ts": 2}]) == []
