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

#: A preventive panel to raise with a GP — OBSERVATIONS, not medical advice. Each item's
#: ``key`` is the token an exam review's ``COVERED:`` line uses to tick it automatically.
GP_CHECKLIST = [
    ("Core bloods", [
        {"key": "fbc", "label": "Full blood count",
         "note": "Anaemia, platelet and white-cell abnormalities"},
        {"key": "uec_egfr", "label": "UEC + eGFR",
         "note": "Kidney function; eGFR ideally >90"},
        {"key": "lft", "label": "Liver function tests",
         "note": "ALT is often the first quiet signal of fatty liver"},
        {"key": "hba1c", "label": "HbA1c",
         "note": "<5.7%; 5.7–6.4% is prediabetes"},
        {"key": "glucose", "label": "Fasting glucose",
         "note": "<5.5 mmol/L; ideal under 5.0"},
        {"key": "insulin", "label": "Fasting insulin",
         "note": "<8 mIU/L; with glucose gives HOMA-IR (<1.5 ideal)"},
        {"key": "lipids", "label": "Lipid profile",
         "note": "Triglycerides <1.5; TG:HDL as an insulin-resistance proxy"},
        {"key": "iron", "label": "Iron studies + ferritin",
         "note": "Depletion — and high ferritin/transferrin flagging haemochromatosis"},
        {"key": "b12_folate", "label": "B12 + folate",
         "note": "Deficiency, especially on any acid suppression"},
        {"key": "tsh", "label": "TSH",
         "note": "Thyroid function; 0.5–2.5 mIU/L is comfortable"},
        {"key": "vitd", "label": "Vitamin D (25-OH)",
         "note": "75–125 nmol/L; rebate restricted, may be out of pocket"},
    ]),
    ("Cardiometabolic add-ons", [
        {"key": "apob", "label": "ApoB",
         "note": "<0.9 g/L general; 0.6–0.8 for aggressive prevention"},
        {"key": "lpa", "label": "Lp(a)",
         "note": ">125 nmol/L elevated — test once, ever"},
        {"key": "hscrp", "label": "hs-CRP",
         "note": "<1 mg/L low risk; test on a rested, well day"},
        {"key": "psa", "label": "PSA (baseline)",
         "note": "40–49: really only with family history (your lab's own note)"},
    ]),
    ("Not bloods", [
        {"key": "bp", "label": "Blood pressure",
         "note": "<120/80; ask for 24-hour ambulatory if borderline in clinic"},
        {"key": "waist", "label": "Waist circumference",
         "note": "<94 cm; better visceral-fat proxy than BMI — tracked on the Progress tab"},
        {"key": "skin", "label": "Full skin check",
         "note": "Annual in SA — new, changing or asymmetric lesions"},
        {"key": "eye", "label": "Eye exam + eye pressure",
         "note": "Baseline at 40; glaucoma is silent"},
        {"key": "sleep_apnoea", "label": "Sleep apnoea screen",
         "note": "Snoring, witnessed apnoeas, unrefreshing sleep"},
        {"key": "family_history", "label": "Family history (written)",
         "note": "Conditions and ages for parents and siblings — it drives the rest"},
    ]),
]

#: The tokens a review's COVERED line may use — the blood tests that can auto-tick.
COVERABLE_KEYS = {it["key"] for _sec, items in GP_CHECKLIST for it in items}


def parse_covered(review: str) -> set[str]:
    """The test tokens an exam review declares it has results for (its ``COVERED:`` line)."""
    for line in (review or "").splitlines():
        if line.strip().lower().startswith("covered:"):
            raw = line.split(":", 1)[1]
            return {t.strip().lower() for t in raw.split(",")
                    if t.strip().lower() in COVERABLE_KEYS}
    return set()


def strip_covered(review: str) -> str:
    """The review without its machine-readable COVERED line — the human-facing text."""
    return chr(10).join(ln for ln in (review or "").splitlines()
                        if not ln.strip().lower().startswith("covered:")).strip()


def checklist_status(covered: dict) -> list[dict]:
    """The GP checklist annotated with what has been done. ``covered`` maps a test key to
    the most recent date an exam covered it."""
    out = []
    for section, items in GP_CHECKLIST:
        rows = [{**it, "done": it["key"] in covered, "date": covered.get(it["key"])}
                for it in items]
        out.append({"section": section, "items": rows,
                    "done": sum(1 for r in rows if r["done"]), "total": len(rows)})
    return out

