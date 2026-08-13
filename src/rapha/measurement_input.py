"""Turn the measurement form's human units into a canonical Measurement.

The portal collects centimetres and kilograms because that is what a tape and a
scale read; the store speaks integer millimetres and grams (no float ever touches a
measurement path). This is the one place that conversion and validation lives, kept
pure so it is testable without a server.

Blank fields are simply omitted — the store merges, so an entry that fills only the
waist leaves every other field untouched. That is the point: you can log one number
today and another next week without wiping the first.
"""

from __future__ import annotations

from datetime import date

from .models import Measurement, Source
from .units import Grams, Millimetres

#: Circumference (and span) fields the form offers, all entered in centimetres.
CM_FIELDS = ["waist", "neck", "hip", "chest", "arm", "thigh", "shoulders",
             "calf", "wingspan"]


class MeasurementError(ValueError):
    """Input we will not store — bad number, out-of-range, future date, or empty."""


def _to_mm(value, name: str) -> int:
    try:
        cm = float(value)
    except (TypeError, ValueError):
        raise MeasurementError(f"{name}: '{value}' is not a number") from None
    if not (0 < cm <= 300):
        raise MeasurementError(f"{name}: {cm} cm is out of range")
    return round(cm * 10)


def measurement_from_form(data: dict, *, today: date | None = None) -> Measurement:
    """Validate + convert the form dict. Raises MeasurementError on anything bad."""
    today = today or date.today()

    raw_date = str(data.get("date") or "").strip()
    try:
        on = date.fromisoformat(raw_date) if raw_date else today
    except ValueError:
        raise MeasurementError(f"'{raw_date}' is not a valid date") from None
    if on > today:
        raise MeasurementError("that date is in the future")

    fields: dict[str, Millimetres] = {}
    for name in CM_FIELDS:
        value = data.get(name)
        if value not in (None, ""):
            fields[name] = Millimetres(_to_mm(value, name))

    weight = None
    w = data.get("weight")
    if w not in (None, ""):
        try:
            kg = float(w)
        except (TypeError, ValueError):
            raise MeasurementError(f"weight: '{w}' is not a number") from None
        if not (0 < kg <= 500):
            raise MeasurementError(f"weight: {kg} kg is out of range")
        weight = Grams(round(kg * 1000))

    notes = str(data.get("notes") or "").strip() or None

    if not fields and weight is None and notes is None:
        raise MeasurementError("nothing to record — fill in at least one field")

    return Measurement(on=on, source=Source.MANUAL, weight=weight, notes=notes, **fields)
