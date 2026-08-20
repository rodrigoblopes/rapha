"""Training volume — the master 'am I doing more work over time' signal.

Two numbers matter for a recomposition/hypertrophy block, and neither is on a watch
face: **tonnage** (Σ reps × load, the total mechanical work moved) and **hard sets**
(working sets taken near a real load — the accepted driver of hypertrophy). Trended by
week, a rising line is progress in the one currency that compounds; a flat line at
constant bodyweight is a plateau no single-session number reveals.

Pure: a flat list of sets in, a week-by-week series out. Weight is integer grams and
reps integer counts, exactly as Garmin detects them; tonnage is reported in kilograms.
A sub-kilo load is detection noise (see progression.py) and is not counted as a hard set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: Below this a detected "load" is machine noise, not a working set (see progression.py).
MIN_WORKING_LOAD_G = 1000


@dataclass(frozen=True, slots=True)
class WeekVolume:
    """One ISO week of training work."""

    week_start: date          # the Monday of the week
    tonnage_kg: float         # Σ reps × load over the week, in kilograms
    hard_sets: int            # working sets carrying a real load
    total_sets: int           # every logged working set, loaded or not
    sessions: int             # distinct training days that week


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_volume(
    sets: list[tuple[date, int | None, int | None, str | None]],
    *,
    weeks: int = 12,
    today: date | None = None,
) -> list[WeekVolume]:
    """Group sets into the last ``weeks`` ISO weeks, oldest first.

    Each set is ``(on_date, reps, weight_g, category)``. Every week in the window is
    represented, even one with no training (a zero row) — a gap in the bars is itself
    the signal. ``today`` defaults to the newest set's date so a stale DB still renders.
    """
    if not sets:
        return []
    anchor = today or max(on for on, *_ in sets)
    this_monday = _monday(anchor)
    window_start = this_monday - timedelta(weeks=weeks - 1)

    buckets: dict[date, dict] = {
        this_monday - timedelta(weeks=w): {"t": 0, "hard": 0, "total": 0, "days": set()}
        for w in range(weeks)
    }
    for on, reps, weight_g, _cat in sets:
        wk = _monday(on)
        if wk < window_start or wk > this_monday:
            continue
        b = buckets[wk]
        b["total"] += 1
        b["days"].add(on)
        if weight_g and weight_g >= MIN_WORKING_LOAD_G:
            b["hard"] += 1
            b["t"] += (reps or 0) * weight_g
    return [
        WeekVolume(
            week_start=wk,
            tonnage_kg=round(buckets[wk]["t"] / 1000, 1),
            hard_sets=buckets[wk]["hard"],
            total_sets=buckets[wk]["total"],
            sessions=len(buckets[wk]["days"]),
        )
        for wk in sorted(buckets)
    ]


def trend(series: list[WeekVolume]) -> float | None:
    """Signed change in weekly tonnage from the first to the last non-empty week.

    The honest headline: are you moving more total load now than at the start of the
    window? ``None`` if fewer than two training weeks exist to compare.
    """
    trained = [w for w in series if w.tonnage_kg > 0]
    if len(trained) < 2:
        return None
    return round(trained[-1].tonnage_kg - trained[0].tonnage_kg, 1)
