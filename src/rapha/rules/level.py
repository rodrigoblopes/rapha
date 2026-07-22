"""Decide the Projeto 60 Dias starting level from real training history.

⚠️ **The user asked not to have this guessed** (CLAUDE.md). So this reads the
actual Garmin record and *shows its evidence*, and it never returns a bare verdict.

⚠️ **Provisional criteria.** Módulo 18's *Auto Check* is the course's own
self-assessment, and it is video-only until transcription runs. Until then, the
Garmin-history half below uses a documented, defensible heuristic, and every
result says so. When the Auto Check transcript exists, its questions are folded in
and this note comes out.

The heuristic rests on the two signals that actually distinguish the levels in a
resistance programme — how *often* and how *consistently* someone has been lifting
— not on how much they can lift, which Garmin does not know. The bands are
deliberately conservative: recommending too advanced a sheet risks injury, while
too easy a sheet only costs a fortnight, so ambiguity resolves downward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..models import Activity

#: Garmin activity type keys that count as resistance training.
STRENGTH_KINDS = frozenset(
    {"strength_training", "indoor_cardio", "fitness_equipment", "bouldering"}
)

INICIANTE = "INICIANTE"
INTERMEDIARIO = "INTERMEDIÁRIO"
AVANCADO = "AVANÇADO"


@dataclass(frozen=True, slots=True)
class LevelEvidence:
    """What the recommendation is built from — shown, never hidden behind a verdict."""

    weeks_observed: int
    strength_sessions: int
    sessions_per_week: float
    active_weeks: int
    consistency: float          # fraction of weeks with >=1 strength session
    longest_gap_days: int
    recommendation: str
    module: str                 # which Cariani module the level maps to
    reasoning: list[str]
    provisional: bool = True    # until Módulo 18 Auto Check is folded in
    notes: list[str] = field(default_factory=list)


#: Level -> the Cariani module that holds its sheets.
LEVEL_MODULE = {
    INICIANTE: "MÓDULO 03 (Iniciantes)",
    INTERMEDIARIO: "MÓDULO 04 (Intermediário)",
    AVANCADO: "MÓDULO 05 (Avançados)",
}


def _strength(activities: list[Activity]) -> list[Activity]:
    return [a for a in activities if a.kind in STRENGTH_KINDS]


def assess_level(
    activities: list[Activity], *, today: date, weeks: int = 52
) -> LevelEvidence:
    """Recommend a starting level from the training history in the window."""
    since = today - timedelta(weeks=weeks)
    window = [a for a in activities if since <= a.start.date() <= today]
    strength = _strength(window)

    # Group strength sessions by ISO week.
    weeks_with: dict[tuple[int, int], int] = {}
    for a in strength:
        iso = a.start.isocalendar()
        key = (iso.year, iso.week)
        weeks_with[key] = weeks_with.get(key, 0) + 1

    active_weeks = len(weeks_with)
    per_week = round(len(strength) / weeks, 2) if weeks else 0.0
    consistency = round(active_weeks / weeks, 2) if weeks else 0.0

    # Longest gap between consecutive strength sessions (readaptation risk).
    days = sorted({a.start.date() for a in strength})
    longest_gap = max(
        ((b - a).days for a, b in zip(days, days[1:], strict=False)), default=weeks * 7
    )

    reasoning: list[str] = []
    notes: list[str] = []

    if not strength:
        recommendation = INICIANTE
        reasoning.append(
            "no resistance sessions found in the window — start from the "
            "adaptation block (MÓDULO 02) then Iniciantes"
        )
        notes.append(
            "Garmin may not tag gym sessions as strength; if you have been "
            "training, the Auto Check will correct this."
        )
    else:
        recent = [a for a in strength if a.start.date() >= today - timedelta(weeks=8)]
        recent_per_week = len(recent) / 8

        # Consistency over the last two months is what actually gates the level.
        if recent_per_week >= 3 and consistency >= 0.6 and longest_gap <= 21:
            recommendation = AVANCADO
            reasoning.append(
                f"{recent_per_week:.1f} strength sessions/week over the last 8 weeks, "
                f"{consistency:.0%} of the year with at least one session, longest "
                f"gap {longest_gap} days — a consistent, high-frequency history"
            )
        elif recent_per_week >= 2 and consistency >= 0.3:
            recommendation = INTERMEDIARIO
            reasoning.append(
                f"{recent_per_week:.1f} strength sessions/week recently and "
                f"{consistency:.0%} of weeks active — an established but not maximal "
                "training history"
            )
        else:
            recommendation = INICIANTE
            reasoning.append(
                f"only {recent_per_week:.1f} strength sessions/week recently — the "
                "history is light or interrupted, so start conservative"
            )

        if longest_gap > 28:
            notes.append(
                f"a {longest_gap}-day gap appears in the history; connective tissue "
                "readapts slower than muscle, so the first fortnight should feel easy"
            )

    reasoning.append(
        "provisional: Módulo 18 (Auto Check) is video-only and not yet transcribed; "
        "this reads Garmin history alone and resolves ambiguity toward the easier "
        "sheet, because too-easy costs a fortnight and too-hard risks injury"
    )

    return LevelEvidence(
        weeks_observed=weeks,
        strength_sessions=len(strength),
        sessions_per_week=per_week,
        active_weeks=active_weeks,
        consistency=consistency,
        longest_gap_days=longest_gap,
        recommendation=recommendation,
        module=LEVEL_MODULE[recommendation],
        reasoning=reasoning,
        provisional=True,
        notes=notes,
    )
