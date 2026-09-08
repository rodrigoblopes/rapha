"""Where in the 60 days are we, and which training day is live.

The protocol is 60 days. A sheet prescribes a handful of distinct training days and
then *rotates* them (parsed from the sheet's cycle page — see `protocol/ficha_pdf`).
This resolves "today" to the concrete session to train, following that rotation and
honouring rest days.

Pure: the start date and today are arguments, never clock reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CyclePosition:
    day_of_protocol: int        # 1..60
    cycle_day: int              # which training-day number is live today
    is_rest: bool
    session_day: int | None     # the day whose exercises to train (after rotation)
    note: str


def _rotation_map(rotation: list[dict]) -> dict[int, dict]:
    return {e["day"]: e for e in rotation}


def resolve(
    programme: dict, *, start: date, today: date, cycle_length: int | None = None
) -> CyclePosition:
    """Resolve today to a concrete session using the sheet's rotation.

    ``cycle_length`` defaults to the largest day the sheet actually prescribes or
    references, so a 4-distinct-day sheet that restarts at day 10 has a 9-day cycle
    (days 1–9, then repeat).
    """
    sessions = {s["day"]: s for s in programme.get("sessions", [])}
    rotation = _rotation_map(programme.get("rotation", []))

    day_of = (today - start).days + 1
    if day_of < 1:
        return CyclePosition(day_of, 0, False, None, "protocol has not started yet")
    day_of = min(day_of, 60)

    # The cycle repeats. Its length is the restart day minus one, or the highest
    # referenced day, whichever we can find.
    if cycle_length is None:
        restart = next(
            (d for d, e in rotation.items() if e.get("restarts_cycle")), None
        )
        highest = max([*sessions, *rotation], default=1)
        cycle_length = (restart - 1) if restart else highest

    cycle_day = (day_of - 1) % cycle_length + 1

    # Is this cycle-day a rest, a repeat, or an original session?
    entry = rotation.get(cycle_day)
    if entry and entry.get("is_rest"):
        return CyclePosition(day_of, cycle_day, True, None, "rest day")
    if entry and entry.get("repeats_day"):
        src = entry["repeats_day"]
        return CyclePosition(
            day_of, cycle_day, False, src, f"repeats the day {src} session"
        )
    if cycle_day in sessions:
        session = sessions[cycle_day]
        # An *explicitly empty* session is the sheet's rest slot (Cariani's sheets
        # carry a "TREINADOR" placeholder day with no exercises: 4 training days, then
        # this — the rest — then the cycle restarts). Treat it as rest. A fixture that
        # simply omits the exercises key is not this case and stays a training day.
        if "exercises" in session and not session["exercises"]:
            return CyclePosition(day_of, cycle_day, True, None, "rest day")
        focus = session.get("focus", "")
        return CyclePosition(day_of, cycle_day, False, cycle_day, focus)

    return CyclePosition(
        day_of, cycle_day, False, None,
        "no session mapped for this cycle day — check the sheet",
    )

def training_sequence(programme: dict, *, cycle_length: int | None = None) -> list[int]:
    """The non-rest session-days of one cycle, in order — the sequence you actually
    progress through as you train. Repeats resolve to their source day; rest days and
    the empty 'TREINADOR' placeholder are dropped. So a 4-on/1-off sheet returns
    ``[1, 2, 3, 4]`` — and the live session is chosen by how many of these you have
    *completed*, not by the calendar, so a missed day is picked up rather than skipped.
    """
    sessions = {s["day"]: s for s in programme.get("sessions", [])}
    rotation = _rotation_map(programme.get("rotation", []))
    if cycle_length is None:
        restart = next((d for d, e in rotation.items() if e.get("restarts_cycle")), None)
        highest = max([*sessions, *rotation], default=1)
        cycle_length = (restart - 1) if restart else highest

    seq: list[int] = []
    for d in range(1, cycle_length + 1):
        entry = rotation.get(d)
        if entry and entry.get("is_rest"):
            continue
        if entry and entry.get("repeats_day"):
            seq.append(entry["repeats_day"])
            continue
        ses = sessions.get(d)
        if ses is None:
            continue
        if "exercises" in ses and not ses["exercises"]:   # empty placeholder = rest
            continue
        seq.append(d)
    return seq

