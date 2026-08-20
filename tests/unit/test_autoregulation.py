"""Auto-regulation: recovery status -> a concrete session adjustment."""

from rapha.rules.autoregulation import adjust_for_recovery


def test_green_pushes_and_allows_progression():
    a = adjust_for_recovery("green", [])
    assert a.load_directive == "push"
    assert a.gate_progression is False


def test_amber_maintains_and_gates_progression():
    a = adjust_for_recovery("amber", ["HRV"])
    assert a.load_directive == "maintain"
    assert a.gate_progression is True
    assert "HRV" in a.detail


def test_red_reduces_and_gates_progression():
    a = adjust_for_recovery("red", ["HRV", "Sleep"])
    assert a.load_directive == "reduce"
    assert a.gate_progression is True
    assert "HRV and Sleep" in a.detail


def test_unknown_status_does_not_gate():
    a = adjust_for_recovery("unknown", [])
    assert a.gate_progression is False
    assert a.load_directive == "maintain"
