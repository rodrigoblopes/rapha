"""Read recovery from Garmin's overnight signals — a training traffic light.

Pure: a window of DailyMetrics in, a status out. The judgment combines the four
signals a wearable actually measures well overnight — HRV, resting HR, stress and
sleep — against each person's own recent baseline, not a population number. A body
compared to itself is the only fair comparison.

The output is deliberately an *observation with reasoning*, never an order. When
the signals conflict it says so; it does not silently pick training or rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from ..models import DailyMetrics


class Readiness(Enum):
    GREEN = "green"    # signals at or better than baseline — train as planned
    AMBER = "amber"    # one signal off — train, but hold something back
    RED = "red"        # several off — a deload or rest day serves you better


@dataclass(frozen=True, slots=True)
class RecoverySignal:
    label: str
    latest: float | None
    baseline: float | None
    good: bool | None          # True = favourable, False = unfavourable, None = no data
    note: str
    higher_is_better: bool = True   # which direction of this metric is the good one
    recent: str = ""               # the last few actual readings, for a "where from?" caption


@dataclass(frozen=True, slots=True)
class RecoveryRead:
    status: Readiness
    headline: str
    signals: list[RecoverySignal] = field(default_factory=list)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _fmt(value: float, unit: str) -> str:
    """A readable value for the note. Sleep hours become h:mm (9.53 -> 9h32m); the
    rest keep their integer unit (55ms, 51, 30)."""
    if unit == "h":
        hours = int(value)
        minutes = round((value - hours) * 60)
        return f"{hours}h{minutes:02d}m"
    return f"{value:.0f}{unit}"


def assess_recovery(days: list[DailyMetrics], *, today: date) -> RecoveryRead:
    """Compare the most recent night against the trailing ~3-week baseline.

    ``latest`` is the newest actual reading (what you see on Garmin this morning),
    not a multi-day mean — a 3-night average of sleep read as "last night" is
    exactly the confusion this avoids. The baseline stays the trailing average.
    """
    window = [d for d in days if today - timedelta(days=28) <= d.on <= today]
    prior = [d for d in window if d.on < today - timedelta(days=2)]

    signals: list[RecoverySignal] = []
    votes: list[bool] = []

    def add(label, getter, higher_is_better, unit, tol):
        readings = sorted((d.on, getter(d)) for d in window if getter(d) is not None)
        latest = readings[-1][1] if readings else None
        base = _mean([getter(d) for d in prior if getter(d) is not None])
        # The last 3 nights, oldest to newest, so the caption ends on the headline value.
        recent3 = " › ".join(_fmt(v, unit) for _, v in readings[-3:])
        if latest is None or base is None:
            signals.append(RecoverySignal(label, latest, base, None, "no recent reading",
                                          higher_is_better, recent3))
            return
        delta = latest - base
        favourable = (delta >= -tol) if higher_is_better else (delta <= tol)
        # "at/above baseline" for higher-is-better; "at/below" for lower-is-better
        direction = "above" if delta > 0 else ("below" if delta < 0 else "at")
        good_word = "steady" if abs(delta) <= tol else ("good" if favourable else "watch")
        signals.append(RecoverySignal(
            label, round(latest, 1), round(base, 1), favourable,
            f"{_fmt(latest, unit)} vs {_fmt(base, unit)} baseline — {direction}, {good_word}",
            higher_is_better, f"last 3: {recent3}",
        ))
        votes.append(favourable)

    add("HRV", lambda d: d.hrv_ms, True, "ms", 3)
    add("Resting HR", lambda d: d.resting_hr, False, "", 2)
    add("Stress", lambda d: d.stress_avg, False, "", 4)
    add("Sleep", lambda d: (d.sleep.value / 3600 if d.sleep else None), True, "h", 0.5)

    bad = votes.count(False)
    if not votes:
        return RecoveryRead(Readiness.AMBER, "Not enough recent data to read recovery.", signals)
    if bad == 0:
        status, head = Readiness.GREEN, "Recovered — train as planned, push the working sets."
    elif bad == 1:
        status, head = Readiness.AMBER, "Mostly recovered — train, but leave a rep in reserve."
    else:
        status, head = Readiness.RED, (
            "Several signals are down — a lighter session or a rest day will serve "
            "you better than pushing through."
        )
    return RecoveryRead(status, head, signals)
