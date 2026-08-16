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

    def test_prancha_abdominal_is_a_plank_not_a_crunch(self):
        # "abdominal" alone → CRUNCH, but a "prancha abdominal" is a timed plank.
        assert map_exercise("PRANCHA ABDOMINAL").category == "PLANK"
        assert map_exercise("Prancha").category == "PLANK"
        assert map_exercise("Abdominal Crunch").category == "CRUNCH"


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

# A pyramid: two sets at 15, two at 12 — should collapse to two repeat groups.
PYRAMID = {
    "exercises": [{
        "name": "Supino reto",
        "sets": [{"reps": 15}, {"reps": 15}, {"reps": 12}, {"reps": 12}],
        "rest": {"value": 90},
    }]
}


class TestBuildWorkout:
    def test_the_payload_names_the_workout_and_is_strength(self):
        result = build_workout(SESSION, name="Day 1 — Peito")
        assert result.payload["workoutName"] == "Day 1 — Peito"
        assert result.payload["sportType"]["sportTypeKey"] == "strength_training"

    def test_same_rep_sets_collapse_into_one_repeat_group_each(self):
        steps = build_workout(PYRAMID, name="x").payload["workoutSegments"][0]["workoutSteps"]
        # two blocks: 2x15 and 2x12
        assert [s["type"] for s in steps] == ["RepeatGroupDTO", "RepeatGroupDTO"]
        assert steps[0]["numberOfIterations"] == 2
        assert steps[1]["numberOfIterations"] == 2
        first_ex = steps[0]["workoutSteps"][0]
        assert first_ex["endConditionValue"] == 15
        assert steps[1]["workoutSteps"][0]["endConditionValue"] == 12

    def test_rest_is_inside_each_set_so_it_follows_every_set(self):
        # A break after every set — including the last, giving a break before the
        # next exercise (the gap the flat build was missing).
        steps = build_workout(PYRAMID, name="x").payload["workoutSegments"][0]["workoutSteps"]
        for block in steps:
            kinds = [c["stepType"]["stepTypeKey"] for c in block["workoutSteps"]]
            assert kinds == ["interval", "rest"]
            assert block["workoutSteps"][1]["endConditionValue"] == 90

    def test_reps_use_the_correct_reps_condition_not_distance(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.REPS)
        first = result.payload["workoutSegments"][0]["workoutSteps"][0]
        assert first["endCondition"]["conditionTypeKey"] == "reps"
        assert first["endCondition"]["conditionTypeId"] == 10   # 3 is distance
        assert first["endConditionValue"] == 12

    def test_time_strategy_uses_lap_button_and_keeps_the_count_in_the_note(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.TIME)
        first = result.payload["workoutSegments"][0]["workoutSteps"][0]
        assert first["endCondition"]["conditionTypeKey"] == "lap.button"
        assert "12 reps" in first["description"]

    def test_a_timed_hold_becomes_a_time_step_regardless_of_strategy(self):
        result = build_workout(SESSION, name="x", strategy=RepStrategy.REPS)
        steps = result.payload["workoutSegments"][0]["workoutSteps"]
        plank = next(s for s in steps if s.get("category") == "PLANK")
        assert plank["endCondition"]["conditionTypeKey"] == "time"
        assert plank["endConditionValue"] == 60

    def test_steporders_are_sequential_across_the_tree(self):
        steps = build_workout(PYRAMID, name="x").payload["workoutSegments"][0]["workoutSteps"]
        orders = []
        for s in steps:
            orders.append(s["stepOrder"])
            orders += [c["stepOrder"] for c in s.get("workoutSteps", [])]
        assert orders == sorted(orders) and orders[0] == 1 and len(set(orders)) == len(orders)


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
        intervals = [s for s in steps if s["stepType"]["stepTypeKey"] == "interval"]
        assert len(intervals) == 1
        assert intervals[0]["category"] == "BENCH_PRESS"


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
