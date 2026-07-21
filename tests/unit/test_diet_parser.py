"""Parsing the calorie-calculated diet models.

Fixtures reproduce the *shape* of the models with invented foods and amounts.
"""

from rapha.protocol.diet_pdf import parse_portions, split_alternatives
from rapha.units import Grams


class TestPortions:
    def test_grams_are_read_per_food(self):
        portions = parse_portions("100g de arroz, 120g de frango grelhado,")

        assert [(p.food, p.amount) for p in portions] == [
            ("arroz", Grams(100)),
            ("frango grelhado", Grams(120)),
        ]

    def test_ad_libitum_food_carries_no_mass(self):
        """`à vontade` is not a quantity.

        Inventing a number for it would put a fabricated figure straight into a
        macro total, and it would look exactly as authoritative as a real one.
        """
        portions = parse_portions("Vegetais á vontade")

        assert len(portions) == 1
        assert portions[0].unlimited
        assert portions[0].amount is None

    def test_a_line_mixing_weighed_and_unlimited_food(self):
        portions = parse_portions("Folhas a vontade + 50g de legumes no vapor .")

        weighed = [p for p in portions if p.amount]
        unlimited = [p for p in portions if p.unlimited]
        assert weighed[0].amount == Grams(50)
        assert len(unlimited) == 1

    def test_countable_units_are_not_grams(self):
        portions = parse_portions("Wrap 2 unidades + 2 ovos")

        counts = {p.unit_count for p in portions if p.unit_count}
        assert counts == {2}
        assert all(p.amount is None for p in portions if p.unit_count)


class TestAlternativesAreChoicesNotAdditions:
    """`OU` means or.

    Treating alternatives as additive would roughly double a model's calories —
    the most damaging arithmetic error available in this file, and one that would
    produce a plausible-looking menu.
    """

    def test_ou_splits_into_separate_alternatives(self):
        alts = split_alternatives(
            "120g de macarrao com 100g de patinho OU 150g de atum em agua"
        )

        assert len(alts) == 2

    def test_the_alternatives_are_not_summed(self):
        alts = split_alternatives("120g de macarrao OU 135g de frango")
        total_if_summed = sum(
            p.amount.value for a in alts for p in a.portions if p.amount
        )
        first_only = sum(p.amount.value for p in alts[0].portions if p.amount)

        assert first_only == 120
        assert total_if_summed == 255, "guards the fixture; the meal is 120 OR 135"

    def test_a_single_option_yields_one_alternative(self):
        alts = split_alternatives("140g de arroz, 120g de patinho moido.")

        assert len(alts) == 1
        assert len(alts[0].portions) == 2
