"""Acute:chronic workload ratio. Invented load points, round numbers."""

from datetime import date, timedelta

from rapha.rules.workload import acwr


def _steady(daily: int, days: int, end: date) -> list[tuple[date, int]]:
    # `daily` load (points) every day for `days` days ending at `end`; stored ×10.
    return [(end - timedelta(days=i), daily * 10) for i in range(days)]


class TestAcwr:
    def test_no_load_is_unknown(self):
        b = acwr([])
        assert b.ratio is None and b.band == "unknown" and not b.reliable

    def test_steady_training_sits_at_one(self):
        # Same daily load for 5 weeks: acute == chronic weekly, ratio 1.0, optimal.
        loads = _steady(10, 35, date(2026, 8, 20))
        b = acwr(loads, today=date(2026, 8, 20))
        assert b.ratio == 1.0
        assert b.band == "optimal"
        assert b.reliable

    def test_a_spike_week_reads_high(self):
        base = _steady(10, 28, date(2026, 8, 13))          # four weeks of base
        spike = _steady(30, 7, date(2026, 8, 20))          # a tripled last week
        b = acwr(base + spike, today=date(2026, 8, 20))
        assert b.ratio is not None and b.ratio > 1.5
        assert b.band == "spike"

    def test_ratio_is_unreliable_before_a_full_chronic_window(self):
        b = acwr(_steady(10, 6, date(2026, 8, 20)), today=date(2026, 8, 20))
        assert not b.reliable

    def test_detraining_when_recent_load_drops_off(self):
        base = _steady(20, 21, date(2026, 8, 6))           # loaded weeks, then nothing
        b = acwr(base, today=date(2026, 8, 20))            # last 7 days empty
        assert b.acute == 0
        assert b.band == "detraining"
