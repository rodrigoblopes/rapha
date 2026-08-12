"""Navy body fat and Cariani biotype. Invented measurements."""

from rapha.rules.measurements import (
    BREVILINEO,
    LONGILINEO,
    NORMOLINEO,
    biotype,
    navy_bodyfat_pct_x10,
)


class TestNavyBodyFat:
    def test_a_known_case(self):
        # waist 93.5, neck 43.5, height 177 cm -> ~19.0% by the Navy formula.
        bf = navy_bodyfat_pct_x10(935, 435, 1770)
        assert 185 <= bf <= 195

    def test_a_leaner_waist_reads_lower(self):
        lean = navy_bodyfat_pct_x10(830, 400, 1770)
        soft = navy_bodyfat_pct_x10(1000, 400, 1770)
        assert lean < soft

    def test_a_non_positive_differential_is_none(self):
        # Neck >= waist would blow up the log; refuse rather than error.
        assert navy_bodyfat_pct_x10(400, 400, 1770) is None

    def test_women_return_none_without_a_hip(self):
        assert navy_bodyfat_pct_x10(750, 320, 1650, sex="F") is None


class TestBiotype:
    def test_short_wingspan_is_brevilineo(self):
        # 172.5 cm span vs 177 cm height — arms shorter than height.
        assert biotype(1725, 1770) == BREVILINEO

    def test_equal_is_normolineo(self):
        assert biotype(1770, 1770) == NORMOLINEO
        assert biotype(1785, 1770) == NORMOLINEO  # within the 3 cm band

    def test_long_wingspan_is_longilineo(self):
        assert biotype(1820, 1770) == LONGILINEO
