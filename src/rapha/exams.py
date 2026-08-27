"""Medical-exam ingest + review storage — the lab-report analogue of photos.py.

An uploaded exam (a PDF lab report, or a photo of a paper result) is stored under
``%RAPHA_HOME%/data/exams/<date>/``, where ``review.md`` — the plain-language read the
Claude CLI writes — sits beside it. Holds no credential; it only ever touches files
under ``%RAPHA_HOME%``. The review is an OBSERVATION against the lab's own reference
ranges, never medical advice (see the prompt in vision.py).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

#: A lab report is a PDF; allow a phone photo of a paper result too.
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_BYTES = 30 * 1024 * 1024


class ExamError(ValueError):
    """An upload we will not store: wrong type, empty, or oversize."""


def _basename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _ext(filename: str) -> str:
    base = _basename(filename)
    return f".{base.rsplit('.', 1)[1].lower()}" if "." in base else ""


def _safe_stem(filename: str) -> str:
    base = _basename(filename)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._")
    return (stem or "exam")[:64]


def _dedupe(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, i = path.stem, path.suffix, 1
    while (candidate := path.with_name(f"{stem}-{i}{suffix}")).exists():
        i += 1
    return candidate


def exams_dir(cfg) -> Path:
    return cfg.home / "data" / "exams"


def ingest_exam(cfg, filename: str, data: bytes, *, on: date | None = None) -> Path:
    """Validate and store an exam file under its upload date. Returns the path."""
    ext = _ext(filename)
    if ext not in ALLOWED_EXT:
        raise ExamError(
            f"unsupported file type {ext or '(none)'}; allowed: "
            f"{', '.join(sorted(ALLOWED_EXT))}")
    if not data:
        raise ExamError("empty upload")
    if len(data) > MAX_BYTES:
        raise ExamError(f"file too large ({len(data)} bytes; cap {MAX_BYTES})")

    on = on or date.today()
    dest_dir = exams_dir(cfg) / on.isoformat()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _dedupe(dest_dir / f"{_safe_stem(filename)}{ext}")
    dest.write_bytes(data)
    return dest


def files_for(cfg, day: str) -> list[Path]:
    """The stored exam files for a day (the review.md is not one of them)."""
    d = exams_dir(cfg) / day
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in ALLOWED_EXT)


def read_review(day_dir: Path) -> str | None:
    """The written exam review (markdown), or None if not analysed yet."""
    path = day_dir / "review.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None
