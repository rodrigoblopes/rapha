"""The store. Every number here is invented.

The property under test is the one MrW learned the hard way (its ADR-007): the unit
of ingest is a *window*, not a row. Garmin will be re-polled over overlapping ranges
constantly, and row-identity schemes fall apart on field-poor data. Replacing a
closed window makes duplicates structurally impossible instead of merely unlikely.
"""

import sqlite3
from datetime import date, datetime

import pytest

from rapha.db import Store
from rapha.models import Activity, DailyMetrics, Source
from rapha.units import Grams, Kcal, Seconds


def day(d: int, *, rhr: int = 52, kcal: int = 2500) -> DailyMetrics:
    return DailyMetrics(
        on=date(2026, 6, d),
        resting_hr=rhr,
        hrv_ms=61,
        sleep=Seconds(27_000),
        steps=8_400,
        calories_total=Kcal(kcal),
        calories_active=Kcal(620),
        source=Source.GARMIN_API,
    )


def ride(n: int) -> Activity:
    return Activity(
        activity_id=f"act-{n}",
        start=datetime(2026, 6, n, 6, 30),
        kind="cycling",
        duration=Seconds(3_600),
        distance_m=24_000,
        avg_hr=138,
        calories=Kcal(700),
        source=Source.GARMIN_API,
    )


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


class TestWindowReplacement:
    def test_ingesting_the_same_window_twice_changes_nothing(self, store):
        rows = [day(1), day(2), day(3)]
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), rows)
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), rows)

        assert len(store.daily_between(date(2026, 6, 1), date(2026, 6, 30))) == 3

    def test_re_ingesting_a_window_replaces_rather_than_merges(self, store):
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1), day(2), day(3)])
        # Garmin revised the data: only two days now, and a different resting HR.
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1, rhr=49), day(2)])

        rows = store.daily_between(date(2026, 6, 1), date(2026, 6, 30))
        assert len(rows) == 2
        assert rows[0].resting_hr == 49

    def test_a_partial_overlap_only_replaces_its_own_range(self, store):
        store.ingest_daily(
            date(2026, 6, 1), date(2026, 6, 5), [day(1), day(2), day(3), day(4), day(5)]
        )
        # A later sync covers 4-7 only. Days 1-3 must survive untouched.
        store.ingest_daily(
            date(2026, 6, 4), date(2026, 6, 7), [day(4, rhr=48), day(5), day(6), day(7)]
        )

        rows = store.daily_between(date(2026, 6, 1), date(2026, 6, 30))
        assert [r.on.day for r in rows] == [1, 2, 3, 4, 5, 6, 7]
        assert rows[0].resting_hr == 52  # day 1, untouched
        assert rows[3].resting_hr == 48  # day 4, replaced

    def test_an_empty_window_clears_it(self, store):
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1), day(2)])
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [])

        assert store.daily_between(date(2026, 6, 1), date(2026, 6, 30)) == []

    def test_a_row_outside_its_declared_window_is_refused(self, store):
        # Silently accepting it would put a row where the next window-replace
        # cannot find it, and it would survive forever as a ghost.
        with pytest.raises(ValueError, match="outside"):
            store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(9)])


class TestAtomicity:
    def test_a_batch_rejected_before_the_delete_leaves_the_window_intact(self, store):
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1), day(2), day(3)])

        with pytest.raises(ValueError):
            store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1), day(9)])

        rows = store.daily_between(date(2026, 6, 1), date(2026, 6, 30))
        assert len(rows) == 3, "the rejected batch must not have deleted the good one"

    def test_a_batch_that_fails_MID_INSERT_rolls_the_delete_back(self, store):
        """The one that actually tests atomicity.

        Validation runs before the DELETE, so the test above never reaches it. This
        one fails *after* the DELETE — two rows sharing a primary key — which is the
        case that leaves the window silently empty if the pair is not one step.
        """
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(1), day(2), day(3)])

        with pytest.raises(sqlite3.IntegrityError):
            store.ingest_daily(date(2026, 6, 1), date(2026, 6, 3), [day(2), day(2)])

        rows = store.daily_between(date(2026, 6, 1), date(2026, 6, 30))
        assert len(rows) == 3, "the DELETE must have rolled back with the failed INSERT"
        assert [r.on.day for r in rows] == [1, 2, 3]


class TestUnitsSurviveTheRoundTrip:
    def test_quantities_come_back_as_quantities_not_ints(self, store):
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 1), [day(1)])
        row = store.daily_between(date(2026, 6, 1), date(2026, 6, 1))[0]

        assert row.calories_total == Kcal(2500)
        assert row.sleep == Seconds(27_000)
        assert isinstance(row.calories_total, Kcal)

    def test_a_missing_measurement_stays_missing(self, store):
        sparse = DailyMetrics(on=date(2026, 6, 1), source=Source.GARMIN_API)
        store.ingest_daily(date(2026, 6, 1), date(2026, 6, 1), [sparse])
        row = store.daily_between(date(2026, 6, 1), date(2026, 6, 1))[0]

        assert row.resting_hr is None
        assert row.calories_total is None, "0 kcal and 'not measured' are different facts"

    def test_weight_round_trips_as_grams(self, store):
        weighed = DailyMetrics(
            on=date(2026, 6, 2), weight=Grams(84_300), source=Source.GARMIN_API
        )
        store.ingest_daily(date(2026, 6, 2), date(2026, 6, 2), [weighed])
        assert store.daily_between(date(2026, 6, 2), date(2026, 6, 2))[0].weight == Grams(84_300)


class TestActivities:
    def test_activities_replace_by_window_too(self, store):
        store.ingest_activities(date(2026, 6, 1), date(2026, 6, 3), [ride(1), ride(2)])
        store.ingest_activities(date(2026, 6, 1), date(2026, 6, 3), [ride(1), ride(2)])

        assert len(store.activities_between(date(2026, 6, 1), date(2026, 6, 30))) == 2

    def test_the_source_tag_survives(self, store):
        store.ingest_activities(date(2026, 6, 1), date(2026, 6, 1), [ride(1)])
        got = store.activities_between(date(2026, 6, 1), date(2026, 6, 1))
        assert got[0].source is Source.GARMIN_API


class TestSchema:
    def test_a_store_can_be_reopened(self, tmp_path):
        path = tmp_path / "reopen.db"
        with Store(path) as s:
            s.ingest_daily(date(2026, 6, 1), date(2026, 6, 1), [day(1)])
        with Store(path) as s:
            assert len(s.daily_between(date(2026, 6, 1), date(2026, 6, 1))) == 1
