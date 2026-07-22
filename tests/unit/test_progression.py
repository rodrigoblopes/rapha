"""Módulo 17 load progression, encoded from Cariani's transcript.

These pin the four decisions in his own framing: establish, progress, hold-because-
consolidating, hold-because-too-heavy.
"""

from rapha.rules.progression import (
    Decision,
    SetResult,
    advise,
    next_load_kg_x10,
)


class TestTheFourDecisions:
    def test_a_new_exercise_establishes_the_load_first(self):
        advice = advise(None)
        assert advice.decision is Decision.ESTABLISH
        assert "target reps" in advice.reasoning

    def test_target_hit_with_facility_means_progress(self):
        # Sailed past the target -> too light -> add the smallest step.
        advice = advise(SetResult(target_reps=12, completed_reps=14, form_held_to_target=True))
        assert advice.decision is Decision.PROGRESS

    def test_target_hit_but_hard_and_clean_means_hold(self):
        # Reached 12, last reps hard and clean -> consolidate, do not add weight.
        advice = advise(SetResult(target_reps=12, completed_reps=12, form_held_to_target=True))
        assert advice.decision is Decision.HOLD
        assert "catch up" in advice.reasoning or "hold" in advice.reasoning.lower()

    def test_falling_short_means_hold_because_too_heavy(self):
        # Form broke at 9 of 12 -> too heavy -> keep it and build in.
        advice = advise(SetResult(target_reps=12, completed_reps=9, form_held_to_target=False))
        assert advice.decision is Decision.HOLD
        assert "too heavy" in advice.reasoning

    def test_reaching_target_with_broken_form_still_progresses_load_down_the_right_path(self):
        # done == target but form did NOT hold -> it was easy enough to reach
        # sloppily, which M17 treats as ready to progress once cleaned up.
        advice = advise(SetResult(target_reps=12, completed_reps=12, form_held_to_target=False))
        assert advice.decision is Decision.PROGRESS


class TestIncrementsAreTheSmallestStep:
    def test_barbell_adds_the_smallest_plate_step(self):
        # M17: add the least weight that keeps the rep target, never a jump.
        assert next_load_kg_x10(400) == 425  # +2.5 kg

    def test_dumbbell_climbs_the_ladder_one_rung(self):
        assert next_load_kg_x10(10, using_dumbbells=True) == 20   # 1 -> 2 kg
        assert next_load_kg_x10(20, using_dumbbells=True) == 30   # 2 -> 3 kg

    def test_above_the_dumbbell_ladder_takes_the_smallest_further_step(self):
        assert next_load_kg_x10(30, using_dumbbells=True) == 40


class TestReasoningIsAlwaysShown:
    def test_every_decision_carries_its_reasoning(self):
        for result in (
            None,
            SetResult(12, 15, True),
            SetResult(12, 12, True),
            SetResult(12, 8, False),
        ):
            assert advise(result).reasoning
            assert "M17" in advise(result).reasoning
