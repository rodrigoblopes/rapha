"""Auto-regulation — let this morning's recovery change today's session, not just a dot.

A readiness traffic light that changes no instruction is decoration. This turns it into a
concrete adjustment in the language a lifter acts on: how many reps to leave in reserve,
whether to chase the top of the range or hold, and — crucially — whether today is a day
to add load at all. On a down day, progressing the weight fights the recovery signal; the
call to add a plate waits for a fresh morning.

Pure and framework-honest: it reports an observation ("your signals are down, so…"), never
an order, and it names *which* signals drove it so the reasoning is visible. It gates
progression by suppressing the *add-load* step only — the working weight is never reduced
below what was already earned; a red day simply holds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionAdjustment:
    readiness: str          # green | amber | red
    load_directive: str     # push | maintain | reduce
    reps_in_reserve: str    # plain-language RIR guidance
    gate_progression: bool  # True -> hold load today, don't add the plate
    headline: str
    detail: str


def adjust_for_recovery(status: str, off_signals: list[str] | None = None) -> SessionAdjustment:
    """Recovery status (+ which signals are down) -> a concrete session adjustment."""
    off = [s for s in (off_signals or [])]
    joined = " and ".join(off) if off else "the down signals"
    # Sentence-lead capital without lowercasing acronyms ("HRV" must not become "Hrv").
    named = joined[:1].upper() + joined[1:]

    if status == "green":
        return SessionAdjustment(
            "green", "push", "0–1 reps in reserve", False,
            "Recovered — chase the top of the rep range.",
            "Signals are at or above your baseline: train as planned and push the working "
            "sets to the top of the range. This is the day to earn a load increase.",
        )
    if status == "amber":
        return SessionAdjustment(
            "amber", "maintain", "1–2 reps in reserve", True,
            "Mostly recovered — train, but hold today's loads.",
            f"{named} slightly off baseline: keep the session, but leave a "
            "rep or two in reserve and hold today's weights rather than adding load — the "
            "plate waits for a fresher morning.",
        )
    if status == "red":
        return SessionAdjustment(
            "red", "reduce", "3+ reps in reserve", True,
            "Signals down — lighten the session or take the rest day.",
            f"{named} well below baseline: a lighter session (fewer sets, more "
            "in reserve) or an honest rest day will build more than pushing through. Hold "
            "loads; do not add weight today.",
        )
    return SessionAdjustment(
        "unknown", "maintain", "train by feel", False,
        "Not enough recovery data to adjust.",
        "No recent overnight signals to read — train to the sheet and judge loads by feel.",
    )
