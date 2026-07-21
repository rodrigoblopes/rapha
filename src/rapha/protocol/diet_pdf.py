"""Parse the calorie-calculated diet models (Módulo 21).

Each model is one PDF at a stated calorie level, laid out as numbered meals:

    REFEIÇÃO 2
    100g de arroz,
    100g de frango grelhado,
    Folhas a vontade + 50g de legumes no vapor .

then blocks of substitutions ("Opções para substituição para almoço"), then a
list of vegetables that are unrestricted.

Two things this parser is careful about:

**"À vontade" is not a quantity.** Free vegetables carry no gram figure, and
inventing one would put a fabricated number into a macro total. They are recorded
as unlimited and excluded from the arithmetic.

**"OU" means alternative, not addition.** `120g de macarrão OU 135g de frango`
is one meal with two ways to make it. Summing them would roughly double the
model's calories — the single most damaging mistake available here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from ..units import Grams

_MEAL = re.compile(r"REFEI[ÇC][ÃA]O\s+(\d+)", re.IGNORECASE)
_PORTION = re.compile(r"(\d+)\s*g\s+de\s+([^,.+]+)", re.IGNORECASE)
_UNITS = re.compile(r"(\d+)\s+(unidades?|ovos?|claras?|colher[^,.]*)", re.IGNORECASE)
#: The sheets write this three ways — `à vontade`, `á vontade`, `a vontade`.
#: The acute accent is a typo in the source, but it is in the source, and a
#: regex that misses it silently drops the food from the meal.
_AD_LIB = re.compile(r"[àáa]\s*vontade", re.IGNORECASE)
#: `2500 kcal`, and ranges like `2000-2500kcal`. For a range the LOWER bound is
#: taken: these models are selected to sit under a computed target, and choosing
#: the top of a range would overshoot it by up to 500 kcal every time.
_KCAL_RANGE = re.compile(r"(\d{3,5})\s*-\s*(\d{3,5})\s*\+?\s*kcal", re.IGNORECASE)
_KCAL_IN_NAME = re.compile(r"(\d{3,5})\s*\+?\s*kcal", re.IGNORECASE)

#: A meal with fewer than this many foods is a parse to distrust, not a light meal.
MIN_PORTIONS_PER_MEAL = 2

_SUBSTITUTION_HEADING = re.compile(
    r"Op[çc][õo]es?\s+(?:para\s+substitui[çc][ãa]o\s+para\s+|de\s+)?(.+)", re.IGNORECASE
)
_VEG_HEADING = re.compile(r"Op[çc][õo]es\s+de\s+vegetais", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Portion:
    """One food and how much of it. ``unlimited`` foods carry no mass."""

    food: str
    amount: Grams | None = None
    unit_count: int | None = None
    unit: str | None = None
    unlimited: bool = False


@dataclass(frozen=True, slots=True)
class Alternative:
    """One way to satisfy a meal or a substitution slot."""

    portions: list[Portion]


@dataclass(frozen=True, slots=True)
class Meal:
    number: int
    alternatives: list[Alternative]

    @property
    def primary(self) -> Alternative | None:
        return self.alternatives[0] if self.alternatives else None


@dataclass(frozen=True, slots=True)
class DietModel:
    name: str
    kcal: int | None
    meals: list[Meal]
    substitutions: dict[str, list[Alternative]] = field(default_factory=dict)
    free_foods: list[str] = field(default_factory=list)
    source_file: str = ""
    warnings: list[str] = field(default_factory=list)


def parse_portions(line: str) -> list[Portion]:
    """Every food in one line. `à vontade` items are unlimited, not zero."""
    portions: list[Portion] = []

    for grams, food in _PORTION.findall(line):
        portions.append(Portion(food=_clean(food), amount=Grams(int(grams))))

    for count, unit in _UNITS.findall(line):
        portions.append(
            Portion(food=_clean(unit), unit_count=int(count), unit=_clean(unit))
        )

    if _AD_LIB.search(line):
        # "Folhas a vontade", "Vegetais á vontade" — the food is whatever precedes it.
        name = _AD_LIB.split(line)[0]
        name = re.sub(r".*?([A-Za-zÀ-ÿ\s]+)$", r"\1", name).strip(" +.,")
        portions.append(Portion(food=_clean(name) or "vegetais", unlimited=True))

    return portions


def split_alternatives(text: str) -> list[Alternative]:
    """Split on `OU`. Alternatives are choices, never additions.

    Summing them instead of choosing between them would roughly double the
    model's calories, which is the worst arithmetic error available in this file.
    """
    chunks = re.split(r"\bOU\b", text, flags=re.IGNORECASE)
    out = [Alternative(portions=parse_portions(c)) for c in chunks]
    return [a for a in out if a.portions]


def parse_diet(path: Path) -> DietModel:
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    lines = [ln.strip() for ln in text.splitlines()]

    meals: list[Meal] = []
    substitutions: dict[str, list[Alternative]] = {}
    free_foods: list[str] = []
    warnings: list[str] = []

    current_meal: int | None = None
    buffer: list[str] = []
    current_sub: str | None = None
    in_vegetables = False

    def flush() -> None:
        nonlocal current_meal, buffer, current_sub
        body = " ".join(buffer).strip()
        buffer = []
        if not body:
            current_meal, current_sub = None, None
            return
        alts = split_alternatives(body)
        if current_meal is not None:
            meals.append(Meal(number=current_meal, alternatives=alts))
        elif current_sub is not None:
            substitutions.setdefault(current_sub, []).extend(alts)
        current_meal, current_sub = None, None

    for line in lines:
        if not line:
            continue

        if m := _MEAL.search(line):
            flush()
            in_vegetables = False
            current_meal = int(m.group(1))
            continue

        if _VEG_HEADING.search(line):
            flush()
            in_vegetables = True
            continue

        if line.lower().startswith("op") and (m := _SUBSTITUTION_HEADING.match(line)):
            flush()
            in_vegetables = False
            current_sub = _clean(m.group(1)).rstrip(":").strip()
            continue

        if line.upper().startswith("CONSIDERA"):
            flush()
            in_vegetables = False
            continue

        if in_vegetables:
            # A grid of vegetable names, several per line.
            free_foods.extend(
                _clean(w) for w in re.split(r"\s{2,}|\t", line) if len(_clean(w)) > 2
            )
            continue

        if current_meal is not None or current_sub is not None:
            buffer.append(line)

    flush()

    stem = path.stem.replace("+", " ")
    kcal_range = _KCAL_RANGE.search(stem)
    kcal_single = _KCAL_IN_NAME.search(stem)
    if kcal_range:
        kcal = int(kcal_range.group(1))  # lower bound — see _KCAL_RANGE
    elif kcal_single:
        kcal = int(kcal_single.group(1))
    else:
        kcal = None

    if kcal is None:
        warnings.append(
            "no calorie level in the filename — model cannot be matched to a target"
        )
    if not meals:
        warnings.append("no meals could be read from this model")

    total_portions = sum(len(a.portions) for m in meals for a in m.alternatives)
    if meals and total_portions < MIN_PORTIONS_PER_MEAL * len(meals):
        # The failure that looks like success: meals were found, so the parse
        # reports structure, but almost no food was read out of them. A menu built
        # on this would silently under-feed.
        warnings.append(
            f"{len(meals)} meals but only {total_portions} foods read — this model "
            "probably uses a layout the parser does not handle; do not build a menu "
            "from it without checking the PDF"
        )

    return DietModel(
        name=_clean(path.stem.replace("+", " ").replace("_", " ")),
        kcal=kcal,
        meals=meals,
        substitutions=substitutions,
        free_foods=sorted(set(free_foods)),
        source_file=path.name,
        warnings=warnings,
    )


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip(" .,+-")
