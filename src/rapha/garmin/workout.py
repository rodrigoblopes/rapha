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
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}

# Condition-type ids verified against Garmin's live API: 10 is reps (3 is DISTANCE —
# a long-standing bug in this file that never bit because we defaulted to lap-button).
_END_REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps"}
_END_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time"}
_END_LAP = {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}
_END_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations"}

#: A break between sets/exercises when the sheet does not state a rest.
DEFAULT_REST_S = 60


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


def _exercise_step(category: str, name: str | None, kind: str, value: int, note: str,
                   strategy: RepStrategy) -> dict:
    """One working set as an executable step. ``kind`` is 'reps' or 'time'."""
    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 0,  # renumbered at the end
        "stepType": _STEP_TYPES["interval"],
        "category": category,
        "exerciseName": name,
        "description": note,
    }
    if kind == "time":
        step["endCondition"] = _END_TIME
        step["endConditionValue"] = value
    elif strategy is RepStrategy.REPS:
        step["endCondition"] = _END_REPS
        step["endConditionValue"] = value
    else:
        # Lap-button: the athlete ends the set; the rep target rides in the note.
        step["endCondition"] = _END_LAP
    return step


def _rest_step(seconds: int) -> dict:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": 0,
        "stepType": _STEP_TYPES["rest"],
        "endCondition": _END_TIME,
        "endConditionValue": seconds,
    }


def _repeat_group(iterations: int, children: list[dict]) -> dict:
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": 0,
        "stepType": _STEP_TYPES["repeat"],
        "numberOfIterations": iterations,
        "smartRepeat": False,
        "endCondition": _END_ITERATIONS,
        "endConditionValue": iterations,
        "workoutSteps": children,
    }


def _group_sets(sets: list[dict]) -> list[tuple[str, int, int]]:
    """Collapse consecutive identical sets into (kind, value, count) runs.

    A pyramid 15,15,12,12 becomes [('reps',15,2), ('reps',12,2)] — two set-blocks —
    so each block is one Garmin repeat group. Varying reps that never repeat degrade
    to blocks of one, which is honest (they simply are not grouped).
    """
    runs: list[list] = []
    for s in sets:
        if s.get("reps") is not None:
            key = ("reps", s["reps"])
        elif s.get("duration") is not None:
            d = s["duration"]
            key = ("time", d["value"] if isinstance(d, dict) else d)
        else:
            continue
        if runs and runs[-1][0] == key:
            runs[-1][1] += 1
        else:
            runs.append([key, 1])
    return [(k[0], k[1], count) for k, count in runs]


def _renumber(steps: list[dict]) -> None:
    """Assign sequential stepOrder across the flattened tree (repeats then children)."""
    counter = [1]

    def walk(lst: list[dict]) -> None:
        for s in lst:
            s["stepOrder"] = counter[0]
            counter[0] += 1
            if s.get("type") == "RepeatGroupDTO":
                walk(s["workoutSteps"])

    walk(steps)


def build_workout(
    session: dict,
    *,
    name: str,
    strategy: RepStrategy = RepStrategy.REPS,
) -> BuildResult:
    """Build a Garmin strength-workout payload from one parsed session.

    Each exercise becomes one or more **set-blocks** (Garmin repeat groups): a run of
    same-rep sets is one block that repeats N times over [exercise, rest]. Putting the
    rest inside the iteration gives a break after *every* set — including the last, so
    there is a break before the next exercise. An unmapped exercise is collected and
    skipped, never silently replaced (CLAUDE.md).
    """
    steps: list[dict] = []
    unmapped: list[str] = []

    for exercise in session.get("exercises", []):
        ex_name = exercise["name"]
        try:
            garmin = map_exercise(ex_name)
        except UnmappedExercise:
            unmapped.append(ex_name)
            continue

        rest = exercise.get("rest")
        rest_secs = (rest["value"] if isinstance(rest, dict) else rest) if rest else DEFAULT_REST_S

        for kind, value, count in _group_sets(exercise.get("sets") or []):
            unit = "reps" if kind == "reps" else "s"
            note = (f"{ex_name} — {count}x{value} {unit}" if count > 1
                    else f"{ex_name} — {value} {unit}")
            ex_step = _exercise_step(garmin.category, garmin.name, kind, value, note, strategy)
            block = [ex_step, _rest_step(rest_secs)]
            if count >= 2:
                steps.append(_repeat_group(count, block))
            else:
                steps.extend(block)  # a single set needs no repeat wrapper

    _renumber(steps)
    payload = {
        "workoutName": name,
        "sportType": SPORT_STRENGTH,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": SPORT_STRENGTH, "workoutSteps": steps}
        ],
    }
    return BuildResult(payload=payload, unmapped=unmapped, strategy=strategy)


def _work_steps(steps: list[dict]) -> list[tuple[int, dict]]:
    """(iterations, executable-step) for every working set, flattening repeat groups."""
    out: list[tuple[int, dict]] = []
    for s in steps:
        if s.get("type") == "RepeatGroupDTO":
            iters = s["numberOfIterations"]
            for child in s["workoutSteps"]:
                if child["stepType"]["stepTypeKey"] == "interval":
                    out.append((iters, child))
        elif s["stepType"]["stepTypeKey"] == "interval":
            out.append((1, s))
    return out


def describe(result: BuildResult) -> str:
    """A human-readable dry-run summary of what would be created."""
    steps = result.payload["workoutSegments"][0]["workoutSteps"]
    work = _work_steps(steps)
    lines = [
        f"workout: {result.payload['workoutName']}",
        f"  strategy: {result.strategy.value}  ({len(work)} set-blocks)",
    ]
    for iters, s in work:
        cond = s["endCondition"]["conditionTypeKey"]
        val = s.get("endConditionValue", "lap")
        who = s.get("exerciseName") or s["category"]
        lines.append(f"    {who:<28} {iters}x  {cond} {val}")
    if result.unmapped:
        lines.append(f"  UNMAPPED, skipped: {', '.join(sorted(set(result.unmapped)))}")
    return "\n".join(lines)
