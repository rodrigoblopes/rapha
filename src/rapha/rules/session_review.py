"""Post-session review — reading today's logged sets against the plan.

Before the session the Training tab shows a double-progression *target* per exercise
(the load to try, the rep goal). After it, Garmin's per-set detection says what was
actually lifted. This pairs the two and reads the result the way a coach would once the
bar is racked: where you progressed, where a lift stalled and what that means next time.

Pure — planned targets + logged sets in, a review out — so it is testable with invented
fixtures and holds no I/O. A sub-kilo detected load is machine noise (see progression.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_WORKING_LOAD_G = 1000


@dataclass(frozen=True, slots=True)
class Outcome:
    name: str
    target_reps: int
    expected_kg_x10: int | None   # the load the plan expected (last known)
    top_kg_x10: int | None        # today's heaviest working set
    reps_at_top: int
    verdict: str                  # progressed | held | short


@dataclass(frozen=True, slots=True)
class SessionReview:
    tonnage_kg: float
    hard_sets: int
    outcomes: list[Outcome] = field(default_factory=list)
    strong: list[str] = field(default_factory=list)
    work_on: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)


def _kg(x10: int) -> str:
    return f"{x10 / 10:g}"


def review_session(planned: list[dict], logged: dict,
                   *, recovery_status: str = "green") -> SessionReview:
    """``planned`` is ``[{name, garmin, target_reps, expected_kg_x10}]``; ``logged`` maps a
    Garmin exercise name to today's ``[(reps, weight_g), ...]``. Only movements that were
    actually logged today produce an outcome."""
    outcomes: list[Outcome] = []
    tonnage_g = 0
    hard = 0

    for pe in planned:
        sets = logged.get(pe["garmin"]) or []
        if not sets:
            continue
        weighted = [(r or 0, w) for r, w in sets if w and w >= MIN_WORKING_LOAD_G]
        for r, w in weighted:
            tonnage_g += r * w
            hard += 1

        target = pe["target_reps"]
        expected = pe.get("expected_kg_x10")
        if not weighted:                      # bodyweight movement
            best = max((r or 0) for r, _ in sets)
            outcomes.append(Outcome(pe["name"], target, None, None, best,
                                    "progressed" if best >= target else "short"))
            continue
        top_w = max(w for _, w in weighted)
        reps_at_top = max(r for r, w in weighted if w == top_w)
        top_x10 = round(top_w / 100)
        if expected is not None and top_x10 > expected:
            verdict = "progressed"
        elif reps_at_top < target:
            verdict = "short"
        else:
            verdict = "held"
        outcomes.append(Outcome(pe["name"], target, expected, top_x10, reps_at_top, verdict))

    strong, work_on = [], []
    for o in outcomes:
        nm = o.name.title()
        if o.verdict == "progressed":
            if o.top_kg_x10 is None:
                strong.append(f"{nm}: {o.reps_at_top} reps — add reps or a harder variation next")
            else:
                line = f"{nm}: {_kg(o.top_kg_x10)} kg × {o.reps_at_top}"
                if o.expected_kg_x10 and o.top_kg_x10 > o.expected_kg_x10:
                    line += f" (up from {_kg(o.expected_kg_x10)})"
                strong.append(line)
        elif o.verdict == "held":
            strong.append(f"{nm}: held {_kg(o.top_kg_x10)} kg × {o.reps_at_top}")
        else:  # short
            at = f" at {_kg(o.top_kg_x10)} kg" if o.top_kg_x10 else ""
            work_on.append(f"{nm}: {o.reps_at_top} reps{at} vs a {o.target_reps} target "
                           "— hold the load and bank a clean session before adding")

    advice: list[str] = []
    prog = sum(1 for o in outcomes if o.verdict == "progressed")
    short = sum(1 for o in outcomes if o.verdict == "short")
    if outcomes:
        if prog and not short:
            advice.append(
                "You added load across the board — a textbook session. Keep the jumps small "
                "and the last rep clean; that is what makes the next increase stick.")
        elif short:
            advice.append(
                "A lift or two stalled at the target — that is the plan working, not failing. "
                "Hold those loads and earn another clean session before adding weight, rather "
                "than grinding sloppy reps.")
        if recovery_status in ("amber", "red") and prog:
            advice.append(
                "You pushed on a morning your recovery signals were down — fine once, but if "
                "they stay low, an easier session protects the progress you just made.")
        advice.append(
            f"Total work today was {tonnage_g / 1000:.0f} kg moved across {hard} hard sets. "
            "What matters is whether that trends up week over week — the tonnage bars on the "
            "Performance tab are the honest signal.")

    return SessionReview(round(tonnage_g / 1000, 1), hard, outcomes, strong, work_on, advice)
