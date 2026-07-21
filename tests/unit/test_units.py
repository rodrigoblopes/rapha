"""Integer units, and the rounding policy that keeps Rapha honest.

Every number in this file is invented. Real body metrics never enter the repo.
"""

import pytest

from rapha.units import (
    Grams,
    Kcal,
    Millimetres,
    Rounding,
    apply_bps,
    deficit_target,
    protein_target,
)


class TestIntegerDiscipline:
    """Floats are banned in every measurement path, exactly as in MrW's Money."""

    def test_a_float_cannot_become_a_quantity(self):
        with pytest.raises(TypeError):
            Grams(1500.5)

    def test_a_bool_is_not_an_integer_here(self):
        # bool subclasses int in Python; letting it through would be a silent bug.
        with pytest.raises(TypeError):
            Kcal(True)

    def test_quantities_add_and_subtract_within_their_own_unit(self):
        assert Grams(120) + Grams(30) == Grams(150)
        assert Kcal(2400) - Kcal(400) == Kcal(2000)

    def test_units_do_not_mix(self):
        with pytest.raises(TypeError):
            Grams(120) + Kcal(120)

    def test_scaling_by_an_integer_stays_exact(self):
        assert Grams(85) * 4 == Grams(340)

    def test_kilograms_and_centimetres_are_convenience_constructors_not_floats(self):
        assert Grams.from_kg(85) == Grams(85_000)
        assert Millimetres.from_cm(177) == Millimetres(1770)


class TestRoundingIsExplicit:
    """apply_bps never guesses which way to round — the caller must say."""

    def test_rounding_down_truncates(self):
        # 2500 kcal, 17.5% -> 437.5, exact answer is not an integer
        assert apply_bps(Kcal(2500), 1750, Rounding.DOWN) == Kcal(437)

    def test_rounding_up_takes_the_ceiling(self):
        assert apply_bps(Kcal(2500), 1750, Rounding.UP) == Kcal(438)

    def test_an_exact_result_is_unaffected_by_direction(self):
        assert apply_bps(Kcal(2000), 2500, Rounding.DOWN) == Kcal(500)
        assert apply_bps(Kcal(2000), 2500, Rounding.UP) == Kcal(500)

    def test_direction_must_be_given(self):
        with pytest.raises(TypeError):
            apply_bps(Kcal(2500), 1750)  # type: ignore[call-arg]


class TestTheAsymmetryThatMatters:
    """Rapha is never optimistic about a deficit, and never stingy with protein.

    The risk is not symmetric. Under-prescribing protein during an energy deficit
    costs lean mass, which is the one thing a recomposition exists to protect.
    Over-prescribing a deficit does the same by a different route. So the two
    targets round in opposite directions, and neither is the default.
    """

    def test_protein_target_rounds_up_so_it_is_never_under_prescribed(self):
        # 84.3 kg at 1.9 g/kg = 160.17 g. Rounding down would prescribe less
        # protein than the framework asks for.
        assert protein_target(Grams(84_300), g_per_kg_x10=19) == Grams(161)

    def test_protein_target_is_exact_when_it_divides_cleanly(self):
        assert protein_target(Grams(80_000), g_per_kg_x10=20) == Grams(160)

    def test_deficit_target_rounds_the_deficit_down_so_it_is_never_harsher(self):
        # 2531 kcal measured TDEE, 17.5% deficit = 442.925 kcal.
        # Rounding the deficit UP would silently prescribe a harsher cut than asked.
        assert deficit_target(Kcal(2531), deficit_bps=1750) == Kcal(2531 - 442)

    def test_a_zero_deficit_is_maintenance(self):
        assert deficit_target(Kcal(2500), deficit_bps=0) == Kcal(2500)

    def test_a_deficit_can_never_exceed_the_expenditure_it_is_taken_from(self):
        with pytest.raises(ValueError):
            deficit_target(Kcal(2500), deficit_bps=10_001)
