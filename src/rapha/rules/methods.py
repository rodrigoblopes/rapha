"""Execution-method cues — how a set is *performed*, not just its reps and load.

Some movements in a Cariani sheet carry a technique that changes how the set is run:
an isometric hold, an eccentric emphasis, a peak-contraction squeeze. The reps/load
prescription alone doesn't convey it, and a set run as a plain set is a different
stimulus. This maps a keyword in the (Portuguese) exercise name to a plain-language cue.

Scope: these Intermediário fichas are mostly straight sets with progressive load and a
handful of isometric holds. They also carry the occasional Módulo 16 set-method — Sheet
03 D3 ends Puxador Alto with a **drop-set** — so the assumption that the advanced methods
(rest-pause, drop-set, bi-set) never reach this athlete's sheets was wrong. This table
maps a method NAMED in the exercise text to a cue; a drop-set carried structurally (a set
flagged ``dropset`` in the parsed data) is modelled in ``garmin/workout.py`` instead, as
its own lap-ended step. Nothing is invented where the data is silent.
"""

from __future__ import annotations

#: (keyword variants that may appear in the name) -> (label, plain-language cue).
_METHODS: list[tuple[tuple[str, ...], str, str]] = [
    (("isometr",), "Isometria",
     "Hold the contracted position for the stated count before releasing — the tension "
     "is the point, not the movement."),
    (("negativ", "excêntric", "excentric"), "Ênfase na negativa",
     "Lower under control for the stated count; the eccentric (lowering) phase is where "
     "the work is — resist gravity, don't drop."),
    (("pico", "contração", "contracao"), "Pico de contração",
     "Squeeze and pause a beat at peak contraction on every rep."),
    (("rest-pause", "rest pause", "restpause"), "Rest-pause",
     "Take the set to near-failure, rest 10–15 s, then squeeze out more reps at the same "
     "load — one extended set, not a fresh one."),
    (("drop", "drop-set", "dropset"), "Drop-set",
     "At failure, strip ~20% of the load and continue without rest; repeat once more."),
    (("bi-set", "biset", "bi set", "conjugad"), "Bi-set",
     "Two exercises back to back with no rest between them, then rest after the pair."),
    (("super-set", "superset", "super set"), "Super-set",
     "Antagonist pair back to back with no rest between the two movements."),
]


def method_cue(exercise_name: str) -> tuple[str, str] | None:
    """(label, cue) if the name names an execution method, else None. First match wins."""
    t = (exercise_name or "").lower()
    for variants, label, cue in _METHODS:
        if any(v in t for v in variants):
            return label, cue
    return None
