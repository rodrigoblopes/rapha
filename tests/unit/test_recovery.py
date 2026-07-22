"""The recovery traffic light. Invented metrics throughout."""

from datetime import date, timedelta

from rapha.models import DailyMetrics, Source
from rapha.rules.recovery import Readiness, assess_recovery
from rapha.units import Seconds

TODAY = date(2026, 7, 22)


def day(offset: int, *, hrv=50, rhr=52, stress=30, sleep_h=8.0) -> DailyMetrics:
    return DailyMetrics(
        on=TODAY - timedelta(days=offset),
        source=Source.GARMIN_API,
        hrv_ms=hrv,
        resting_hr=rhr,
        stress_avg=stress,
        sleep=Seconds(int(sleep_h * 3600)) if sleep_h else None,
    )


def _baseline(**recent):
    # 20 baseline days at the nominal values, then the last two at `recent`.
    days = [day(o) for o in range(4, 24)]
    days += [day(0, **recent), day(1, **recent)]
    return days


class TestReadiness:
    def test_signals_at_baseline_are_green(self):
        read = assess_recovery(_baseline(), today=TODAY)
        assert read.status is Readiness.GREEN

    def test_one_signal_off_is_amber(self):
        # Only sleep drops; the rest hold.
        read = assess_recovery(_baseline(sleep_h=5.0), today=TODAY)
        assert read.status is Readiness.AMBER

    def test_several_signals_off_is_red(self):
        # HRV crashes, RHR jumps, sleep short — a clear "back off".
        read = assess_recovery(_baseline(hrv=35, rhr=60, sleep_h=4.5), today=TODAY)
        assert read.status is Readiness.RED

    def test_hrv_up_and_stress_down_is_green(self):
        read = assess_recovery(_baseline(hrv=58, stress=22), today=TODAY)
        assert read.status is Readiness.GREEN


class TestItComparesToTheOwnBaseline:
    def test_a_high_resting_hr_person_is_judged_against_themselves(self):
        # Someone whose RHR sits at 60 is not penalised for it — only a rise is.
        days = [day(o, rhr=60) for o in range(4, 24)]
        days += [day(0, rhr=60), day(1, rhr=60)]
        assert assess_recovery(days, today=TODAY).status is Readiness.GREEN


class TestHonesty:
    def test_every_signal_carries_its_numbers(self):
        read = assess_recovery(_baseline(), today=TODAY)
        assert len(read.signals) == 4
        assert all(s.note for s in read.signals)

    def test_no_data_is_amber_not_a_false_green(self):
        read = assess_recovery([], today=TODAY)
        assert read.status is Readiness.AMBER
