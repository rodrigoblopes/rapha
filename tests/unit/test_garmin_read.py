"""Normalising Garmin's payloads into canonical records.

All payloads here are invented and deliberately ragged, because the real ones are:
Garmin's responses differ by device and firmware, and a key that is missing means
"this device did not record it".
"""

from datetime import date
from typing import ClassVar

from rapha.garmin.read import activity_from_payload, daily_from_payloads
from rapha.models import Source
from rapha.units import Grams, Kcal, Seconds


class TestDailyMetrics:
    def test_a_complete_day(self):
        d = daily_from_payloads(
            date(2026, 6, 1),
            summary={
                "restingHeartRate": 52,
                "totalSteps": 8400,
                "totalKilocalories": 2531,
                "activeKilocalories": 620,
                "averageStressLevel": 28,
                "bodyBatteryHighestValue": 88,
                "bodyBatteryLowestValue": 21,
            },
            sleep={"dailySleepDTO": {"sleepTimeSeconds": 27000}},
            hrv={"hrvSummary": {"lastNightAvg": 61}},
            vo2={"generic": {"vo2MaxPreciseValue": 44.7}},
            weight_g=84300,
        )

        assert d.calories_total == Kcal(2531)
        assert d.sleep == Seconds(27000)
        assert d.hrv_ms == 61
        assert d.weight == Grams(84300)
        assert d.source is Source.GARMIN_API

    def test_vo2max_keeps_one_decimal_as_an_integer(self):
        """44.7 becomes 447, not 44. Floats are banned; precision is not."""
        d = daily_from_payloads(
            date(2026, 6, 1), None, None, None, {"generic": {"vo2MaxPreciseValue": 44.7}}
        )
        assert d.vo2max_x10 == 447

    def test_a_day_the_watch_was_not_worn_is_all_none(self):
        """None means not measured. Zero would drag every average it touches."""
        d = daily_from_payloads(date(2026, 6, 2), None, None, None, None)

        assert d.calories_total is None
        assert d.resting_hr is None
        assert d.sleep is None
        assert d.on == date(2026, 6, 2)

    def test_a_partial_payload_does_not_explode(self):
        # Devices vary: no HRV sensor, no Body Battery, no VO2max.
        d = daily_from_payloads(
            date(2026, 6, 3),
            summary={"totalKilocalories": 2200},
            sleep={"dailySleepDTO": {}},
            hrv={},
            vo2={},
        )

        assert d.calories_total == Kcal(2200)
        assert d.sleep is None
        assert d.hrv_ms is None
        assert d.vo2max_x10 is None

    def test_a_null_nested_value_is_not_mistaken_for_zero(self):
        d = daily_from_payloads(
            date(2026, 6, 4), summary={"restingHeartRate": None}, sleep=None,
            hrv=None, vo2=None
        )
        assert d.resting_hr is None


class TestActivities:
    RAW: ClassVar[dict] = {
        "activityId": 987654321,
        "startTimeLocal": "2026-06-01 06:30:00",
        "activityType": {"typeKey": "cycling"},
        "duration": 3600.0,
        "distance": 24000.0,
        "averageHR": 138,
        "maxHR": 171,
        "calories": 700,
        "activityTrainingLoad": 88.4,
    }

    def test_a_normal_activity(self):
        a = activity_from_payload(self.RAW)

        assert a.activity_id == "987654321"
        assert a.kind == "cycling"
        assert a.duration == Seconds(3600)
        assert a.avg_hr == 138
        assert a.calories == Kcal(700)

    def test_training_load_keeps_a_decimal(self):
        assert activity_from_payload(self.RAW).training_load_x10 == 884

    def test_an_activity_without_a_start_time_is_dropped_not_guessed(self):
        # Inventing a timestamp would file the session on the wrong day, which is
        # worse than not having it: the assessment reads training *history*.
        assert activity_from_payload({"activityId": 1}) is None

    def test_an_unparseable_start_time_is_dropped(self):
        assert activity_from_payload({"activityId": 1, "startTimeLocal": "nope"}) is None

    def test_a_strength_session_without_distance(self):
        a = activity_from_payload(
            {
                "activityId": 5,
                "startTimeLocal": "2026-06-02 18:00:00",
                "activityType": {"typeKey": "strength_training"},
                "duration": 4200,
            }
        )

        assert a.kind == "strength_training"
        assert a.distance_m is None
        assert a.duration == Seconds(4200)
