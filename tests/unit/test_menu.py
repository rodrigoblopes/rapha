"""The menu generator: model selection, TACO matching, honest totals.

All foods and numbers here are invented.
"""

from rapha.rules.menu import (
    build_food_index,
    choose_model,
    cost_portion,
    match_food,
    total_day,
)
from rapha.units import Grams, Kcal


def _food(number, name, kcal, p, c, f):
    return {"number": number, "name": name, "kcal": kcal,
            "protein_dg": p, "carb_dg": c, "fat_dg": f}


FOODS = [
    _food(1, "Arroz, tipo 1, cozido", 128, 25, 281, 2),
    _food(2, "Arroz, doce", 200, 30, 400, 20),
    _food(3, "Frango, peito, grelhado", 159, 320, 0, 25),
    _food(4, "Batata, doce, cozida", 77, 6, 184, 1),
]
INDEX = build_food_index(FOODS)

DIETS = [
    {"kcal": 1500, "warnings": [], "meals": []},
    {"kcal": 2000, "warnings": [], "meals": []},
    {"kcal": 2500, "warnings": [], "meals": []},
    {"kcal": 3000, "warnings": ["half parsed"], "meals": []},
]


class TestFoodMatching:
    def test_a_plain_ingredient_prefers_the_plain_food(self):
        # "arroz" should match "Arroz, tipo 1, cozido", not "Arroz, doce".
        match = match_food("arroz", FOODS, INDEX)
        assert match["number"] == 1

    def test_a_cooking_method_does_not_prevent_a_match(self):
        match = match_food("frango grelhado", FOODS, INDEX)
        assert match["number"] == 3

    def test_an_unknown_food_returns_none_rather_than_a_wrong_guess(self):
        # A zero-overlap guess is worse than admitting the food is unmatched.
        assert match_food("quinoa", FOODS, INDEX) is None


class TestCosting:
    def test_macros_scale_with_grams(self):
        p = cost_portion({"food": "arroz", "amount": 200}, FOODS, INDEX)
        assert p.kcal == 256          # 128 * 200 / 100
        assert p.protein_dg == 50     # 25 dg * 200 / 100
        assert p.matched_to == "Arroz, tipo 1, cozido"

    def test_amount_from_extracted_json_is_an_encoded_grams(self):
        # The diet parser stores a Grams, which serialises to {"value": N}. The
        # menu must read that, not only the bare int used in these fixtures.
        p = cost_portion({"food": "arroz", "amount": {"value": 150}}, FOODS, INDEX)
        assert p.grams == 150
        assert p.kcal == 192  # 128 * 150 / 100

    def test_an_unmatched_food_keeps_its_grams_but_has_no_macros(self):
        p = cost_portion({"food": "quinoa", "amount": 80}, FOODS, INDEX)
        assert p.grams == 80
        assert p.kcal is None
        assert p.matched_to is None

    def test_an_unlimited_vegetable_contributes_nothing_and_is_flagged(self):
        p = cost_portion({"food": "vegetais", "unlimited": True}, FOODS, INDEX)
        assert p.unlimited
        assert p.kcal == 0


class TestTotalsAreHonest:
    def test_an_unmatched_food_is_reported_not_silently_zero(self):
        """The failure that costs muscle in a recomposition.

        A silently skipped ingredient makes the day's protein look lower than it
        is. The gap has to be visible, so unmatched foods are listed with totals.
        """
        portions = [
            cost_portion({"food": "arroz", "amount": 100}, FOODS, INDEX),
            cost_portion({"food": "quinoa", "amount": 100}, FOODS, INDEX),
        ]
        totals = total_day(portions)

        assert totals.kcal == Kcal(128)
        assert totals.unmatched == ["quinoa"]

    def test_a_fully_matched_day_reports_no_gaps(self):
        portions = [
            cost_portion({"food": "arroz", "amount": 100}, FOODS, INDEX),
            cost_portion({"food": "frango grelhado", "amount": 100}, FOODS, INDEX),
        ]
        totals = total_day(portions)

        assert totals.unmatched == []
        assert totals.protein == Grams(2 + 32)  # 2.5 -> 2 (int g), 32.0

    def test_unlimited_vegetables_do_not_inflate_the_total(self):
        portions = [
            cost_portion({"food": "arroz", "amount": 100}, FOODS, INDEX),
            cost_portion({"food": "folhas", "unlimited": True}, FOODS, INDEX),
        ]
        assert total_day(portions).kcal == Kcal(128)


class TestModelSelection:
    def test_the_nearest_calorie_model_is_chosen(self):
        assert choose_model(DIETS, Kcal(2100))["kcal"] == 2000

    def test_a_warned_model_is_never_chosen_even_if_nearest(self):
        # 3000 is nearest to 2900, but it is half-parsed, so 2500 wins.
        assert choose_model(DIETS, Kcal(2900))["kcal"] == 2500

    def test_no_usable_model_returns_none(self):
        assert choose_model([{"kcal": None, "warnings": []}], Kcal(2000)) is None
