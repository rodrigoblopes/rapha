"""Per-photo-set analysis loading. Invented review text only."""

from __future__ import annotations

from rapha.dashboard.briefing import _read_photo_analysis


def test_absent_file_is_none(tmp_path):
    assert _read_photo_analysis(tmp_path) is None


def test_empty_file_is_none(tmp_path):
    (tmp_path / "analysis.md").write_text("   \n", encoding="utf-8")
    assert _read_photo_analysis(tmp_path) is None


def test_first_block_is_the_headline_rest_are_paragraphs(tmp_path):
    (tmp_path / "analysis.md").write_text(
        "Leaner this month.\n\nThe waist is tighter.\n\nProtein held the muscle.",
        encoding="utf-8",
    )
    out = _read_photo_analysis(tmp_path)
    assert out["headline"] == "Leaner this month."
    assert out["paragraphs"] == ["The waist is tighter.", "Protein held the muscle."]


def test_a_single_line_review_has_a_headline_and_no_paragraphs(tmp_path):
    (tmp_path / "analysis.md").write_text("Solid baseline.", encoding="utf-8")
    out = _read_photo_analysis(tmp_path)
    assert out["headline"] == "Solid baseline."
    assert out["paragraphs"] == []
