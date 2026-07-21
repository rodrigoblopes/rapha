"""Pull Garmin data into the store.

**Activities are fetched in bulk; daily metrics are not.** Garmin exposes
`get_activities_by_date(start, end)` as a single call, but calories, sleep and HRV
are per-day endpoints. Fetching a year of those would be ~1,400 requests against
an API whose rate limit is unpublished and which has already returned 429 during
development.

So the two have different horizons, matched to what actually needs them:

    activities      a full year — the level assessment reads training history
    daily metrics   a shorter window — TDEE averages 14-28 days (ADR-005)

Normalisation lives here and nowhere else. Everything below this line speaks
canonical records, and cannot tell an API row from a `.FIT` export.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

from ..db import Store
from ..models import Activity, DailyMetrics, Source
from ..units import Grams, Kcal, Seconds

#: Politeness between per-day calls. The rate limit is unpublished; 429s are real.
PACE_S = 0.35

#: Default horizon for the per-day metrics, comfortably over the TDEE window.
DEFAULT_METRIC_DAYS = 60


def _get(d: Any, *path: str, default: Any = None) -> Any:
    """Walk a nested dict, tolerating missing keys and None at any level.

    Garmin's payloads are inconsistent between devices and firmware versions; a
    missing key means "this device did not record it", which must stay None
    rather than becoming zero.
    """
    for key in path:
        if not isinstance(d, dict):
            return default
        d = d.get(key)
    return default if d is None else d


def _int(value: Any) -> int | None:
    """Round to a whole number. Garmin returns some counts as floats."""
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _kcal(value: Any) -> Kcal | None:
    n = _int(value)
    return None if n is None else Kcal(n)


def daily_from_payloads(
    on: date,
    summary: dict | None,
    sleep: dict | None,
    hrv: dict | None,
    vo2: dict | None,
    weight_g: int | None = None,
) -> DailyMetrics:
    """Turn Garmin's several per-day payloads into one canonical record."""
    return DailyMetrics(
        on=on,
        source=Source.GARMIN_API,
        resting_hr=_int(_get(summary, "restingHeartRate")),
        hrv_ms=_int(_get(hrv, "hrvSummary", "lastNightAvg")),
        sleep=(
            Seconds(s)
            if (s := _int(_get(sleep, "dailySleepDTO", "sleepTimeSeconds")))
            else None
        ),
        steps=_int(_get(summary, "totalSteps")),
        calories_total=_kcal(_get(summary, "totalKilocalories")),
        calories_active=_kcal(_get(summary, "activeKilocalories")),
        stress_avg=_int(_get(summary, "averageStressLevel")),
        body_battery_high=_int(_get(summary, "bodyBatteryHighestValue")),
        body_battery_low=_int(_get(summary, "bodyBatteryLowestValue")),
        vo2max_x10=(
            _int(float(v) * 10)
            if (v := _get(vo2, "generic", "vo2MaxPreciseValue")) is not None
            else None
        ),
        weight=Grams(weight_g) if weight_g else None,
    )


def activity_from_payload(raw: dict) -> Activity | None:
    start_raw = raw.get("startTimeLocal") or raw.get("startTimeGMT")
    if not start_raw:
        return None
    try:
        start = datetime.fromisoformat(str(start_raw).replace("Z", ""))
    except ValueError:
        return None

    return Activity(
        activity_id=str(raw.get("activityId")),
        start=start,
        kind=_get(raw, "activityType", "typeKey", default="unknown"),
        duration=Seconds(_int(raw.get("duration")) or 0),
        source=Source.GARMIN_API,
        distance_m=_int(raw.get("distance")),
        avg_hr=_int(raw.get("averageHR")),
        max_hr=_int(raw.get("maxHR")),
        training_load_x10=(
            _int(float(load) * 10)
            if (load := raw.get("activityTrainingLoad")) is not None
            else None
        ),
        calories=_kcal(raw.get("calories")),
    )


def _weights_by_date(client, start: date, end: date) -> dict[date, int]:
    """Bulk weigh-ins, in grams. Absent is absent — never zero."""
    out: dict[date, int] = {}
    try:
        payload = client.get_weigh_ins(start.isoformat(), end.isoformat())
    except Exception:
        return out

    for day in _get(payload, "dailyWeightSummaries", default=[]) or []:
        stamp = _get(day, "summaryDate")
        grams = _int(_get(day, "latestWeight", "weight"))  # Garmin stores grams
        if stamp and grams:
            try:
                out[date.fromisoformat(stamp)] = grams
            except ValueError:
                continue
    return out


def sync(
    cfg,
    start: date,
    end: date,
    *,
    metric_days: int = DEFAULT_METRIC_DAYS,
    verbose: bool = False,
) -> int:
    """Pull Garmin into SQLite. Idempotent — a window is replaced, never merged."""
    from . import auth

    client = auth.connect(cfg)

    def say(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    say(f"syncing activities {start} .. {end}")
    raw_activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
    activities = [a for a in (activity_from_payload(r) for r in raw_activities) if a]
    say(f"  {len(activities)} activities")

    metric_start = max(start, end - timedelta(days=metric_days))
    say(f"syncing daily metrics {metric_start} .. {end}")
    weights = _weights_by_date(client, metric_start, end)

    days: list[DailyMetrics] = []
    cursor = metric_start
    while cursor <= end:
        stamp = cursor.isoformat()
        payloads: list[dict | None] = []
        for fetch in (
            client.get_user_summary,
            client.get_sleep_data,
            client.get_hrv_data,
            client.get_max_metrics,
        ):
            try:
                payloads.append(fetch(stamp))
            except Exception:
                payloads.append(None)
            time.sleep(PACE_S)

        summary, sleep, hrv, vo2 = payloads
        if isinstance(vo2, list):
            vo2 = vo2[0] if vo2 else None
        days.append(
            daily_from_payloads(
                cursor, summary, sleep, hrv, vo2, weights.get(cursor)
            )
        )
        if verbose and cursor.day == 1:
            say(f"  ... {cursor}")
        cursor += timedelta(days=1)

    with Store(cfg.db_path) as store:
        store.ingest_activities(start, end, activities)
        store.ingest_daily(metric_start, end, days)

    measured = sum(1 for d in days if d.calories_total is not None)
    say(
        f"stored {len(activities)} activities and {len(days)} days "
        f"({measured} with an expenditure reading) in {cfg.db_path}"
    )
    return 0
