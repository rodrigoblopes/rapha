"""Parsing Garmin Connect's web-export CSVs.

The export is one CSV per data widget, and they are gloriously inconsistent: three
date formats, comma decimals in some files and dots in others, units glued to
numbers, and `--` for missing. These tests pin the parsing of that mess. All values
here are invented.
"""

from datetime import date
from typing import ClassVar

from rapha.ingest.garmin_csv import (
    parse_activity_row,
    parse_dmy,
    parse_duration_hms,
    parse_num,
    parse_sleep_duration,
)
from rapha.units import Kcal, Seconds


class TestDateFormats:
    def test_slash_dmy(self):
        assert parse_dmy("02/07/2026") == date(2026, 7, 2)

    def test_iso(self):
        assert parse_dmy("2026-07-22") == date(2026, 7, 22)

    def test_iso_with_time(self):
        assert parse_dmy("2026-07-22 05:28:51") == date(2026, 7, 22)

    def test_day_month_no_year_uses_default(self):
        # HRV.csv gives "25 Jun" with no year — anchored to the export's year.
        assert parse_dmy("25 Jun", default_year=2026) == date(2026, 6, 25)

    def test_spaced_day_month_year(self):
        assert parse_dmy(" 22 Jul 2026") == date(2026, 7, 22)

    def test_junk_returns_none(self):
        assert parse_dmy("--") is None
        assert parse_dmy("") is None


class TestNumbers:
    def test_comma_decimal(self):
        # Activities.csv is Brazilian-locale: "1,02" is 1.02.
        assert parse_num("1,02") == 1.02

    def test_dot_decimal(self):
        assert parse_num("85.0") == 85.0

    def test_units_are_stripped(self):
        assert parse_num("58ms") == 58.0
        assert parse_num("85.0 kg") == 85.0
        assert parse_num("40.5") == 40.5

    def test_thousands_dot_with_comma_decimal(self):
        # "3.470" in a comma-decimal file is 3470 (dot = thousands sep).
        assert parse_num("3.470", comma_decimal=True) == 3470.0

    def test_missing_is_none(self):
        assert parse_num("--") is None
        assert parse_num("") is None


class TestDurations:
    def test_hms(self):
        assert parse_duration_hms("00:56:08") == Seconds(3368)

    def test_hms_with_fraction(self):
        assert parse_duration_hms("00:00:51,5") == Seconds(51)

    def test_sleep_duration(self):
        assert parse_sleep_duration("6h 23min") == Seconds(6 * 3600 + 23 * 60)

    def test_sleep_missing(self):
        assert parse_sleep_duration("--") is None


class TestActivityRow:
    HEADER: ClassVar[list[str]] = [
        "Activity Type", "Date", "Favorite", "Title", "Distance", "Calories",
        "Time", "Avg HR", "Max HR", "Aerobic TE", "Avg Run Cadence",
        "Max Run Cadence", "Avg Pace", "Best Pace", "Avg Stride Length",
        "Training Stress Score®", "Steps", "Total Reps", "Total Sets",
    ]

    def test_a_strength_row(self):
        row = dict(zip(self.HEADER, [
            "Strength Training", "2026-07-22 04:31:00", "false", "Chest + Triceps",
            "0,00", "290", "00:56:08", "101", "132", "1,4", "--", "--", "--", "--",
            "0,0", "662", "331", "27",
        ], strict=False))
        act = parse_activity_row(row)
        assert act.kind == "strength_training"
        assert act.calories == Kcal(290)
        assert act.duration == Seconds(3368)
        assert act.avg_hr == 101
        assert act.start.date() == date(2026, 7, 22)

    def test_a_run_row_keeps_distance(self):
        row = dict(zip(self.HEADER, [
            "Treadmill Running", "2026-07-14 05:39:47", "false", "Base", "2,44",
            "275", "00:27:36", "130", "144", "3,1", "101", "150", "11:18", "9:52",
            "0,87", "2.852", "--", "--", "--",
        ], strict=False))
        act = parse_activity_row(row)
        assert act.kind == "treadmill_running"
        assert act.distance_m == 2440   # 2.44 km -> metres
        assert act.calories == Kcal(275)

    def test_a_row_without_a_date_is_dropped(self):
        row = dict(zip(self.HEADER, ["Running", "--", "false"], strict=False))
        assert parse_activity_row(row) is None
