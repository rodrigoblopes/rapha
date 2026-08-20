"""Per-exercise set history — the raw material for load progression.

Garmin's `exerciseSets` endpoint reports every set of a strength activity: the
detected exercise, the reps, and the weight **in integer grams** (25000 == 25 kg).
That is the one thing the activity summary throws away, and it is exactly what
Módulo 17's double-progression rule needs — you cannot tell whether a lift is
progressing without last session's top set.

**Same window-replace discipline as the main store, keyed on the activity.** One
activity's sets are one window: re-recording an activity deletes its rows and
reinserts them. So a re-sync over an overlapping range, or Garmin re-processing a
recent activity into a heavier top set, both land cleanly — no duplicates, no stale
rows. (See db.py's header; MrW's ADR-007 is the origin.)

Only ACTIVE sets are stored. REST rows carry no exercise, no reps and no weight —
keeping them would just be noise the progression read has to filter every time.
Bodyweight movements store a NULL weight, never zero: absent load is a fact.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Self

SCHEMA = """
CREATE TABLE IF NOT EXISTS exercise_sets (
    activity_id  INTEGER NOT NULL,
    on_date      TEXT    NOT NULL,
    set_index    INTEGER NOT NULL,
    name         TEXT,
    category     TEXT,
    reps         INTEGER,
    weight_g     INTEGER,
    PRIMARY KEY (activity_id, set_index)
);
CREATE INDEX IF NOT EXISTS exercise_sets_name ON exercise_sets(name);
CREATE INDEX IF NOT EXISTS exercise_sets_date ON exercise_sets(on_date);
"""


@dataclass(frozen=True, slots=True)
class SetRow:
    """One working set as stored."""

    activity_id: int
    on: date
    set_index: int
    name: str | None
    category: str | None
    reps: int | None
    weight_g: int | None


@dataclass(frozen=True, slots=True)
class SessionBest:
    """The shape of one exercise's session for the progression view."""

    on: date
    top_weight_g: int | None
    reps_at_top: int | None
    volume_g: int
    sets: int


@dataclass(frozen=True, slots=True)
class ExerciseSummary:
    """One movement, once, for a history index."""

    name: str
    category: str | None
    sessions: int
    last_seen: date


