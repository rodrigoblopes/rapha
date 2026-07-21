"""Extract the course into `%RAPHA_HOME%/protocol/`.

⚠️ The output of this module never enters the repo (ADR-002). It is derived from
purchased material, and derived-from-copyrighted is still copyrighted. A fresh
clone does nothing useful until this has run — the repo is the machine, not the
material.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..units import Grams, Kcal, Millimetres, Seconds
from .diet_pdf import parse_diet
from .ficha_pdf import parse_ficha

#: Directory name fragments -> what lives in them.
FICHA_MODULES = ("02", "03", "04", "05", "06", "07")
DIET_MODULE = "21"


def _encode(obj: Any) -> Any:
    if isinstance(obj, Grams | Kcal | Millimetres | Seconds):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _encode(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    return obj


def _module_dirs(course: Path, wanted: tuple[str, ...] | str) -> list[Path]:
    wanted_t = (wanted,) if isinstance(wanted, str) else wanted
    return [
        d
        for d in sorted(course.iterdir())
        if d.is_dir() and any(f" {n} " in d.name or f" {n}-" in d.name or f"{n} -" in d.name for n in wanted_t)
    ]


def extract(course: Path, out: Path, *, male_only: bool = True) -> dict[str, Any]:
    """Parse fichas and diet models into JSON. Returns a summary."""
    out.mkdir(parents=True, exist_ok=True)

    programmes = []
    for module in _module_dirs(course, FICHA_MODULES):
        for pdf in sorted(module.glob("*.pdf")):
            if male_only and "feminino" in pdf.name.lower():
                continue
            prog = parse_ficha(pdf)
            programmes.append({"module": module.name, **_encode(prog)})

    diets = []
    for module in _module_dirs(course, DIET_MODULE):
        for pdf in sorted(module.glob("*.pdf")):
            diets.append({"module": module.name, **_encode(parse_diet(pdf))})

    (out / "programmes.json").write_text(
        json.dumps(programmes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "diets.json").write_text(
        json.dumps(diets, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "programmes": len(programmes),
        "sessions": sum(len(p["sessions"]) for p in programmes),
        "exercises": sum(
            len(s["exercises"]) for p in programmes for s in p["sessions"]
        ),
        "programmes_with_warnings": sum(1 for p in programmes if p["warnings"]),
        "diets": len(diets),
        "diets_with_warnings": sum(1 for d in diets if d["warnings"]),
        "out": str(out),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def load(out: Path) -> tuple[list[dict], list[dict]]:
    """Read back what extract wrote. Empty lists if it has not run."""
    def _read(name: str) -> list[dict]:
        path = out / name
        if not path.is_file():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    return _read("programmes.json"), _read("diets.json")
