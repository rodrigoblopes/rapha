"""The store. SQLite, one file, in %RAPHA_HOME%.

**The unit of ingest is a window, not a row.** One source, one closed date range:
delete everything in that range, insert the batch, commit. MrW arrived at the same
rule (its ADR-007) after finding that row-identity schemes cannot work on field-poor
data — two identical rows are either a real pair or a duplicate, and nothing in the
data says which.

Garmin makes this concrete rather than theoretical. Sync is re-run over overlapping
ranges constantly, and Garmin revises recent days as a watch back-fills. Window
replacement makes duplicates structurally impossible and lets a revision land
cleanly, without either being a special case.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from .models import Activity, DailyMetrics, Measurement, Source
from .units import Grams, Kcal, Millimetres, Seconds

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    on_date            TEXT PRIMARY KEY,
    source             TEXT NOT NULL,
    resting_hr         INTEGER,
    hrv_ms             INTEGER,
    sleep_s            INTEGER,
    steps              INTEGER,
    calories_total     INTEGER,
    calories_active    INTEGER,
    stress_avg         INTEGER,
    body_battery_high  INTEGER,
    body_battery_low   INTEGER,
    vo2max_x10         INTEGER,
    weight_g           INTEGER
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id        TEXT PRIMARY KEY,
    start_at           TEXT NOT NULL,
    on_date            TEXT NOT NULL,
    kind               TEXT NOT NULL,
    source             TEXT NOT NULL,
    duration_s         INTEGER NOT NULL,
    distance_m         INTEGER,
    avg_hr             INTEGER,
    max_hr             INTEGER,
    training_load_x10  INTEGER,
    calories           INTEGER
);
CREATE INDEX IF NOT EXISTS activities_on_date ON activities(on_date);

CREATE TABLE IF NOT EXISTS measurements (
    on_date   TEXT PRIMARY KEY,
    source    TEXT NOT NULL,
    weight_g  INTEGER,
    waist_mm  INTEGER,
    neck_mm   INTEGER,
    hip_mm    INTEGER
);
"""


def _q(cls: type, value: int | None):
    """Rebuild a quantity from storage. None stays None — 'not measured' is a fact."""
    return None if value is None else cls(value)


def _v(quantity) -> int | None:
    return None if quantity is None else quantity.value