class ExerciseStore:
    """SQLite-backed per-set store. Use as a context manager.

    Shares the ``rapha.db`` file with :class:`~rapha.db.Store`; the tables are
    disjoint, so opening both (sequentially) against the same path is fine.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ── ingest ───────────────────────────────────────────────────────────────

    def record_activity(self, activity_id: int, on: date, payload: dict) -> int:
        """Store one activity's ACTIVE sets. Returns the number kept.

        Window-replace on ``activity_id``: the delete and insert are one atomic
        step, so re-recording the same (or a revised) activity never duplicates.
        """
        raw_sets = (payload or {}).get("exerciseSets") or []
        rows = []
        for i, s in enumerate(raw_sets):
            if s.get("setType") != "ACTIVE":
                continue
            exercises = s.get("exercises") or []
            first = exercises[0] if exercises else {}
            rows.append(
                (
                    activity_id,
                    on.isoformat(),
                    i,
                    first.get("name"),
                    first.get("category"),
                    _as_int(s.get("repetitionCount")),
                    _as_int(s.get("weight")),
                )
            )

        with self._transaction():
            self._conn.execute(
                "DELETE FROM exercise_sets WHERE activity_id = ?", (activity_id,)
            )
            self._conn.executemany(
                """INSERT INTO exercise_sets
                       (activity_id, on_date, set_index, name, category, reps, weight_g)
                   VALUES (?,?,?,?,?,?,?)""",
                rows,
            )
        return len(rows)

    # ── read ─────────────────────────────────────────────────────────────────

    def sets_for_activity(self, activity_id: int) -> list[SetRow]:
        rows = self._conn.execute(
            "SELECT * FROM exercise_sets WHERE activity_id = ? ORDER BY set_index",
            (activity_id,),
        ).fetchall()
        return [_row(r) for r in rows]

    def progression(self, name: str) -> list[SessionBest]:
        """One exercise's sessions, newest first, each reduced to its top set.

        ``top_weight_g`` is the heaviest working set that day; ``reps_at_top`` the
        reps performed at that weight (the heaviest, most-reps set if several tie);
        ``volume_g`` the session's total reps×weight — the three numbers Módulo 17's
        double-progression rule reads to decide whether to add load.
        """
        rows = self._conn.execute(
            """SELECT on_date, reps, weight_g FROM exercise_sets
               WHERE name = ? ORDER BY on_date""",
            (name,),
        ).fetchall()

        by_day: dict[date, list[tuple[int | None, int | None]]] = {}
        for r in rows:
            on = date.fromisoformat(r["on_date"])
            by_day.setdefault(on, []).append((r["reps"], r["weight_g"]))

        out: list[SessionBest] = []
        for on in sorted(by_day, reverse=True):
            sets = by_day[on]
            volume = sum((reps or 0) * (w or 0) for reps, w in sets)
            weighted = [(reps, w) for reps, w in sets if w is not None]
            if weighted:
                top_w = max(w for _, w in weighted)
                reps_at_top = max(reps or 0 for reps, w in weighted if w == top_w)
            else:  # a purely bodyweight session — rank by reps instead
                top_w = None
                reps_at_top = max((reps or 0 for reps, _ in sets), default=0)
            out.append(SessionBest(on, top_w, reps_at_top, volume, len(sets)))
        return out

    def last_session_sets(
        self, name: str, *, weighted_only: bool = False
    ) -> list[tuple[int | None, int | None]]:
        """One movement's ACTIVE sets from its most recent session: (reps, weight_g).

        This is what the double-progression call reads — last time's actual sets, in
        order — to judge whether to add load. Empty if the movement was never logged.

        ``weighted_only`` picks the most recent session that actually carried a load,
        skipping later sessions where Garmin logged reps but no weight (a machine set
        the watch never captured). That is what progression needs: the last *known*
        working load, not a repping-only session with the weight missing.
        """
        weight_clause = " AND weight_g >= 1000" if weighted_only else ""
        latest = self._conn.execute(
            f"SELECT MAX(on_date) AS d FROM exercise_sets WHERE name = ?{weight_clause}",
            (name,),
        ).fetchone()
        if not latest or not latest["d"]:
            return []
        rows = self._conn.execute(
            """SELECT reps, weight_g FROM exercise_sets
               WHERE name = ? AND on_date = ? ORDER BY set_index""",
            (name, latest["d"]),
        ).fetchall()
        return [(r["reps"], r["weight_g"]) for r in rows]

    def all_sets(self) -> list[SetRow]:
        """Every stored working set, oldest first — the raw feed for volume/tonnage."""
        rows = self._conn.execute(
            "SELECT * FROM exercise_sets ORDER BY on_date, activity_id, set_index"
        ).fetchall()
        return [_row(r) for r in rows]

    def exercises(self) -> list[ExerciseSummary]:
        """Every movement seen, once, with its session count and latest date."""
        rows = self._conn.execute(
            """SELECT name,
                      MAX(category)                    AS category,
                      COUNT(DISTINCT on_date)          AS sessions,
                      MAX(on_date)                     AS last_seen
               FROM exercise_sets
               WHERE name IS NOT NULL
               GROUP BY name
               ORDER BY last_seen DESC, name""",
        ).fetchall()
        return [
            ExerciseSummary(
                name=r["name"],
                category=r["category"],
                sessions=r["sessions"],
                last_seen=date.fromisoformat(r["last_seen"]),
            )
            for r in rows
        ]

    # ── internals ────────────────────────────────────────────────────────────

    @contextmanager
    def _transaction(self):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")


def _as_int(value) -> int | None:
    """Garmin sends reps/weight as ints, but tolerate a stray float; None stays None."""
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _row(r: sqlite3.Row) -> SetRow:
    return SetRow(
        activity_id=r["activity_id"],
        on=date.fromisoformat(r["on_date"]),
        set_index=r["set_index"],
        name=r["name"],
        category=r["category"],
        reps=r["reps"],
        weight_g=r["weight_g"],
    )
