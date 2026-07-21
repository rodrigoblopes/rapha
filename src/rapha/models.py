"""Canonical records.

Every adapter emits these, and the rules engine reads only these. That seam is what
lets a fallback rung — a `.FIT` export, a browser-retrieved file — swap in for the
Garmin API without anything downstream noticing (CLAUDE.md, fallback ladder).

Which is why `source` is on every record and never inferred: when a number looks
wrong, the first question is always where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from .units import Grams, Kcal, Millimetres, Seconds


class Source(Enum):
    """How a record arrived. Rungs of the fallback ladder, plus the manual paths."""

    GARMIN_API = "garmin_api"
    GARMIN_BROWSER = "garmin_browser"
    GARMIN_EXPORT = "garmin_export"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class DailyMetrics:
    """One day of whole-body measurements.

    Every field but the date is optional, and ``None`` means *not measured* — which
    is a different fact from zero. A day with no watch on the wrist has no resting
    HR; recording that as 0 would drag every average it touches.
    """

    on: date
    source: Source
    resting_hr: int | None = None
    hrv_ms: int | None = None
    sleep: Seconds | None = None
    steps: int | None = None
    #: Total daily energy expenditure as the device measured it. The input to
    #: the TDEE average (ADR-005) — not an estimate from a formula.
    calories_total: Kcal | None = None
    calories_active: Kcal | None = None
    stress_avg: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None
    vo2max_x10: int | None = None
    weight: Grams | None = None


@dataclass(frozen=True, slots=True)
class Activity:
    """One recorded session. Garmin's own id is the natural key within a window."""

    activity_id: str
    start: datetime
    kind: str
    duration: Seconds
    source: Source
    distance_m: int | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    training_load_x10: int | None = None
    calories: Kcal | None = None


@dataclass(frozen=True, slots=True)
class Measurement:
    """A manual tape-and-scale entry.

    Without a body-composition scale this is the only series that can separate fat
    loss from weight loss: waist and neck through the Navy formula. Photos and
    strength progression corroborate it; scale weight alone cannot (CLAUDE.md).
    """

    on: date
    source: Source = Source.MANUAL
    weight: Grams | None = None
    waist: Millimetres | None = None
    neck: Millimetres | None = None
    hip: Millimetres | None = None
