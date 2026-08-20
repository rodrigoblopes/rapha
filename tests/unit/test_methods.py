"""Execution-method cue detection from Portuguese exercise names."""

from rapha.rules.methods import method_cue


def test_isometria_is_detected():
    label, cue = method_cue("ROSCA ALTERNADA sentado C/ ISOMETRIA (10 rep)")
    assert label == "Isometria"
    assert "hold" in cue.lower()


def test_a_plain_movement_has_no_cue():
    assert method_cue("SUPINO RETO") is None


def test_negative_emphasis_is_detected():
    assert method_cue("Agachamento com ênfase na negativa")[0] == "Ênfase na negativa"


def test_empty_name_is_safe():
    assert method_cue("") is None
