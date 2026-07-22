"""Energy targets and the Módulo 18 cut-vs-bulk gate.

All numbers invented.
"""

from datetime import date

from rapha.models import DailyMetrics, Source
from rapha.rules.energy import (
    Direction,
    measured_tdee,
    predicted_bmr,
    recompose_direction,
)
from rapha.units import Grams, Kcal

TODAY = date(2026, 7, 22)


def day(d: int, kcal: int | None) -> DailyMetrics:
    return DailyMetrics(
        on=date(2026, 7, d),
        source=Source.GARMIN_API,
        calories_total=None if kcal is None else Kcal(kcal),
    )


class TestMeasuredTDEE:
    def test_it_averages_the_window(self):
        days = [day(d, 2500) for d in range(1, 22)]
        assert measured_tdee(days, window_days=21, today=TODAY) == Kcal(2500)

    def test_a_day_the_watch_was_off_is_skipped_not_zeroed(self):
        # One missing day must not drag the average toward zero.
        days = [day(d, 2500) for d in range(1, 21)] + [day(21, None)]
        assert measured_tdee(days, window_days=21, today=TODAY) == Kcal(2500)

    def test_too_few_days_returns_none(self):
        days = [day(d, 2500) for d in range(1, 4)]
        assert measured_tdee(days, window_days=21, today=TODAY) is None


class TestPredictedBMRIsOnlyASanityCheck:
    def test_it_is_in_a_plausible_range(self):
        # 85 kg, 177 cm, 40 y, male -> Mifflin-St Jeor ~1780 kcal BMR.
        bmr = predicted_bmr(Grams(85_000), height_mm=1770, age_years=40, sex="M")
        assert 1650 <= bmr.value <= 1900


class TestCutBulkGate:
    def test_above_fifteen_percent_is_a_cut(self):
        direction, reason = recompose_direction(220)  # 22.0%
        assert direction is Direction.CUT
        assert "deficit" in reason or "definition" in reason

    def test_at_or_below_fifteen_percent_opens_a_surplus(self):
        assert recompose_direction(150)[0] is Direction.SURPLUS   # exactly 15%
        assert recompose_direction(120)[0] is Direction.SURPLUS   # 12%

    def test_no_estimate_is_unknown_not_a_guess(self):
        # None must not silently become "cut" — the direction is genuinely unknown.
        direction, reason = recompose_direction(None)
        assert direction is Direction.UNKNOWN
        assert "body-fat" in reason.lower() or "body fat" in reason.lower()

    def test_every_direction_explains_itself(self):
        for bf in (None, 300, 150):
            assert recompose_direction(bf)[1]
