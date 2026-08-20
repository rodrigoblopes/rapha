"""Load progression — Projeto 60 Dias, Módulo 17 (Como Progredir Cargas).

⚠️ This is the method, not a detail of it (CLAUDE.md), and it is encoded from
Cariani's own words in the Módulo 17 transcript
(`%RAPHA_HOME%/protocol/transcripts/MÓDULO 17 …`), not invented. The rule, in his
framing:

  1. The ficha fixes the REPS. You find the load that lets you hit that rep target
     with cadenced movement and proper posture — "é esse o peso que você deve
     determinar para a primeira série."
  2. Progress the load only when you complete the target reps *with facility* —
     "se tiver com facilidade de fazer 12 movimentos, mais peso."
  3. Hold the load when you cannot complete the target reps with perfect form —
     "se não conseguir fazer 12 movimentos perfeitos, mantenha o peso" — and work
     more sessions at that weight until you can.
  4. The ceiling is the rep past the target where form breaks and you start to
     cheat ("a partir da décima terceira … a querer roubar"). That is the point
     to hold, not exceed.
  5. Increments are the smallest plate available (2.5 kg, then 5 kg), or the next
     dumbbell for a beginner (1 → 2 → 3 kg).

This is **double progression**: reps are the fixed target, load is the variable,
and the two never move at once. It is autoregulated by movement quality rather
than by a fixed percentage, so this module reports a *decision* and its reasoning
— it never prescribes a specific kilo, which only the lifter, feeling the set, can
choose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Smallest sensible load steps, Cariani's own examples. Barbell first, then the
#: beginner dumbbell ladder. Kilograms ×10 to stay integer.
PLATE_STEPS_KG_X10 = (25, 50)          # 2.5 kg, 5.0 kg (a plate per side is 2×)
DUMBBELL_LADDER_KG_X10 = (10, 20, 30)  # 1, 2, 3 kg


class Decision(Enum):
    PROGRESS = "progress"   # target hit with facility -> add the smallest step
    HOLD = "hold"           # target not reached with clean form -> same load
    ESTABLISH = "establish"  # first exposure -> find the load for the rep target


@dataclass(frozen=True, slots=True)
class SetResult:
    """What actually happened on a set, as the lifter would report it."""

    target_reps: int
    completed_reps: int
    #: True if the last clean rep was the target and it still felt hard (good), as
    #: opposed to sailing past it (too light) or form breaking early (too heavy).
    form_held_to_target: bool


@dataclass(frozen=True, slots=True)
class ProgressionAdvice:
    decision: Decision
    reasoning: str


def advise(result: SetResult | None) -> ProgressionAdvice:
    """One set's outcome -> the Módulo 17 decision, with its reasoning shown.

    ``None`` means the exercise is new and no load is established yet.
    """
    if result is None:
        return ProgressionAdvice(
            Decision.ESTABLISH,
            "First exposure: pick the load you can move for the target reps with "
            "cadenced form and proper posture — that is the working weight (M17).",
        )

    target, done = result.target_reps, result.completed_reps

    # Hit the target and it was easy -> the load has been outgrown.
    if done > target or (done == target and not result.form_held_to_target):
        return ProgressionAdvice(
            Decision.PROGRESS,
            f"Completed {done} vs a target of {target} with facility — add the "
            "smallest available step (2.5 kg, then 5 kg). Reps stay fixed; only the "
            "load moves (M17 double progression).",
        )

    # Reached the target and it was genuinely hard -> hold and consolidate.
    if done == target and result.form_held_to_target:
        return ProgressionAdvice(
            Decision.HOLD,
            f"Hit the {target}-rep target but the last reps were hard and clean — "
            "hold this load and let strength catch up before adding weight (M17).",
        )

    # Fell short of the target -> too heavy; hold and build into it.
    return ProgressionAdvice(
        Decision.HOLD,
        f"Only {done} clean reps against a target of {target}: form broke before "
        "the target, so the load is too heavy. Keep it and work more sessions here "
        'until the target is reachable — "mantenha o peso" (M17).',
    )


def next_load_kg_x10(current_kg_x10: int, *, using_dumbbells: bool = False) -> int:
    """The load after a PROGRESS decision, in kg ×10. The lifter still confirms it.

    This is guidance, not a prescription: it returns the *smallest* increment,
    because M17 is explicit that you add the least weight that still lets you keep
    the rep target, never a jump.
    """
    if using_dumbbells:
        for rung in DUMBBELL_LADDER_KG_X10:
            if rung > current_kg_x10:
                return rung
        return current_kg_x10 + DUMBBELL_LADDER_KG_X10[0]
    return current_kg_x10 + PLATE_STEPS_KG_X10[0]

@dataclass(frozen=True, slots=True)
class NextSessionCall:
    """The double-progression decision for one exercise, read from real history.

    Unlike :func:`advise`, which takes a hand-reported set, this is fed straight
    from Garmin's per-set detection (:class:`~rapha.garmin.exercise_store.SetRow`),
    so it can name the load actually lifted and the concrete next step to try —
    while staying, per M17, a suggestion the lifter confirms by feel.
    """

    decision: Decision
    target_reps: int | None
    last_weight_kg_x10: int | None
    suggested_kg_x10: int | None
    bodyweight: bool
    reasoning: str


def call_from_history(
    target_reps: int | None,
    last_sets: list[tuple[int | None, int | None]],
    *,
    using_dumbbells: bool = False,
) -> NextSessionCall:
    """Last session's sets + the rep target -> the M17 call, with a concrete load.

    ``last_sets`` is ``[(reps, weight_g), ...]`` for the most recent session of one
    movement (ACTIVE sets, in order). The working load is the heaviest set; the
    reps at that load are judged against ``target_reps``. Progress adds the smallest
    step; a short session holds and builds into the weight (M17).
    """
    weighted = [(r, w) for r, w in last_sets if w is not None]

    # No history at all -> the load is not established yet.
    if not last_sets:
        return NextSessionCall(
            Decision.ESTABLISH, target_reps, None, None, False,
            "No logged history yet: pick the load you can move for the target reps "
            "with cadenced form — that becomes the working weight (M17).",
        )

    # A bodyweight movement (no set carried a load): progress by reps, not by plate.
    if not weighted:
        best = max((r or 0) for r, _ in last_sets)
        if target_reps is not None and best >= target_reps:
            return NextSessionCall(
                Decision.PROGRESS, target_reps, None, None, True,
                f"Bodyweight: hit {best} against a {target_reps}-rep target last time "
                "— add reps or a harder variation; there is no plate to add (M17).",
            )
        return NextSessionCall(
            Decision.HOLD, target_reps, None, None, True,
            f"Bodyweight: {best} reps last time, target {target_reps} — stay here "
            "until the target is clean across all sets (M17).",
        )

    top_w = max(w for _, w in weighted)
    reps_at_top = max((r or 0) for r, w in weighted if w == top_w)
    last_kg_x10 = round(top_w / 100)   # grams -> kg×10 (80000 g -> 800)

    # No rep target to judge against (a timed hold slipped through) -> just report.
    if target_reps is None:
        return NextSessionCall(
            Decision.HOLD, None, last_kg_x10, last_kg_x10, False,
            f"Last worked at {last_kg_x10 / 10:g} kg; no rep target on file to judge "
            "progression — hold and confirm by feel (M17).",
        )

    if reps_at_top >= target_reps:
        nxt = next_load_kg_x10(last_kg_x10, using_dumbbells=using_dumbbells)
        return NextSessionCall(
            Decision.PROGRESS, target_reps, last_kg_x10, nxt, False,
            f"Hit {reps_at_top} at {last_kg_x10 / 10:g} kg against a {target_reps}-rep "
            f"target — add the smallest step to {nxt / 10:g} kg. Reps stay fixed; only "
            "the load moves (M17 double progression). Confirm it by feel.",
        )
    return NextSessionCall(
        Decision.HOLD, target_reps, last_kg_x10, last_kg_x10, False,
        f"Only {reps_at_top} clean reps at {last_kg_x10 / 10:g} kg against a "
        f"{target_reps}-rep target — hold this load and work more sessions here until "
        'the target is reachable, "mantenha o peso" (M17).',
    )

