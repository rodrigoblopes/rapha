"""Building Garmin workout JSON, and the fail-loud exercise mapping.

Sessions here are invented, shaped like the parser's output.
"""

import pytest

from rapha.garmin.workout import RepStrategy, build_workout, describe
from rapha.mapping.exercises import UnmappedExercise, map_exercise


class TestExerciseMapping:
    def test_a_known_movement_maps(self):
        ex = map_exercise("SUPINO RETO NO SMITH")
        assert ex.category == "BENCH_PRESS"

    def test_equipment_and_tempo_words_do_not_block_a_match(self):
        assert map_exercise("Agachamento no Smith").category == "SQUAT"
        assert map_exercise("ROSCA DIRETA C/ BARRA W").category == "CURL"

    def test_an_unmapped_exercise_raises_rather_than_guessing(self):
        # The whole point: doing the wrong lift for eight weeks is worse than a
        # loud stop. It must never be silently substituted.
        with pytest.raises(UnmappedExercise):
            map_exercise("Exercício Inventado Que Não Existe")

    def test_a_specific_key_is_not_shadowed_by_a_generic_one(self):
        # Regression: a bare "cadeira" fallback once shadowed "cadeira adutora",
        # mapping a hip adduction to a leg extension — the exact wrong-movement
        # failure this module exists to prevent. Longest key must win.
        assert map_exercise("CADEIRA ADUTORA").category == "HIP_RAISE"
        assert map_exercise("CADEIRA ABDUTORA").name == "HIP_ABDUCTION"
        assert map_exercise("CADEIRA EXTENSORA").name == "LEG_EXTENSIONS"


SESSION = {
    "day": 1,
    "focus": "PEITO",
    "exercises": [
        {
            "name": "Supino reto",
            "sets": [{"index": 1, "reps": 12}, {"index": 2, "reps": 10}],
            "rest": {"value": 60},
        },
        {
            "name": "Prancha",
            "sets": [{"index": 1, "duration": {"value": 60}}],
            "rest": None,
        },
    ],
}


class TestBuildWorkout:
    def test_the_payload_names_the_workout_and_is_strength(self):
        result = build_workout(SESSION, name="Day 1 — Peito")
        assert result.payload["workoutName"] == "Day 1 — Peito"
        assert result.payload["sportType"]["sportTypeKey"] == "strength_training"

    def test_rest_steps_go_between_sets_but_not_after_the_last(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.TIME)
        steps = result.payload["workoutSegments"][0]["workoutSteps"]
        kinds = [s["stepType"]["stepTypeKey"] for s in steps]
        # supino set1, rest, supino set2, (no rest), prancha
        assert kinds == ["interval", "rest", "interval", "interval"]

    def test_time_strategy_uses_lap_button_for_reps_and_keeps_the_count_in_the_note(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.TIME)
        first = result.payload["workoutSegments"][0]["workoutSteps"][0]
        assert first["endCondition"]["conditionTypeKey"] == "lap.button"
        assert "12 reps" in first["description"]

    def test_reps_strategy_emits_a_reps_end_condition(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.REPS)
        first = result.payload["workoutSegments"][0]["workoutSteps"][0]
        assert first["endCondition"]["conditionTypeKey"] == "reps"
        assert first["endConditionValue"] == 12

    def test_a_timed_hold_becomes_a_time_step_regardless_of_strategy(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.REPS)
        steps = result.payload["workoutSegments"][0]["workoutSteps"]
        plank = steps[-1]
        assert plank["endCondition"]["conditionTypeKey"] == "time"
        assert plank["endConditionValue"] == 60


class TestUnmappedIsReportedNotSubstituted:
    def test_an_unmapped_exercise_is_skipped_and_named(self):
        session = {
            "exercises": [
                {"name": "Supino reto", "sets": [{"index": 1, "reps": 10}], "rest": None},
                {"name": "Movimento Alienígena", "sets": [{"index": 1, "reps": 10}], "rest": None},
            ]
        }
        result = build_workout(session, name="x")
        assert "Movimento Alienígena" in result.unmapped
        # The mapped one still made it; the unmapped one did not become something else.
        steps = result.payload["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1


class TestDescribe:
    def test_the_dry_run_summary_lists_work_steps_and_unmapped(self):
        session = {
            "exercises": [
                {"name": "Supino reto", "sets": [{"index": 1, "reps": 10}], "rest": None},
                {"name": "Movimento Alienígena", "sets": [{"index": 1, "reps": 10}], "rest": None},
            ]
        }
        text = describe(build_workout(session, name="Day 1"))
        assert "Day 1" in text
        assert "UNMAPPED" in text
        assert "Movimento Alienígena" in text
