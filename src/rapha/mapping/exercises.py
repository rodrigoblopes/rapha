"""Cariani's Portuguese exercise names -> Garmin's fixed exercise taxonomy.

⚠️ **An unmapped exercise stops the push with a named error. It is never
substituted** (CLAUDE.md). Silently swapping "supino reto" for a similar-looking
Garmin category means doing the wrong lift for eight weeks and never finding out —
the failure is invisible precisely because the workout still looks complete.

Garmin's workout API keys a strength step by (category, exerciseName), both drawn
from a closed enum Garmin publishes. This table is the curated bridge. It matches
on the *normalised* name (accent-stripped, lowercased, method words dropped), so
"SUPINO RETO NO SMITH" and "Supino reto" reach the same entry.

The table is deliberately partial. It covers the movements that actually appear in
the male fichas; a gap is surfaced at push time, not filled with a guess.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GarminExercise:
    category: str
    name: str | None = None


class UnmappedExercise(KeyError):
    """A ficha exercise with no Garmin mapping. The push must stop here."""


# Words that describe *how*, not *what* — dropped before matching so equipment and
# tempo variants collapse to the base movement.
_NOISE = {
    "no", "na", "com", "de", "do", "da", "c", "e", "ou", "em", "reto",
    "smith", "livre", "maquina", "máquina", "halter", "halteres", "barra",
    "w", "corda", "cabo", "pulley", "banco", "chao", "chão", "unilateral",
    "alternado", "alternada", "sentado", "sentada", "pe", "pé",
    "inclinado", "declinado", "aberto", "aberta", "fechado", "fechada",
    "pegada", "pronada", "supinada", "neutra", "isometria", "isometrico",
}


def normalise(name: str) -> str:
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", name.lower())
        if unicodedata.category(c) != "Mn"
    )
    words = [w for w in re.findall(r"[a-z]+", stripped) if w not in _NOISE and len(w) > 1]
    return " ".join(words)


# Keyed by a normalised *substring* that uniquely identifies the movement.
# Matching takes the LONGEST matching key, not the first, so a generic entry can
# never shadow a specific one regardless of order — "cadeira adutora" beats the
# bare "cadeira". Ordering the list by hand is fragile; letting the longest key
# win is not.
_TABLE: list[tuple[str, GarminExercise]] = [
    # chest
    ("crucifixo", GarminExercise("FLYE", "DUMBBELL_FLYE")),
    ("cross over", GarminExercise("FLYE", "CABLE_CROSSOVER")),
    ("crossover", GarminExercise("FLYE", "CABLE_CROSSOVER")),
    ("supino", GarminExercise("BENCH_PRESS", "BARBELL_BENCH_PRESS")),
    ("paralelas", GarminExercise("PUSH_UP", "DIP")),
    ("flexao", GarminExercise("PUSH_UP", "PUSH_UP")),
    # back
    ("puxador", GarminExercise("PULL_UP", "LAT_PULLDOWN")),
    ("puxada", GarminExercise("PULL_UP", "LAT_PULLDOWN")),
    # a standing cable pull-over is a straight-arm cable pulldown (lat isolation)
    ("pulover", GarminExercise("PULL_UP", "STRAIGHT_ARM_PULLDOWN")),
    ("pull over", GarminExercise("PULL_UP", "STRAIGHT_ARM_PULLDOWN")),
    ("pullover", GarminExercise("PULL_UP", "STRAIGHT_ARM_PULLDOWN")),
    ("barra fixa", GarminExercise("PULL_UP", "PULL_UP")),
    ("remada", GarminExercise("ROW", "BENT_OVER_ROW")),
    # legs
    ("leg press", GarminExercise("SQUAT", "LEG_PRESS")),
    ("agachamento", GarminExercise("SQUAT", "SQUAT")),
    ("avanco", GarminExercise("LUNGE", "LUNGE")),
    ("terra", GarminExercise("DEADLIFT", "BARBELL_DEADLIFT")),
    ("stiff", GarminExercise("DEADLIFT", "STIFF_LEG_DEADLIFT")),
    ("flexor sentado", GarminExercise("LEG_CURL", "SEATED_LEG_CURL")),
    ("flexor", GarminExercise("LEG_CURL", "LYING_LEG_CURL")),
    ("extensor", GarminExercise("LEG_CURL", "LEG_EXTENSIONS")),
    ("cadeira", GarminExercise("LEG_CURL", "LEG_EXTENSIONS")),
    ("cadeira extensora", GarminExercise("LEG_CURL", "LEG_EXTENSIONS")),
    ("cadeira flexora", GarminExercise("LEG_CURL", "SEATED_LEG_CURL")),
    ("mesa flexora", GarminExercise("LEG_CURL", "LYING_LEG_CURL")),
    ("cadeira adutora", GarminExercise("HIP_RAISE", "HIP_ADDUCTION")),
    ("cadeira abdutora", GarminExercise("HIP_RAISE", "HIP_ABDUCTION")),
    ("elevacao pelvica", GarminExercise("HIP_RAISE", "BARBELL_HIP_THRUST")),
    ("panturrilha", GarminExercise("CALF_RAISE", "STANDING_CALF_RAISE")),
    ("passada", GarminExercise("LUNGE", "LUNGE")),
    ("afundo", GarminExercise("LUNGE", "LUNGE")),
    # shoulders
    ("desenvolvimento", GarminExercise("SHOULDER_PRESS", "BARBELL_SHOULDER_PRESS")),
    # Garmin has no FRONT_RAISE category — front raises live under LATERAL_RAISE.
    ("elevacao lateral", GarminExercise("LATERAL_RAISE", "DUMBBELL_LATERAL_RAISE")),
    ("elevacao frontal", GarminExercise("LATERAL_RAISE", "BARBELL_FRONT_RAISE")),
    ("encolhimento", GarminExercise("SHRUG", "BARBELL_SHRUG")),
    # arms
    ("rosca scott", GarminExercise("CURL", "PREACHER_CURL")),
    ("rosca inversa", GarminExercise("CURL", "REVERSE_CURL")),
    ("rosca", GarminExercise("CURL", "BICEPS_CURL")),
    ("triceps testa", GarminExercise("TRICEPS_EXTENSION", "LYING_TRICEPS_EXTENSION")),
    ("triceps frances", GarminExercise("TRICEPS_EXTENSION", "OVERHEAD_TRICEPS_EXTENSION")),
    ("triceps", GarminExercise("TRICEPS_EXTENSION", "TRICEPS_PUSHDOWN")),
    # core / lower back
    ("hiperextensao", GarminExercise("HYPEREXTENSION", "HYPEREXTENSION")),
    ("lombar", GarminExercise("HYPEREXTENSION", "HYPEREXTENSION")),
    # Compound key wins by length over the bare "abdominal" → CRUNCH, so a
    # "prancha abdominal" is a plank (a timed hold), not a crunch.
    ("prancha abdominal", GarminExercise("PLANK", "PLANK")),
    ("prancha", GarminExercise("PLANK", "PLANK")),
    ("abdominal", GarminExercise("CRUNCH", "CRUNCH")),
    ("crunch", GarminExercise("CRUNCH", "CRUNCH")),
    # warmup / cardio
    ("esteira", GarminExercise("CARDIO", "TREADMILL")),
    ("aquecimento", GarminExercise("WARM_UP", None)),
]


def map_exercise(name: str) -> GarminExercise:
    """Return the Garmin exercise for a ficha name, or raise UnmappedExercise.

    The longest matching key wins, so "cadeira adutora" is not shadowed by the
    bare "cadeira" fallback. A tie between equally long keys is a table bug, not a
    runtime one, and would be caught by the coverage test.
    """
    norm = normalise(name)
    best: tuple[int, GarminExercise] | None = None
    for key, exercise in _TABLE:
        if key in norm and (best is None or len(key) > best[0]):
            best = (len(key), exercise)
    if best is not None:
        return best[1]
    raise UnmappedExercise(
        f"no Garmin mapping for {name!r} (normalised {norm!r}). Add it to the table "
        "in mapping/exercises.py rather than pushing the wrong movement."
    )


def try_map(name: str) -> GarminExercise | None:
    """Non-raising variant, for reporting coverage before a push."""
    try:
        return map_exercise(name)
    except UnmappedExercise:
        return None
