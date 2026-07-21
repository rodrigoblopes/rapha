"""Integer units, and the rounding policy that keeps Rapha honest.

Floats are banned in every measurement path, for the same reason MrW bans them in
money paths: binary floating point cannot represent 0.1, and a system that tells you
what to eat and how much to lift should not accumulate drift it cannot explain.

Every quantity wraps an ``int`` in its base unit:

    Grams        food mass, macronutrients, bodyweight
    Kcal         energy
    Millimetres  height and tape measurements
    Seconds      durations

Rounding is never implicit. ``apply_bps`` requires a direction, because the honest
direction depends on what the number *is* — see ``protein_target`` and
``deficit_target`` below, which round opposite ways on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Self


class Rounding(Enum):
    """Which way to go when a result is not a whole number."""

    DOWN = "down"
    UP = "up"


def _require_int(value: object, unit: str) -> int:
    # bool subclasses int. Letting True through would silently become 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{unit} takes a whole number of its base unit, got {value!r} "
            f"({type(value).__name__}). Floats are banned in measurement paths."
        )
    return value


def _scale(value: int, numerator: int, denominator: int, rounding: Rounding) -> int:
    """value * numerator / denominator, as an exact integer in the stated direction."""
    product = value * numerator
    if rounding is Rounding.DOWN:
        return product // denominator
    return -(-product // denominator)


@dataclass(frozen=True, slots=True, order=True)
class _Quantity:
    """A whole number of one unit. Arithmetic never crosses unit boundaries."""

    value: int

    def __post_init__(self) -> None:
        _require_int(self.value, type(self).__name__)

    def __add__(self, other: object) -> Self:
        if type(other) is not type(self):
            return NotImplemented
        return type(self)(self.value + other.value)  # type: ignore[attr-defined]

    def __sub__(self, other: object) -> Self:
        if type(other) is not type(self):
            return NotImplemented
        return type(self)(self.value - other.value)  # type: ignore[attr-defined]

    def __mul__(self, factor: int) -> Self:
        _require_int(factor, "a scaling factor")
        return type(self)(self.value * factor)

    __rmul__ = __mul__

    def __str__(self) -> str:
        return f"{self.value}{type(self).__name__.lower()[0]}"


class Grams(_Quantity):
    """Mass, in whole grams. Bodyweight lives here too: 85 kg is 85_000 g."""

    @classmethod
    def from_kg(cls, kg: int) -> Grams:
        return cls(_require_int(kg, "Grams.from_kg") * 1_000)

    @property
    def kg_x1000(self) -> int:
        """Bodyweight in grams *is* kg x 1000 — named for callers doing per-kg maths."""
        return self.value


class Kcal(_Quantity):
    """Energy, in whole kilocalories."""


class Millimetres(_Quantity):
    """Length, in whole millimetres. Tape measurements and height."""

    @classmethod
    def from_cm(cls, cm: int) -> Millimetres:
        return cls(_require_int(cm, "Millimetres.from_cm") * 10)


class Seconds(_Quantity):
    """Duration, in whole seconds."""


def apply_bps(quantity: _Quantity, bps: int, rounding: Rounding) -> _Quantity:
    """Take ``bps`` basis points of ``quantity``. 10_000 bps = 100%.

    ``rounding`` is required. There is no sensible default: see below.
    """
    _require_int(bps, "basis points")
    return type(quantity)(_scale(quantity.value, bps, 10_000, rounding))


# ── The asymmetry ────────────────────────────────────────────────────────────
#
# The risk is not symmetric, so the rounding is not symmetric either.
#
# Under-prescribing protein during an energy deficit costs lean mass — the one
# thing a recomposition exists to protect. Over-prescribing the deficit does the
# same damage by a different route. So protein rounds UP and the deficit rounds
# DOWN, and neither direction is a default that could be inherited by accident.


def protein_target(bodyweight: Grams, g_per_kg_x10: int) -> Grams:
    """Daily protein target, rounded UP so it is never under-prescribed.

    ``g_per_kg_x10`` is grams per kg of bodyweight, times ten: 19 means 1.9 g/kg.
    """
    _require_int(g_per_kg_x10, "g_per_kg_x10")
    if g_per_kg_x10 <= 0:
        raise ValueError("protein target must be positive")
    return Grams(_scale(bodyweight.kg_x1000, g_per_kg_x10, 10_000, Rounding.UP))


def deficit_target(tdee: Kcal, deficit_bps: int) -> Kcal:
    """Daily energy target, with the *deficit* rounded DOWN so it is never harsher.

    ``deficit_bps`` is the cut against measured TDEE in basis points: 1750 = 17.5%.
    """
    _require_int(deficit_bps, "deficit_bps")
    if not 0 <= deficit_bps <= 10_000:
        raise ValueError(
            f"deficit_bps must be between 0 and 10_000 (0-100%), got {deficit_bps}"
        )
    deficit = _scale(tdee.value, deficit_bps, 10_000, Rounding.DOWN)
    return Kcal(tdee.value - deficit)
