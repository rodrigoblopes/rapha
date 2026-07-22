"""The target-hitting menu builder.

Unlike the fuzzy model-costing, this solves portions so the day lands on the
calorie and protein targets. The tests pin that it actually hits them.
"""

from rapha.rules.targeted_menu import CURATED, build_targeted_day
from rapha.units import Grams, Kcal


class TestItHitsTheTargets:
    def test_calories_land_within_tolerance(self):
        day = build_targeted_day(Kcal(2050), Grams(161))
        assert abs(day.total_kcal.value - 2050) <= 40

    def test_protein_lands_within_tolerance(self):
        day = build_targeted_day(Kcal(2050), Grams(161))
        assert abs(day.total_protein.value - 161) <= 5

    def test_a_different_target_also_lands(self):
        day = build_targeted_day(Kcal(2500), Grams(180))
        assert abs(day.total_kcal.value - 2500) <= 40
        assert abs(day.total_protein.value - 180) <= 5

    def test_fat_stays_in_a_sane_range(self):
        # Not a starvation-fat day, not a keto day: fat should land near 25-35% kcal.
        day = build_targeted_day(Kcal(2050), Grams(161))
        fat_kcal = day.total_fat.value * 9
        assert 0.20 <= fat_kcal / day.total_kcal.value <= 0.40


class TestTheMealsAreReal:
    def test_every_meal_has_foods_with_grams(self):
        day = build_targeted_day(Kcal(2050), Grams(161))
        assert len(day.meals) == 5
        for meal in day.meals:
            assert meal.items
            assert all(it.grams > 0 for it in meal.items)

    def test_portions_are_rounded_to_something_weighable(self):
        day = build_targeted_day(Kcal(2050), Grams(161))
        for meal in day.meals:
            for it in meal.items:
                assert it.grams % 5 == 0, f"{it.food} = {it.grams} g is not a round portion"

    def test_curated_foods_carry_real_taco_macros(self):
        # Spot-check a couple against the numbers pulled from TACO.
        assert CURATED["arroz"].kcal == 128
        assert CURATED["frango"].protein_dg == 320  # 32.0 g/100g


class TestMacrosAddUp:
    def test_the_reported_total_equals_the_sum_of_items(self):
        day = build_targeted_day(Kcal(2050), Grams(161))
        kcal = sum(it.kcal for meal in day.meals for it in meal.items)
        assert kcal == day.total_kcal.value
