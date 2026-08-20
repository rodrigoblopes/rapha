"""Módulo 17 load progression, encoded from Cariani's transcript.

These pin the four decisions in his own framing: establish, progress, hold-because-
consolidating, hold-because-too-heavy.
"""

from rapha.rules.progression import (
    Decision,
    NextSessionCall,
    SetResult,
    advise,
    call_from_history,
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


class TestCallFromHistory:
    """Double progression read straight from Garmin's per-set history — the real
    numbers the watch detected last session, not a hand-reported set."""

    def test_no_history_establishes(self):
        call = call_from_history(target_reps=12, last_sets=[])
        assert call.decision is Decision.ESTABLISH
        assert call.suggested_kg_x10 is None

    def test_hitting_the_target_at_the_working_weight_progresses(self):
        # Top working set was 80.0 kg for 12 reps against a 12-rep target -> add a plate.
        call = call_from_history(
            target_reps=12,
            last_sets=[(12, 40000), (12, 80000), (12, 80000)],
        )
        assert call.decision is Decision.PROGRESS
        assert call.last_weight_kg_x10 == 800
        assert call.suggested_kg_x10 == 825          # +2.5 kg, smallest plate

    def test_exceeding_the_target_progresses(self):
        call = call_from_history(target_reps=10, last_sets=[(14, 60000)])
        assert call.decision is Decision.PROGRESS
        assert call.suggested_kg_x10 == 625

    def test_falling_short_holds_the_same_load(self):
        # 9 reps at 80 kg against a 12-rep target: too heavy, hold and build in.
        call = call_from_history(target_reps=12, last_sets=[(9, 80000), (8, 80000)])
        assert call.decision is Decision.HOLD
        assert call.suggested_kg_x10 == 800          # keep last week's load

    def test_bodyweight_progresses_by_reps_not_load(self):
        call = call_from_history(target_reps=15, last_sets=[(15, None), (15, None)])
        assert call.decision is Decision.PROGRESS
        assert call.bodyweight is True
        assert call.suggested_kg_x10 is None

    def test_dumbbell_uses_a_smaller_step(self):
        call = call_from_history(
            target_reps=12, last_sets=[(12, 12000)], using_dumbbells=True)
        assert call.decision is Decision.PROGRESS
        assert call.suggested_kg_x10 == 130          # 12 -> 13 kg dumbbell rung

    def test_every_call_explains_itself(self):
        for call in (
            call_from_history(target_reps=12, last_sets=[]),
            call_from_history(target_reps=12, last_sets=[(12, 80000)]),
            call_from_history(target_reps=12, last_sets=[(8, 80000)]),
        ):
            assert isinstance(call, NextSessionCall)
            assert len(call.reasoning) > 20
