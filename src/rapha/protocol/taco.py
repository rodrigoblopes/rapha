"""Parse the TACO food-composition table (Módulo 22) into per-100g records.

TACO — Tabela Brasileira de Composição de Alimentos, UNICAMP/NEPA — is a real
nutrition database, not course notes. It is what turns "100g de arroz" from a diet
model into kilocalories and macronutrients.

Two things make this a text parse rather than a table parse:

**pdfplumber finds no grid.** The PDF is whitespace-aligned, not ruled, so
`extract_tables` returns nothing on the data pages. The rows are parsed from text.

**The macro columns and the food NAME live on one set of pages; minerals and
vitamins repeat the food NUMBER on others.** Only the "Centesimal" pages carry the
name, so those are the ones parsed. The layout is:

    <number> <name…> <umidade%> <kcal> <kJ> <protein g> <lipids g> <chol> <carb g> …

The number and name are variable width; everything after is a run of numeric
tokens. That is parsed from the *right*: the trailing numbers are positional, the
name is whatever is left in the middle.

TACO's sentinels are not zero. ``Tr`` is a trace (below the quantification limit),
``NA`` is not analysed, ``*`` is not applicable. All three become None — recording
a not-analysed nutrient as 0 would silently under-count it in every menu total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

# A TACO numeric cell: `128`, `0,16`, `1.400`, `Tr`, `NA`, `*`, `-`.
_NUM = r"(?:\d[\d.]*,?\d*|Tr|NA|\*|-)"
_ROW = re.compile(rf"^\s*(\d+)\s+(.+?)\s+((?:{_NUM}\s+){{6,}}{_NUM})\s*$")

_MACRO_PAGE = re.compile(r"energia.*prote[íi]na", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class FoodItem:
    """Per 100 g of edible portion. Macros in whole units; None means unknown."""

    number: int
    name: str
    kcal: int | None
    protein_dg: int | None      # decigrams — protein ×10, to keep 1.4 g exact
    carb_dg: int | None
    fat_dg: int | None
    fibre_dg: int | None = None


def _num(token: str) -> float | None:
    """A TACO cell to a float, or None for a sentinel.

    Tr / NA / * / - are not zero: trace, not-analysed, not-applicable. Folding any
    of them to 0 would under-count that nutrient in every total it enters.
    """
    t = token.strip()
    if t in ("Tr", "NA", "*", "-", ""):
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _dg(value: float | None) -> int | None:
    """Grams to decigrams (×10), staying integer. 1.4 g -> 14."""
    return None if value is None else round(value * 10)


def parse_row(line: str) -> FoodItem | None:
    """One data line to a FoodItem, or None if it is not a data row.

    Columns after the name, in TACO order:
        0 umidade%  1 kcal  2 kJ  3 protein  4 lipids  5 cholesterol
        6 carbohydrate  7 fibre  8 ash  9 calcium …
    Parsed positionally from the start of the numeric run.
    """
    m = _ROW.match(line)
    if not m:
        return None

    number = int(m.group(1))
    name = re.sub(r"\s+", " ", m.group(2)).strip()
    cols = m.group(3).split()

    # Guard against a line that merely looks tabular. A real food name has letters,
    # and the numeric run must be long enough to reach carbohydrate (index 6).
    if len(cols) < 7 or not re.search(r"[A-Za-zÀ-ÿ]", name):
        return None

    kcal = _num(cols[1])
    return FoodItem(
        number=number,
        name=name,
        kcal=None if kcal is None else round(kcal),
        protein_dg=_dg(_num(cols[3])),
        fat_dg=_dg(_num(cols[4])),
        carb_dg=_dg(_num(cols[6])),
        fibre_dg=_dg(_num(cols[7])) if len(cols) > 7 else None,
    )


def parse_taco(path: Path) -> list[FoodItem]:
    """Parse every Centesimal page. Deduplicates by food number."""
    items: dict[int, FoodItem] = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _MACRO_PAGE.search(text):
                continue
            for line in text.splitlines():
                item = parse_row(line)
                if item and item.kcal is not None:
                    items.setdefault(item.number, item)
    return [items[n] for n in sorted(items)]
