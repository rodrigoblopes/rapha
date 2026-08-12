"""The weight trend estimate: regression slope, protocol windowing, edge cases.

Invented weigh-ins only — never a real bodyweight.
"""

from __future__ import annotations

from datetime import date

from rapha.dashboard.briefing import _weight_view


def _hist(pairs):
    """[(iso, kg)] -> [(date, grams)] as the store yields it."""
    return [(date.fromisoformat(d), round(kg * 1000)) for d, kg in pairs]


def test_a_single_weigh_in_has_no_trend():
    v = _weight_view(_hist([("2026-08-01", 84.0)]), date(2026, 8, 13))
    assert v["estimate"] == []
    assert v["rate_kg_per_week"] is None
    assert len(v["actual"]) == 1


def test_a_falling_series_gives_a_negative_weekly_rate():
    hist = _hist([("2026-07-28", 85.0), ("2026-08-04", 84.3), ("2026-08-11", 83.6)])
    v = _weight_view(hist, date(2026, 8, 13))
    # exactly -0.7 kg over 7 days between each point
    assert v["rate_kg_per_week"] == -0.7
    assert v["projected_kg"] < 83.6  # projected past today, still falling
    assert len(v["estimate"]) == 2


def test_protocol_start_excludes_the_pre_cut_rise():
    # Rose before the cut, fell after. A whole-history fit would look almost flat;
    # anchoring to the protocol start must report the fall.
    hist = _hist([
        ("2026-06-27", 83.5), ("2026-07-14", 84.2), ("2026-07-22", 85.0),  # pre-cut rise
        ("2026-07-28", 84.9), ("2026-08-05", 84.4), ("2026-08-11", 83.9),  # the cut
    ])
    v = _weight_view(hist, date(2026, 8, 13), protocol_start=date(2026, 7, 23))
    assert v["basis"] == "since the protocol started"
    assert v["rate_kg_per_week"] < 0  # the cut shows through, not the earlier rise


def test_it_falls_back_when_no_weigh_ins_since_protocol_start():
    hist = _hist([("2026-06-01", 83.0), ("2026-06-20", 82.0)])
    v = _weight_view(hist, date(2026, 8, 13), protocol_start=date(2026, 8, 1))
    # nothing since Aug 1, so it must not crash — it widens the window
    assert v["rate_kg_per_week"] is not None
    assert v["basis"] != "since the protocol started"
