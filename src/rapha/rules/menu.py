"""Build a day's menu from a Cariani diet model, costed against TACO.

This does not invent a diet. Cariani's 26 models are the framework; Rapha selects
the one nearest the computed calorie target (ADR-005) and prices its portions
against the TACO food table so the macros are real numbers rather than the model's
round headline figure.

**A food that cannot be matched in TACO is surfaced, not dropped.** A silently
skipped ingredient makes the day's protein look lower than it is, which — in a
recomposition — is the error that costs muscle. Unmatched foods are listed with
the totals so the gap is visible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..units import Grams, Kcal


@dataclass(frozen=True, slots=True)
class CostedPortion:
    food: str
    grams: int | None
    kcal: int | None
    protein_dg: int | None
    carb_dg: int | None
    fat_dg: int | None
    matched_to: str | None = None
    unlimited: bool = False


@dataclass(frozen=True, slots=True)
class MenuTotals:
    kcal: Kcal
    protein: Grams
    carb: Grams
    fat: Grams
    unmatched: list[str] = field(default_factory=list)


# ── food-name matching ───────────────────────────────────────────────────────

_STOP = {
    "de", "da", "do", "com", "e", "ou", "sem", "a", "o", "no", "na", "em",
    "grelhado", "grelhada", "cozido", "cozida", "cru", "crua", "assado", "assada",
    "moido", "moida", "light", "integral",
}


def _normalise(text: str) -> list[str]:
    """Lowercased, accent-stripped content words. `Frango grelhado` -> {frango}."""
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    words = re.findall(r"[a-z]+", stripped)
    return [w for w in words if w not in _STOP and len(w) > 2]


def build_food_index(foods: list[dict]) -> dict[str, list[dict]]:
    """Index TACO foods by content word, for overlap matching."""
    index: dict[str, list[dict]] = {}
    for food in foods:
        for word in _normalise(food["name"]):
            index.setdefault(word, []).append(food)
    return index


def match_food(name: str, foods: list[dict], index: dict[str, list[dict]]) -> dict | None:
    """Best TACO match for a diet-model food name, or None.

    Scored by shared content words, tie-broken toward the shorter TACO name — a
    plain "Arroz, cozido" beats "Arroz doce" for the ingredient "arroz". A match
    needs at least one shared word; a zero-overlap guess would be worse than
    admitting the food is unmatched.
    """
    wanted = _normalise(name)
    if not wanted:
        return None

    wanted_set = set(wanted)
    scored: dict[int, int] = {}
    for word in wanted:
        for food in index.get(word, ()):
            scored[food["number"]] = scored.get(food["number"], 0) + 1

    if not scored:
        return None

    by_number = {f["number"]: f for f in foods}

    def rank(number: int) -> tuple[int, int]:
        overlap = scored[number]
        # Penalise TACO words the ingredient did NOT ask for. For "arroz",
        # "Arroz, doce" carries the extra "doce" and loses to "Arroz, cozido",
        # whose remaining words are all cooking-method stopwords. Fewer unasked-for
        # words is a closer match than merely a shorter string.
        food_words = set(_normalise(by_number[number]["name"]))
        extra = len(food_words - wanted_set)
        return (overlap, -extra)

    return by_number[max(scored, key=rank)]


# ── costing ──────────────────────────────────────────────────────────────────

def _scale(per_100g: int | None, grams: int) -> int | None:
    return None if per_100g is None else per_100g * grams // 100


def _grams(amount: object) -> int | None:
    """Grams from a portion's amount.

    The diet parser stores a Grams, which serialises to {"value": N} in the
    extracted JSON but is a bare int in unit tests. Accept both rather than make
    the caller care which side of extraction it is on.
    """
    if amount is None:
        return None
    if isinstance(amount, dict):
        return amount.get("value")
    return int(amount)


def cost_portion(portion: dict, foods: list[dict], index: dict[str, list[dict]]) -> CostedPortion:
    """Price one diet-model portion against TACO for its stated grams."""
    name = portion["food"]

    if portion.get("unlimited"):
        # `à vontade` free vegetables carry no mass and no calories worth counting.
        return CostedPortion(
            food=name, grams=None, kcal=0, protein_dg=0, carb_dg=0, fat_dg=0,
            unlimited=True,
        )

    grams = _grams(portion.get("amount"))
    if grams is None:
        return CostedPortion(name, None, None, None, None, None)

    match = match_food(name, foods, index)
    if match is None:
        return CostedPortion(name, grams, None, None, None, None, matched_to=None)

    return CostedPortion(
        food=name,
        grams=grams,
        kcal=_scale(match["kcal"], grams),
        protein_dg=_scale(match["protein_dg"], grams),
        carb_dg=_scale(match["carb_dg"], grams),
        fat_dg=_scale(match["fat_dg"], grams),
        matched_to=match["name"],
    )


def total_day(portions: list[CostedPortion]) -> MenuTotals:
    """Sum a day. Unmatched foods are reported, never silently treated as zero."""
    kcal = sum(p.kcal for p in portions if p.kcal is not None)
    protein = sum(p.protein_dg for p in portions if p.protein_dg is not None)
    carb = sum(p.carb_dg for p in portions if p.carb_dg is not None)
    fat = sum(p.fat_dg for p in portions if p.fat_dg is not None)
    unmatched = [
        p.food
        for p in portions
        if not p.unlimited and p.grams is not None and p.matched_to is None
    ]
    return MenuTotals(
        kcal=Kcal(kcal),
        protein=Grams(protein // 10),
        carb=Grams(carb // 10),
        fat=Grams(fat // 10),
        unmatched=unmatched,
    )


def choose_model(diets: list[dict], target: Kcal) -> dict | None:
    """The usable model whose calorie level is nearest the target.

    Only models with a calorie level and no parse warnings are eligible: a
    half-parsed model would build a menu that silently under-feeds.
    """
    usable = [d for d in diets if d.get("kcal") and not d.get("warnings")]
    if not usable:
        return None
    return min(usable, key=lambda d: abs(d["kcal"] - target.value))


def primary_portions(model: dict) -> list[dict]:
    """The first alternative of each meal — the default way to eat the model.

    Alternatives are choices, not additions (diet_pdf), so a menu takes one per
    meal. The substitutions travel with the model for when a food is unwanted.
    """
    portions: list[dict] = []
    for meal in model.get("meals", []):
        alts = meal.get("alternatives") or []
        if alts:
            portions.extend(alts[0].get("portions", []))
    return portions
