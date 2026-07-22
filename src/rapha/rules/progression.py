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
