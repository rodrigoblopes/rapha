"""Parsing the TACO food-composition table.

Fixture rows reproduce TACO's real column layout with invented foods and numbers.
"""

from rapha.protocol.taco import FoodItem, parse_row


class TestRowParsing:
    # <number> <name> <umidade> <kcal> <kJ> <protein> <lipids> <chol> <carb> <fibre> <ash> <ca>
    ROW = "401 Arroz, invented, cru 12,0 358 1498 7,2 1,0 NA 78,8 1,6 0,5 4"

    def test_number_and_name(self):
        item = parse_row(self.ROW)
        assert item.number == 401
        assert item.name == "Arroz, invented, cru"

    def test_energy_is_whole_kcal(self):
        assert parse_row(self.ROW).kcal == 358

    def test_macros_are_decigrams_so_a_decimal_stays_exact(self):
        item = parse_row(self.ROW)
        # 7,2 g protein -> 72 dg; 78,8 carb -> 788; 1,0 fat -> 10
        assert item.protein_dg == 72
        assert item.carb_dg == 788
        assert item.fat_dg == 10

    def test_a_multiword_name_with_commas(self):
        item = parse_row("500 Frango, invented, grelhado 60,0 220 920 31,5 9,1 100 0,0 0,0 1,2 5")
        assert item.name == "Frango, invented, grelhado"
        assert item.protein_dg == 315


class TestSentinelsAreNotZero:
    """Tr / NA / * are trace, not-analysed, not-applicable — never zero.

    Folding them to 0 would under-count that nutrient in every menu total it
    enters, and the total would look authoritative.
    """

    def test_trace_becomes_none(self):
        # protein column is Tr
        item = parse_row("601 Cafe, invented, coado 99,0 2 8 Tr 0,0 NA 0,3 Tr Tr 2")
        assert item.protein_dg is None

    def test_not_analysed_becomes_none(self):
        item = parse_row("602 Fruit, invented, cru 88,0 43 180 1,0 0,3 NA 10,3 NA 0,3 1")
        assert item.fibre_dg is None

    def test_a_real_zero_is_kept(self):
        item = parse_row("603 Oil, invented 0,0 884 3699 0,0 100,0 0 0,0 0,0 0,0 0")
        assert item.protein_dg == 0
        assert item.carb_dg == 0


class TestNonRows:
    def test_a_header_line_is_not_a_food(self):
        assert parse_row("Numero do Umidade Energia Proteina Lipideos") is None

    def test_prose_is_not_a_food(self):
        assert (
            parse_row("As fases III e IV do projeto TACO contemplaram a analise")
            is None
        )

    def test_a_row_without_enough_columns_is_rejected(self):
        assert parse_row("700 Something 12,0 100") is None

    def test_a_bare_number_line_is_rejected(self):
        # The minerals pages repeat the food number with no name.
        assert parse_row("156 24 0,16 26 0,3 Tr 328 0,05 0,2 NA") is None


class TestType:
    def test_it_returns_a_fooditem(self):
        assert isinstance(parse_row(TestRowParsing.ROW), FoodItem)
