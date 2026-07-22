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
        focus = sessions[cycle_day].get("focus", "")
        return CyclePosition(day_of, cycle_day, False, cycle_day, focus)

    return CyclePosition(
        day_of, cycle_day, False, None,
        "no session mapped for this cycle day — check the sheet",
    )
