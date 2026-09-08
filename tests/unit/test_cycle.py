"""Resolving today to a training day through the sheet's rotation."""

from datetime import date

from rapha.rules.cycle import resolve

# A 4-distinct-day sheet that repeats: 5->1, 6->2, 7 rest, 8->3, 9->4, 10 restarts.
# Real training sessions carry exercises; an *empty* one is a rest placeholder (below).
_EX = [{"name": "x", "sets": [{"reps": 10}]}]
PROGRAMME = {
    "sessions": [
        {"day": 1, "focus": "PERNAS", "exercises": _EX},
        {"day": 2, "focus": "PEITO", "exercises": _EX},
        {"day": 3, "focus": "COSTAS", "exercises": _EX},
        {"day": 4, "focus": "OMBRO", "exercises": _EX},
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

    def test_an_empty_placeholder_session_reads_as_rest(self):
        # Cariani's sheets carry a "TREINADOR" day with no exercises — 4 train, then
        # this rest, then restart. A 5-session sheet where day 5 is empty:
        sheet = {"sessions": [
            {"day": 1, "focus": "A", "exercises": _EX},
            {"day": 2, "focus": "B", "exercises": _EX},
            {"day": 3, "focus": "C", "exercises": _EX},
            {"day": 4, "focus": "D", "exercises": _EX},
            {"day": 5, "focus": "TREINADOR", "exercises": []},
        ], "rotation": []}
        assert resolve(sheet, start=START, today=START.replace(day=5)).is_rest
        # …and day 6 restarts the 5-day cycle on session 1.
        assert resolve(sheet, start=START, today=START.replace(day=6)).session_day == 1


def test_training_sequence_drops_rest_and_placeholder_days():
    from rapha.rules.cycle import training_sequence
    sheet = {
        "sessions": [
            {"day": 1, "focus": "Legs", "exercises": [{"name": "squat"}]},
            {"day": 2, "focus": "Chest", "exercises": [{"name": "bench"}]},
            {"day": 3, "focus": "Back", "exercises": [{"name": "row"}]},
            {"day": 4, "focus": "Shoulders", "exercises": [{"name": "press"}]},
            {"day": 5, "focus": "Rest", "exercises": []},
        ],
        "rotation": [{"day": 5, "restarts_cycle": True}],
    }
    assert training_sequence(sheet) == [1, 2, 3, 4]
