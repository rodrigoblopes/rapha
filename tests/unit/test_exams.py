"""Medical-exam store: validation, storage, review read. No network."""

from types import SimpleNamespace

import pytest

from rapha import exams


def _cfg(tmp_path):
    return SimpleNamespace(home=tmp_path)


def test_a_pdf_is_stored_under_its_date(tmp_path):
    from datetime import date
    dest = exams.ingest_exam(_cfg(tmp_path), "bloods.pdf", b"%PDF-1.4 fake",
                             on=date(2025, 5, 10))
    assert dest.parent.name == "2025-05-10"
    assert dest.suffix == ".pdf" and dest.read_bytes() == b"%PDF-1.4 fake"


def test_an_unsupported_type_is_refused(tmp_path):
    with pytest.raises(exams.ExamError):
        exams.ingest_exam(_cfg(tmp_path), "notes.txt", b"hello")


def test_empty_and_oversize_are_refused(tmp_path):
    with pytest.raises(exams.ExamError):
        exams.ingest_exam(_cfg(tmp_path), "x.pdf", b"")
    with pytest.raises(exams.ExamError):
        exams.ingest_exam(_cfg(tmp_path), "x.pdf", b"x" * (exams.MAX_BYTES + 1))


def test_files_and_review_round_trip(tmp_path):
    from datetime import date
    cfg = _cfg(tmp_path)
    exams.ingest_exam(cfg, "bloods.pdf", b"%PDF", on=date(2025, 5, 10))
    day_dir = exams.exams_dir(cfg) / "2025-05-10"
    assert [p.name for p in exams.files_for(cfg, "2025-05-10")] == ["bloods.pdf"]
    assert exams.read_review(day_dir) is None
    (day_dir / "review.md").write_text("Headline.\n\n## Section\nbody", encoding="utf-8")
    assert exams.read_review(day_dir).startswith("Headline.")
