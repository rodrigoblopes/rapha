"""The Garmin write path. WORKOUTS ONLY (ADR-001).

⚠️ Everything in this module creates, schedules or deletes a **workout**. It never
deletes an activity, never modifies health or body-composition data, never touches
account settings. That narrowness is the invariant that replaces MrW's "nothing
writes to a financial institution" — the write surface is one verb, on purpose.

⚠️ Nothing here runs on a dry run. `push` builds and describes the workout with no
client at all, and only calls into this module after explicit confirmation.
"""

from __future__ import annotations

from ..config import Config
from . import auth


def create_workout(cfg: Config, payload: dict) -> int:
    """Create one workout in Garmin Connect. Returns its workout id."""
    client = auth.connect(cfg)
    result = client.upload_workout(payload)
    workout_id = result.get("workoutId") if isinstance(result, dict) else None
    if workout_id is None:
        raise RuntimeError(f"Garmin did not return a workoutId: {result!r}")
    return int(workout_id)


def schedule_workout(cfg: Config, workout_id: int, on: str) -> dict:
    """Put an existing workout on the calendar for a date (YYYY-MM-DD)."""
    client = auth.connect(cfg)
    return client.schedule_workout(workout_id, on)


def delete_workout(cfg: Config, workout_id: int) -> None:
    """Remove a workout. Used to clean up a verification push (ADR-001 test path)."""
    client = auth.connect(cfg)
    client.delete_workout(workout_id)
