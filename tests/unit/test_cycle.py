"""Resolving today to a training day through the sheet's rotation."""

from datetime import date

from rapha.rules.cycle import resolve

# A 4-distinct-day sheet that repeats: 5->1, 6->2, 7 rest, 8->3, 9->4, 10 restarts.
PROGRAMME = {
    "sessions": [
        {"day": 1, "focus": "PERNAS", "exercises": []},
        {"day": 2, "focus": "PEITO", "exercises": []},
        {"day": 3, "focus": "COSTAS", "exercises": []},
        {"day": 4, "focus": "OMBRO", "exercises": []},
    ],
    "rotation": [
        {"day": 5, "repeats_day": 1},
        {"day": 6, "repeats_day": 2},
        {"day": 7, "is_rest": True},
        {"day": 8, "repeats_day": 3},
        {"day": 9, "repeats_day": 4},
        {"day": 10, "restarts_cycle": True},
    ],
}
START = date(2026, 7, 1)


class TestPositionInProtocol:
    def test_day_one_is_the_first_session(self):
        pos = resolve(PROGRAMME, start=START, today=START)
        assert pos.day_of_protocol == 1
        assert pos.session_day == 1
        assert pos.note == "PERNAS"

    def test_before_the_start_is_reported_not_negative(self):
        pos = resolve(PROGRAMME, start=START, today=date(2026, 6, 28))
        assert "not started" in pos.note

    def test_it_caps_at_sixty_days(self):
        pos = resolve(PROGRAMME, start=START, today=date(2027, 1, 1))
        assert pos.day_of_protocol == 60


class TestRotation:
    def test_a_rest_day_is_rest(self):
        # cycle length is 9 (restart at 10). Day 7 is the rest day.
        pos = resolve(PROGRAMME, start=START, today=START.replace(day=7))
        assert pos.is_rest
        assert pos.session_day is None

    def test_a_repeat_day_maps_back_to_its_source(self):
        # Day 5 repeats day 1.
        pos = resolve(PROGRAMME, start=START, today=START.replace(day=5))
        assert pos.session_day == 1

    def test_the_cycle_restarts(self):
        # Day 10 -> cycle_day 1 again (cycle length 9).
        pos = resolve(PROGRAMME, start=START, today=START.replace(day=10))
        assert pos.cycle_day == 1
        assert pos.session_day == 1
