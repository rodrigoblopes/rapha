"""The plain-language daily coach summary. Built from invented state only."""

from __future__ import annotations

from datetime import date

from rapha.dashboard.briefing import _coach


def _state(status="green", off_labels=(), rate=-0.5, target=2200, protein=160,
           rest=False, focus="Peito"):
    signals = [
        {"label": "HRV", "good": True, "higher_is_better": True},
        {"label": "Resting HR", "good": True, "higher_is_better": False},
    ]
    for lbl in off_labels:
        signals.append({"label": lbl, "good": False, "higher_is_better": True})
    return {
        "overview": {"day_of_60": 22, "recovery": {"status": status, "signals": signals}},
        "meals": {"target_kcal": target, "protein_g": protein},
        "training": {"rest": rest, "focus": focus, "exercises": [1, 2, 3]},
        "progress": {"weight_view": {"rate_kg_per_week": rate}},
    }


def _text(state):
    return " ".join(_coach(state, date(2026, 8, 13))["paragraphs"]).lower()


def test_green_reads_as_ready_to_train():
    assert "well recovered" in _text(_state(status="green"))


def test_amber_names_the_off_signal():
    txt = _text(_state(status="amber", off_labels=["Sleep"]))
    assert "sleep" in txt and "leave a rep" in txt


def test_red_advises_toward_rest():
    assert "rest" in _text(_state(status="red"))


def test_a_cut_is_described_as_controlled_loss():
    assert "trending down" in _text(_state(rate=-0.5))


def test_a_gain_is_flagged_when_cutting():
    assert "trending up" in _text(_state(rate=0.4))


def test_protein_is_always_called_out():
    assert "protein" in _text(_state(protein=158))


def test_a_rest_day_is_explained_not_left_blank():
    assert "rest day" in _text(_state(rest=True))


def test_it_survives_missing_sections():
    # No weight view, no meals — must not raise, must still say something.
    out = _coach({"overview": {"day_of_60": 1,
                               "recovery": {"status": "green", "signals": []}}},
                 date(2026, 8, 13))
    assert out["paragraphs"]
