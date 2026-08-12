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


@dataclass(frozen=True, slots=True)
class RecoveryRead:
    status: Readiness
    headline: str
    signals: list[RecoverySignal] = field(default_factory=list)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def assess_recovery(days: list[DailyMetrics], *, today: date) -> RecoveryRead:
    """Compare the last night or two against the trailing ~3-week baseline."""
    window = [d for d in days if today - timedelta(days=28) <= d.on <= today]
    recent = [d for d in window if d.on >= today - timedelta(days=2)]
    prior = [d for d in window if d.on < today - timedelta(days=2)]

    signals: list[RecoverySignal] = []
    votes: list[bool] = []

    def add(label, getter, higher_is_better, unit, tol):
        latest = _mean([getter(d) for d in recent if getter(d) is not None])
        base = _mean([getter(d) for d in prior if getter(d) is not None])
        if latest is None or base is None:
            signals.append(RecoverySignal(label, latest, base, None, "no recent reading",
                                          higher_is_better))
            return
        delta = latest - base
        favourable = (delta >= -tol) if higher_is_better else (delta <= tol)
        # "at/above baseline" for higher-is-better; "at/below" for lower-is-better
        direction = "above" if delta > 0 else ("below" if delta < 0 else "at")
        good_word = "steady" if abs(delta) <= tol else ("good" if favourable else "watch")
        signals.append(RecoverySignal(
            label, round(latest, 1), round(base, 1), favourable,
            f"{latest:.0f}{unit} vs {base:.0f}{unit} baseline — {direction}, {good_word}",
            higher_is_better,
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
