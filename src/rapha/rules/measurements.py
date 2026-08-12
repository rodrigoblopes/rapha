"""Body composition from tape measurements.

The US Navy circumference method for body fat, and Cariani's Módulo 18 biotype
classification (wingspan vs height). Both are estimates — but unlike the scale and
the mirror, they are *repeatable* every 15 days, which is what makes a trend real.

Measurements are stored as integer millimetres. Body fat is a derived statistic, so
the log arithmetic runs in float and returns a rounded whole-tenth of a percent
(×10) — no measurement is stored as a float.
"""

from __future__ import annotations

import math

BREVILINEO = "brevilíneo"
NORMOLINEO = "normolíneo"
LONGILINEO = "longilíneo"


def navy_bodyfat_pct_x10(
    waist_mm: int, neck_mm: int, height_mm: int, *, sex: str = "M"
) -> int | None:
    """US Navy circumference body-fat %, ×10 (e.g. 190 = 19.0%). Men only.

    Women's formula needs a hip circumference too, which isn't collected here, so
    it returns None rather than a wrong number.
    """
    if not sex.upper().startswith("M"):
        return None
    waist, neck, height = waist_mm / 10, neck_mm / 10, height_mm / 10
    if waist - neck <= 0 or height <= 0:
        return None
    denom = (
        1.0324
        - 0.19077 * math.log10(waist - neck)
        + 0.15456 * math.log10(height)
    )
    if denom <= 0:
        return None
    return round((495 / denom - 450) * 10)


def biotype(wingspan_mm: int, height_mm: int, *, tol_mm: int = 30) -> str:
    """Cariani Módulo 18: build from wingspan vs height.

    Longilíneo (long limbs) if the span clears height by more than the tolerance,
    brevilíneo (short limbs) if it falls short by more, normolíneo in the band
    between — a ~3 cm tolerance, since a hair either way is not a real difference.
    """
    diff = wingspan_mm - height_mm
    if diff > tol_mm:
        return LONGILINEO
    if diff < -tol_mm:
        return BREVILINEO
    return NORMOLINEO
