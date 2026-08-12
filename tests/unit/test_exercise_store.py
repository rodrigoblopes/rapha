"""The per-exercise set store: filtering, idempotency, progression read.

Fixtures use invented lifts and round numbers — never real training data. Weights
are Garmin's native integer grams (25000 == 25 kg); reps are integer counts.
"""

from __future__ import annotations

from datetime import date

import pytest

from rapha.garmin.exercise_store import ExerciseStore


def _payload(activity_id: int, sets: list[dict]) -> dict:
    """Shape Garmin's exerciseSets endpoint returns."""
    return {"activityId": activity_id, "exerciseSets": sets}


def _active(name: str, reps: int, weight_g: int | None, category: str = "BENCH_PRESS") -> dict:
    return {
        "setType": "ACTIVE",
        "exercises": [{"category": category, "name": name, "probability": 99.6}],
        "repetitionCount": reps,
        "weight": weight_g,
        "duration": 40,
    }


def _rest(seconds: int = 60) -> dict:
    return {"setType": "REST", "exercises": [], "repetitionCount": None,
            "weight": None, "duration": seconds}


@pytest.fixture
def store(tmp_path):
    with ExerciseStore(tmp_path / "rapha.db") as es:
        yield es


def test_it_keeps_only_active_sets_and_drops_rest(store):
    n = store.record_activity(1, date(2026, 8, 12), _payload(1, [
        _active("BARBELL_BENCH_PRESS", 12, 40000),
        _rest(),
        _active("BARBELL_BENCH_PRESS", 10, 42500),
        _rest(),
    ]))
    assert n == 2
    rows = store.sets_for_activity(1)
    assert [r.reps for r in rows] == [12, 10]
    assert [r.weight_g for r in rows] == [40000, 42500]


def test_reingesting_the_same_activity_is_a_no_op(store):
    payload = _payload(7, [_active("SQUAT", 10, 60000), _rest(),
                           _active("SQUAT", 8, 65000)])
    store.record_activity(7, date(2026, 8, 10), payload)
    store.record_activity(7, date(2026, 8, 10), payload)  # same file, dropped twice
    rows = store.sets_for_activity(7)
    assert len(rows) == 2  # window-replaced by activity_id, not duplicated


def test_a_revised_activity_replaces_the_old_sets(store):
    store.record_activity(9, date(2026, 8, 1), _payload(9, [_active("ROW", 12, 30000)]))
    # Garmin re-processes the activity and now reports a heavier top set.
    store.record_activity(9, date(2026, 8, 1), _payload(9, [
        _active("ROW", 12, 30000), _active("ROW", 12, 32500)]))
    rows = store.sets_for_activity(9)
    assert len(rows) == 2
    assert max(r.weight_g for r in rows) == 32500


def test_progression_reports_top_set_per_session_newest_first(store):
    store.record_activity(1, date(2026, 8, 1), _payload(1, [
        _active("BARBELL_BENCH_PRESS", 12, 40000),
        _active("BARBELL_BENCH_PRESS", 10, 42500)]))
    store.record_activity(2, date(2026, 8, 8), _payload(2, [
        _active("BARBELL_BENCH_PRESS", 12, 42500),
        _active("BARBELL_BENCH_PRESS", 8, 45000)]))

    prog = store.progression("BARBELL_BENCH_PRESS")
    assert [p.on for p in prog] == [date(2026, 8, 8), date(2026, 8, 1)]
    assert prog[0].top_weight_g == 45000
    assert prog[0].reps_at_top == 8
    # volume = sum(reps * weight) across the session's working sets
    assert prog[1].volume_g == 12 * 40000 + 10 * 42500


def test_exercises_lists_each_movement_once_with_its_latest_date(store):
    store.record_activity(1, date(2026, 8, 1), _payload(1, [_active("SQUAT", 10, 60000, "SQUAT")]))
    store.record_activity(2, date(2026, 8, 8), _payload(2, [
        _active("SQUAT", 10, 62500, "SQUAT"),
        _active("BARBELL_BENCH_PRESS", 12, 40000)]))
    names = {e.name: e for e in store.exercises()}
    assert set(names) == {"SQUAT", "BARBELL_BENCH_PRESS"}
    assert names["SQUAT"].last_seen == date(2026, 8, 8)
    assert names["SQUAT"].sessions == 2


def test_a_bodyweight_set_stores_null_weight_not_zero(store):
    store.record_activity(1, date(2026, 8, 1), _payload(1, [
        _active("PULL_UP", 10, None, "PULL_UP")]))
    rows = store.sets_for_activity(1)
    assert rows[0].weight_g is None  # absent load is a fact, not zero
