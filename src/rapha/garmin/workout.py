"""Build Garmin Connect workout JSON from a parsed Cariani session.

This is pure — a parsed session in, a workout payload out — so it is fully
testable without a network. `write.py` is the only thing that sends it.

⚠️ **The rep-based strength step is UNVERIFIED (ADR-001).** Garmin's own builder
historically allowed only time-based steps; some third-party tools claim reps
work. This builder can emit either, chosen by ``RepStrategy``, precisely so the
question can be settled empirically with one dry-run-then-push rather than
assumed. Until a real push confirms reps render on the watch, ``TIME`` is the safe
default: a time step always works, and the rep count rides along in the step
description so nothing is lost.

Garmin's schema, the parts that matter for strength:

    workoutSegments[].workoutSteps[] each carry
      stepType      warmup | interval | rest | cooldown
      endCondition  reps  -> endConditionValue = rep count
                    time  -> endConditionValue = seconds
                    lap.button
      category / exerciseName   the (enum, enum) pair from mapping/exercises.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..mapping.exercises import UnmappedExercise, map_exercise

SPORT_STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training"}

_STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "rest": {"stepTypeId": 4, "stepTypeKey": "rest"},
    "cooldown": {"stepTypeId": 5, "stepTypeKey": "cooldown"},
}

_END_REPS = {"conditionTypeId": 3, "conditionTypeKey": "reps"}
_END_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time"}
_END_LAP = {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}


class RepStrategy(Enum):
    """How to encode a set's rep count on the watch."""

    #: A reps end-condition. Correct if Garmin honours it — unverified (ADR-001).
    REPS = "reps"
    #: A lap-button step; the rep count is in the description. Always works.
    TIME = "time"


@dataclass(frozen=True, slots=True)
class BuildResult:
    payload: dict
    unmapped: list[str]
    strategy: RepStrategy


def _rep_step(order: int, category: str, name: str | None, reps: int, note: str,
              strategy: RepStrategy) -> dict:
    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": _STEP_TYPES["interval"],
        "category": category,
        "exerciseName": name,
        "description": note,
    }
    if strategy is RepStrategy.REPS:
        step["endCondition"] = _END_REPS
        step["endConditionValue"] = reps
    else:
        # Lap-button: the athlete ends the set. The rep target is in the note, so
        # nothing is lost even though the watch does not count reps for us.
        step["endCondition"] = _END_LAP
    return step


def _time_step(order: int, category: str, name: str | None, seconds: int, note: str) -> dict:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": _STEP_TYPES["interval"],
        "category": category,
        "exerciseName": name,
        "endCondition": _END_TIME,
        "endConditionValue": seconds,
        "description": note,
    }


def _rest_step(order: int, seconds: int) -> dict:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": _STEP_TYPES["rest"],
        "endCondition": _END_TIME,
        "endConditionValue": seconds,
    }


def build_workout(
    session: dict,
    *,
    name: str,
    strategy: RepStrategy = RepStrategy.TIME,
) -> BuildResult:
    """Build a Garmin strength-workout payload from one parsed session.

    An unmapped exercise is collected and skipped, and its name is returned in
    ``unmapped`` — the caller (push) decides whether that is acceptable. It is
    never silently replaced with a different movement (CLAUDE.md).
    """
    steps: list[dict] = []
    unmapped: list[str] = []
    order = 1

    for exercise in session.get("exercises", []):
        ex_name = exercise["name"]
        try:
            garmin = map_exercise(ex_name)
        except UnmappedExercise:
            unmapped.append(ex_name)
            continue

        sets = exercise.get("sets") or []
        rest = exercise.get("rest")

        for i, s in enumerate(sets, start=1):
            note = f"{ex_name} — set {i}/{len(sets)}"
            if s.get("reps") is not None:
                note = f"{ex_name} — set {i}/{len(sets)}: {s['reps']} reps"
                steps.append(
                    _rep_step(order, garmin.category, garmin.name, s["reps"], note, strategy)
                )
            elif s.get("duration") is not None:
                secs = s["duration"] if isinstance(s["duration"], int) else s["duration"]["value"]
                steps.append(_time_step(order, garmin.category, garmin.name, secs, note))
            order += 1

            # Rest between sets, but not after the last set of an exercise.
            if rest and i < len(sets):
                secs = rest if isinstance(rest, int) else rest["value"]
                steps.append(_rest_step(order, secs))
                order += 1

    payload = {
        "workoutName": name,
        "sportType": SPORT_STRENGTH,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": SPORT_STRENGTH,
                "workoutSteps": steps,
            }
        ],
    }
    return BuildResult(payload=payload, unmapped=unmapped, strategy=strategy)


def describe(result: BuildResult) -> str:
    """A human-readable dry-run summary of what would be created."""
    steps = result.payload["workoutSegments"][0]["workoutSteps"]
    work = [s for s in steps if s["stepType"]["stepTypeKey"] == "interval"]
    lines = [
        f"workout: {result.payload['workoutName']}",
        f"  strategy: {result.strategy.value}  ({len(work)} work steps, "
        f"{len(steps)} total)",
    ]
    for s in work:
        cond = s["endCondition"]["conditionTypeKey"]
        val = s.get("endConditionValue", "lap")
        lines.append(f"    {s.get('exerciseName') or s['category']:<28} {cond} {val}")
    if result.unmapped:
        lines.append(f"  UNMAPPED, skipped: {', '.join(sorted(set(result.unmapped)))}")
    return "\n".join(lines)
