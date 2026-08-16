"""The browser-write helpers that are testable without a live Garmin session."""

from __future__ import annotations

from rapha.garmin.browser_write import _strip_exercise_names
from rapha.garmin.workout import RepStrategy, build_workout
from rapha.mapping.exercises import map_exercise


def test_strip_exercise_names_nulls_every_step_name_but_keeps_structure():
    payload = {"workoutSegments": [{"workoutSteps": [
        {"exerciseName": "BICEPS_CURL", "category": "CURL", "description": "rosca"},
        {"exerciseName": "PLANK", "category": "PLANK"},
        {"stepType": {"stepTypeKey": "rest"}},  # a rest step has no name
    ]}]}
    out = _strip_exercise_names(payload)
    steps = out["workoutSegments"][0]["workoutSteps"]
    assert steps[0]["exerciseName"] is None
    assert steps[1]["exerciseName"] is None
    assert steps[0]["category"] == "CURL"        # category kept
    assert steps[0]["description"] == "rosca"     # the note kept — nothing lost
    # original is untouched (deep copy)
    assert payload["workoutSegments"][0]["workoutSteps"][0]["exerciseName"] == "BICEPS_CURL"


def test_front_raise_maps_to_a_valid_garmin_category():
    # Garmin has no FRONT_RAISE category; front raises live under SHOULDER_PRESS.
    g = map_exercise("elevação frontal c/ barra")
    assert g.category == "SHOULDER_PRESS"


def test_cross_over_maps_to_cable_crossover():
    g = map_exercise("cross over polia")
    assert g.name == "CABLE_CROSSOVER"


def test_a_built_workout_survives_name_stripping_as_valid_shape():
    session = {"day": 1, "focus": "OMBRO", "exercises": [
        {"name": "elevação frontal", "sets": [{"reps": 12}], "rest": 60},
    ]}
    payload = build_workout(session, name="x", strategy=RepStrategy.TIME).payload
    stripped = _strip_exercise_names(payload)
    step = stripped["workoutSegments"][0]["workoutSteps"][0]
    assert step["category"] == "SHOULDER_PRESS" and step["exerciseName"] is None
