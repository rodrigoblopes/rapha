"""Build a day's menu that lands exactly on the calorie and protein targets.

The model-costing in `menu.py` reads Cariani's fixed grams and reports whatever
they sum to — useful, but it does not *hit a target*, and its fuzzy TACO matching
made coarse choices (chicken → chicken heart). This module solves the other
direction: given a target, it scales real portions of a curated staple set until
the day lands on the numbers.

**Curated, not fuzzy.** The staples are pinned to exact TACO entries (verified
2026-07-22), so "chicken" is always chicken breast, never a mismatch. The two
foods TACO lacks — tilápia and cottage cheese — use standard published values,
flagged in the table.

**The solve is two linear equations.** Protein foods scale by `a`, carbohydrate
foods by `b`; fat rides along on the protein foods (eggs, meat) plus a fixed
olive-oil allowance:

    a·(protein from protein-foods) + b·(protein from carb-foods) = protein target
    a·(kcal from protein-foods)    + b·(kcal from carb-foods)     = kcal − fixed

Two equations, two unknowns, one exact solution — then portions round to the
nearest 5 g (weighable) and the *actual* totals are recomputed from the rounded
grams, so the number shown is the number on the plate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..units import Grams, Kcal


@dataclass(frozen=True, slots=True)
class Food:
    """Per 100 g. Macros in decigrams (×10) to stay integer, as TACO stores them."""

    name_en: str
    kcal: int
    protein_dg: int
    carb_dg: int
    fat_dg: int
    taco: str  # provenance


# Verified against TACO 2026-07-22 (see the search in the build notes). The two
# marked STD are not in TACO; standard published per-100g values are used.
CURATED: dict[str, Food] = {
    "arroz": Food("white rice, cooked", 128, 25, 281, 2, "TACO #3"),
    "frango": Food("chicken breast, grilled", 159, 320, 0, 25, "TACO #360"),
    "frango_desfiado": Food("chicken breast, cooked (shredded)", 163, 315, 0, 32, "TACO #358"),
    "patinho": Food("lean beef (patinho), grilled", 219, 359, 0, 73, "TACO #329"),
    "peixe": Food("white fish (merluza/pescada) fillet", 107, 167, 0, 40, "TACO #265"),
    "ovo": Food("whole egg, cooked", 146, 133, 6, 95, "TACO #425"),
    "clara": Food("egg white, cooked", 59, 134, 0, 1, "TACO #423"),
    "batata_doce": Food("sweet potato, cooked", 77, 6, 184, 1, "TACO #77"),
    "aveia": Food("oats, flakes", 394, 139, 666, 85, "TACO #7"),
    "feijao": Food("carioca beans, cooked", 76, 48, 136, 5, "TACO #464"),
    "banana": Food("banana", 92, 14, 238, 1, "TACO #159"),
    "azeite": Food("olive oil", 884, 0, 0, 1000, "TACO #—"),
}


@dataclass(frozen=True, slots=True)
class Item:
    food: str
    name_en: str
    grams: int
    kcal: int
    protein_dg: int
    carb_dg: int
    fat_dg: int


@dataclass(frozen=True, slots=True)
class Meal:
    number: int
    label: str
    items: list[Item] = field(default_factory=list)
    free: str = "Vegetables / salad — à vontade"

    @property
    def kcal(self) -> int:
        return sum(i.kcal for i in self.items)

    @property
    def protein_g(self) -> int:
        return sum(i.protein_dg for i in self.items) // 10


@dataclass(frozen=True, slots=True)
class TargetedDay:
    meals: list[Meal]
    total_kcal: Kcal
    total_protein: Grams
    total_carb: Grams
    total_fat: Grams


# The template: which foods, in which meal, and their role.
#   role "p" = protein-food (scaled by a), "c" = carb-food (scaled by b),
#   "fix" = fixed grams (olive oil).  base_g is the starting portion.
_TEMPLATE: list[tuple[int, str, list[tuple[str, str, int]]]] = [
    (1, "Breakfast (post-workout)", [
        ("ovo", "p", 100), ("clara", "p", 90), ("aveia", "c", 40), ("banana", "c", 100),
    ]),
    (2, "Lunch", [
        ("arroz", "c", 120), ("feijao", "c", 80), ("frango", "p", 150), ("azeite", "fix", 15),
    ]),
    (3, "Afternoon", [
        ("arroz", "c", 100), ("patinho", "p", 120),
    ]),
    (4, "Dinner", [
        ("batata_doce", "c", 180), ("peixe", "p", 150), ("azeite", "fix", 15),
    ]),
    (5, "Supper", [
        ("frango_desfiado", "p", 100),
    ]),
]


def _macros(food_key: str, grams: float) -> tuple[float, float, float, float]:
    f = CURATED[food_key]
    s = grams / 100
    return f.kcal * s, f.protein_dg * s, f.carb_dg * s, f.fat_dg * s


def _solve(target_kcal: int, protein_dg_target: int) -> tuple[float, float]:
    """Solve the two-equation system for the protein-scale a and carb-scale b."""
    pp = pc = kp = kc = 0.0   # base protein & kcal from protein-foods / carb-foods
    fixed_kcal = fixed_p = 0.0
    for _, _, items in _TEMPLATE:
        for key, role, g in items:
            kcal, prot, _carb, _fat = _macros(key, g)
            if role == "p":
                pp += prot
                kp += kcal
            elif role == "c":
                pc += prot
                kc += kcal
            else:
                fixed_kcal += kcal
                fixed_p += prot

    # a·pp + b·pc = protein_target ; a·kp + b·kc = kcal_target − fixed
    rhs_p = protein_dg_target - fixed_p
    rhs_k = target_kcal - fixed_kcal
    det = pp * kc - pc * kp
    if abs(det) < 1e-6:
        return 1.0, 1.0
    a = (rhs_p * kc - pc * rhs_k) / det
    b = (pp * rhs_k - rhs_p * kp) / det
    # Keep portions sane: never scale a food below a third or above triple.
    return max(0.33, min(3.0, a)), max(0.33, min(3.0, b))


def build_targeted_day(target_kcal: Kcal, protein: Grams) -> TargetedDay:
    a, b = _solve(target_kcal.value, protein.value * 10)

    meals: list[Meal] = []
    tk = tp = tc = tf = 0
    for number, label, items in _TEMPLATE:
        built: list[Item] = []
        for key, role, base in items:
            scale = a if role == "p" else (b if role == "c" else 1.0)
            grams = max(5, round(base * scale / 5) * 5)   # nearest 5 g, weighable
            kcal, prot, carb, fat = _macros(key, grams)
            item = Item(key, CURATED[key].name_en, grams,
                        round(kcal), round(prot), round(carb), round(fat))
            built.append(item)
            tk += item.kcal
            tp += item.protein_dg
            tc += item.carb_dg
            tf += item.fat_dg
        meals.append(Meal(number, label, built))

    return TargetedDay(
        meals=meals,
        total_kcal=Kcal(tk),
        total_protein=Grams(tp // 10),
        total_carb=Grams(tc // 10),
        total_fat=Grams(tf // 10),
    )
