"""Energy and macronutrient targets.

⚠️ **TDEE is measured, not estimated** (ADR-005). Mifflin-St Jeor exists because
most people cannot measure energy expenditure; this user wears a device that
estimates it daily from heart rate and movement. The activity multiplier is the
largest error term in the formula approach, and it is exactly the term the watch
replaces with observation.

The formula is kept — as a *cross-check only*. If measured and predicted disagree
wildly, that indicates a data problem (a week the watch was off the wrist, a
miscalibrated device), and Rapha says so rather than trusting either silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..models import DailyMetrics
from ..units import Grams, Kcal, Rounding, apply_bps, deficit_target, protein_target

#: Below this many measured days, an average is noise wearing an average's clothes.
MIN_DAYS_FOR_TDEE = 7

#: Beyond this gap between measured and predicted, distrust the data.
SANITY_GAP_BPS = 3000  # 30%


def measured_tdee(
    days: list[DailyMetrics], *, window_days: int, today: date
) -> Kcal | None:
    """Mean total daily expenditure over the trailing window.

    A day with no ``calories_total`` is *skipped*, not counted as zero — the watch
    was off the wrist, and averaging in a zero would drag the target down and
    prescribe an unintended extra deficit.
    """
    since = today - timedelta(days=window_days)
    values = [
        d.calories_total.value
        for d in days
        if d.calories_total is not None and since <= d.on <= today
    ]
    if len(values) < MIN_DAYS_FOR_TDEE:
        return None
    return Kcal(sum(values) // len(values))


def predicted_bmr(
    weight: Grams, height_mm: int, age_years: int, sex: str
) -> Kcal:
    """Mifflin-St Jeor, in integers. A cross-check, never the primary source."""
    kg_x10 = weight.value // 100          # grams -> kg x 10
    cm_x10 = height_mm                    # mm    -> cm x 10
    # 10*kg + 6.25*cm - 5*age + (5 | -161), scaled by 10 then divided back.
    scaled = 100 * kg_x10 + 625 * cm_x10 // 10 - 50 * age_years
    scaled += 50 if sex.upper().startswith("M") else -1610
    return Kcal(scaled // 10)


@dataclass(frozen=True, slots=True)
class EnergyTargets:
    tdee: Kcal
    intake: Kcal
    protein: Grams
    deficit_bps: int
    window_days: int
    days_measured: int
    notes: list[str]


def targets(
    days: list[DailyMetrics],
    weight: Grams,
    *,
    window_days: int,
    deficit_bps: int,
    protein_g_per_kg_x10: int,
    today: date,
    height_mm: int | None = None,
    age_years: int | None = None,
    sex: str = "M",
) -> EnergyTargets | None:
    tdee = measured_tdee(days, window_days=window_days, today=today)
    if tdee is None:
        return None

    notes: list[str] = []

    if height_mm and age_years:
        predicted = predicted_bmr(weight, height_mm, age_years, sex)
        gap = abs(tdee.value - predicted.value)
        if gap > apply_bps(predicted, SANITY_GAP_BPS, Rounding.UP).value:
            # Not a reason to switch to the formula — a reason to distrust the data.
            notes.append(
                f"measured TDEE ({tdee.value} kcal) is far from predicted BMR "
                f"({predicted.value} kcal). Check for days the watch was not worn "
                "before relying on this target."
            )

    since = today - timedelta(days=window_days)
    measured_days = sum(
        1 for d in days if d.calories_total is not None and since <= d.on <= today
    )
    if measured_days < window_days:
        notes.append(
            f"{measured_days} of {window_days} days had an expenditure reading; "
            "the average is over those days only"
        )

    return EnergyTargets(
        tdee=tdee,
        intake=deficit_target(tdee, deficit_bps=deficit_bps),
        protein=protein_target(weight, g_per_kg_x10=protein_g_per_kg_x10),
        deficit_bps=deficit_bps,
        window_days=window_days,
        days_measured=measured_days,
        notes=notes,
    )