class Store:
    """A SQLite-backed store. Use as a context manager."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
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

    @staticmethod
    def _check_window(start: date, end: date, dates: list[date], what: str) -> None:
        if start > end:
            raise ValueError(f"window start {start} is after end {end}")
        stray = [d for d in dates if not (start <= d <= end)]
        if stray:
            # Accepting it silently would place a row where the next window-replace
            # for its real date cannot reach it. It would survive every future sync
            # as a ghost, and nothing would ever flag it.
            raise ValueError(
                f"{what} outside the declared window {start}..{end}: {sorted(stray)}"
            )

    def ingest_daily(
        self, window_start: date, window_end: date, rows: list[DailyMetrics]
    ) -> None:
        self._check_window(window_start, window_end, [r.on for r in rows], "daily rows")
        with self._transaction():
            self._conn.execute(
                "DELETE FROM daily_metrics WHERE on_date BETWEEN ? AND ?",
                (window_start.isoformat(), window_end.isoformat()),
            )
            self._conn.executemany(
                """INSERT INTO daily_metrics (
                       on_date, source, resting_hr, hrv_ms, sleep_s, steps,
                       calories_total, calories_active, stress_avg,
                       body_battery_high, body_battery_low, vo2max_x10, weight_g
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.on.isoformat(),
                        r.source.value,
                        r.resting_hr,
                        r.hrv_ms,
                        _v(r.sleep),
                        r.steps,
                        _v(r.calories_total),
                        _v(r.calories_active),
                        r.stress_avg,
                        r.body_battery_high,
                        r.body_battery_low,
                        r.vo2max_x10,
                        _v(r.weight),
                    )
                    for r in rows
                ],
            )

    def ingest_activities(
        self, window_start: date, window_end: date, rows: list[Activity]
    ) -> None:
        self._check_window(
            window_start, window_end, [r.start.date() for r in rows], "activities"
        )
        with self._transaction():
            self._conn.execute(
                "DELETE FROM activities WHERE on_date BETWEEN ? AND ?",
                (window_start.isoformat(), window_end.isoformat()),
            )
            self._conn.executemany(
                """INSERT INTO activities (
                       activity_id, start_at, on_date, kind, source, duration_s,
                       distance_m, avg_hr, max_hr, training_load_x10, calories
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.activity_id,
                        r.start.isoformat(),
                        r.start.date().isoformat(),
                        r.kind,
                        r.source.value,
                        r.duration.value,
                        r.distance_m,
                        r.avg_hr,
                        r.max_hr,
                        r.training_load_x10,
                        _v(r.calories),
                    )
                    for r in rows
                ],
            )

    def record_measurement(self, m: Measurement) -> None:
        """Manual tape entries are one row at a time — no window, no batch."""
        with self._transaction():
            self._conn.execute(
                """INSERT INTO measurements (on_date, source, weight_g, waist_mm, neck_mm, hip_mm)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(on_date) DO UPDATE SET
                       source=excluded.source, weight_g=excluded.weight_g,
                       waist_mm=excluded.waist_mm, neck_mm=excluded.neck_mm,
                       hip_mm=excluded.hip_mm""",
                (
                    m.on.isoformat(),
                    m.source.value,
                    _v(m.weight),
                    _v(m.waist),
                    _v(m.neck),
                    _v(m.hip),
                ),
            )

    # ── read ─────────────────────────────────────────────────────────────────

    def daily_between(self, start: date, end: date) -> list[DailyMetrics]:
        rows = self._conn.execute(
            "SELECT * FROM daily_metrics WHERE on_date BETWEEN ? AND ? ORDER BY on_date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            DailyMetrics(
                on=date.fromisoformat(r["on_date"]),
                source=Source(r["source"]),
                resting_hr=r["resting_hr"],
                hrv_ms=r["hrv_ms"],
                sleep=_q(Seconds, r["sleep_s"]),
                steps=r["steps"],
                calories_total=_q(Kcal, r["calories_total"]),
                calories_active=_q(Kcal, r["calories_active"]),
                stress_avg=r["stress_avg"],
                body_battery_high=r["body_battery_high"],
                body_battery_low=r["body_battery_low"],
                vo2max_x10=r["vo2max_x10"],
                weight=_q(Grams, r["weight_g"]),
            )
            for r in rows
        ]

    def activities_between(self, start: date, end: date) -> list[Activity]:
        rows = self._conn.execute(
            "SELECT * FROM activities WHERE on_date BETWEEN ? AND ? ORDER BY start_at",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            Activity(
                activity_id=r["activity_id"],
                start=datetime.fromisoformat(r["start_at"]),
                kind=r["kind"],
                duration=Seconds(r["duration_s"]),
                source=Source(r["source"]),
                distance_m=r["distance_m"],
                avg_hr=r["avg_hr"],
                max_hr=r["max_hr"],
                training_load_x10=r["training_load_x10"],
                calories=_q(Kcal, r["calories"]),
            )
            for r in rows
        ]

    def measurements(self) -> list[Measurement]:
        rows = self._conn.execute(
            "SELECT * FROM measurements ORDER BY on_date"
        ).fetchall()
        return [
            Measurement(
                on=date.fromisoformat(r["on_date"]),
                source=Source(r["source"]),
                weight=_q(Grams, r["weight_g"]),
                waist=_q(Millimetres, r["waist_mm"]),
                neck=_q(Millimetres, r["neck_mm"]),
                hip=_q(Millimetres, r["hip_mm"]),
            )
            for r in rows
        ]

    def weight_history(self) -> list[tuple[date, int]]:
        """Every weigh-in, oldest first, as (date, grams). Unions both sources.

        Weigh-ins can arrive on a daily_metrics row (inside the metric window) or as
        a measurement (a manual tape entry, or a Garmin weigh-in from beyond that
        window). A date present in both — the same weigh-in seen twice — collapses to
        one point, the measurement winning since that is where the full history lives.
        """
        by_date: dict[date, int] = {}
        daily = self._conn.execute(
            "SELECT on_date, weight_g FROM daily_metrics WHERE weight_g IS NOT NULL"
        ).fetchall()
        meas = self._conn.execute(
            "SELECT on_date, weight_g FROM measurements WHERE weight_g IS NOT NULL"
        ).fetchall()
        for r in daily:  # measurements applied second so they win on a shared date
            by_date[date.fromisoformat(r["on_date"])] = r["weight_g"]
        for r in meas:
            by_date[date.fromisoformat(r["on_date"])] = r["weight_g"]
        return sorted(by_date.items())

    def latest_weight(self) -> Grams | None:
        """Most recent bodyweight from any source — scale, watch, or tape entry."""
        row = self._conn.execute(
            """SELECT weight_g FROM (
                   SELECT on_date, weight_g FROM daily_metrics WHERE weight_g IS NOT NULL
                   UNION ALL
                   SELECT on_date, weight_g FROM measurements WHERE weight_g IS NOT NULL
               ) ORDER BY on_date DESC LIMIT 1"""
        ).fetchone()
        return None if row is None else Grams(row["weight_g"])

    # ── internals ────────────────────────────────────────────────────────────

    @contextmanager
    def _transaction(self):
        """Explicit BEGIN/COMMIT/ROLLBACK.

        The connection runs with ``isolation_level=None`` (autocommit), so
        ``with connection:`` would be a no-op here rather than a transaction — a
        DELETE that succeeded followed by an INSERT that failed would leave the
        window empty and stay that way. Window replacement is only safe if the
        delete and the insert are one atomic step.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")


def open_store(home: Path) -> Store:
    return Store(home / "rapha.db")
