"""Post-session review: logged sets read against the plan. Invented numbers."""

from rapha.rules.session_review import review_session


def _plan(name, garmin, target, expected):
    return {"name": name, "garmin": garmin, "target_reps": target, "expected_kg_x10": expected}


def test_untrained_movements_produce_no_outcome():
    r = review_session([_plan("Bench", "BARBELL_BENCH_PRESS", 12, 600)], {})
    assert r.outcomes == [] and r.tonnage_kg == 0.0


def test_adding_load_reads_as_progressed():
    # planned 60.0 kg, lifted 62.5 kg for the target -> progressed, noted "up from"
    r = review_session(
        [_plan("Leg press", "LEG_PRESS", 12, 600)],
        {"LEG_PRESS": [(12, 62500), (12, 62500)]})
    assert r.outcomes[0].verdict == "progressed"
    assert any("up from 60" in s for s in r.strong)
    assert r.tonnage_kg == 1500.0


def test_missing_the_rep_target_reads_as_short_and_lands_in_work_on():
    r = review_session(
        [_plan("Bench", "BARBELL_BENCH_PRESS", 12, 600)],
        {"BARBELL_BENCH_PRESS": [(8, 60000), (7, 60000)]})
    assert r.outcomes[0].verdict == "short"
    assert r.work_on and "target" in r.work_on[0]


def test_same_load_at_target_reads_as_held():
    r = review_session(
        [_plan("Row", "SEATED_CABLE_ROW", 10, 600)],
        {"SEATED_CABLE_ROW": [(10, 60000)]})
    assert r.outcomes[0].verdict == "held"
    assert any("held" in s for s in r.strong)


def test_advice_flags_pushing_on_a_down_recovery_day():
    r = review_session(
        [_plan("Leg press", "LEG_PRESS", 12, 600)],
        {"LEG_PRESS": [(12, 62500)]}, recovery_status="red")
    assert any("recovery signals were down" in a for a in r.advice)
