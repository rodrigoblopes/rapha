"""Parse Garmin Connect's web-export CSVs into canonical records.

This is the fallback rung that turned out to matter: the API was IP-blocked and the
Chrome cookies were App-Bound-encrypted, so the data arrived as Garmin's own
"export" — one CSV per widget. They are inconsistent in every way a set of CSVs can
be, so the parsing is defensive by necessity:

- **Three date formats** across files: ISO (`2026-07-22`), slashed (`02/07/2026`),
  and bare `25 Jun` with no year (anchored to the export's year).
- **Comma decimals** in the activity file (`1,02` = 1.02, Brazilian locale) but
  **dot decimals** elsewhere (`85.0 kg`).
- **Units glued to numbers** (`58ms`, `85.0 kg`, `6h 23min`).
- **`--` for missing**, which stays None — never zero.

Everything emerges as the same `Activity` / `DailyMetrics` the API adapter emits,
tagged `Source.GARMIN_EXPORT`, so the rules engine cannot tell the difference.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from ..models import Activity, DailyMetrics, Source
from ..units import Grams, Kcal, Seconds

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}


def parse_dmy(text: str | None, *, default_year: int | None = None) -> date | None:
    """Parse any of Garmin's export date formats, or None."""
    if not text:
        return None
    s = text.strip()
    if not s or s == "--":
        return None

    # ISO, optionally with a time: 2026-07-22[ 05:28:51]
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", s):
        return date(int(m[1]), int(m[2]), int(m[3]))

    # Slashed d/m/Y
    if m := re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
        return date(int(m[3]), int(m[2]), int(m[1]))

    # "22 Jul 2026" or bare "25 Jun" (year defaulted)
    if m := re.match(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*(?:\s+(\d{4}))?", s):
        month = _MONTHS.get(m[2].lower())
        if month:
            year = int(m[3]) if m[3] else default_year
            if year:
                return date(year, month, int(m[1]))
    return None


def parse_num(text: str | None, *, comma_decimal: bool = False) -> float | None:
    """A number that may carry units, comma decimals, or dot thousands."""
    if text is None:
        return None
    s = text.strip()
    if not s or s in ("--", "—"):
        return None
    s = re.sub(r"[^\d.,-]", "", s)  # drop units like 'ms', 'kg'
    if not s or s in ("-", ".", ","):
        return None
    if comma_decimal:
        # dot is thousands, comma is decimal: 3.470 -> 3470; 1,02 -> 1.02
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_duration_hms(text: str | None) -> Seconds | None:
    """`HH:MM:SS` (a trailing `,5` fraction is dropped) -> Seconds."""
    if not text or text.strip() in ("--", ""):
        return None
    parts = text.split(",")[0].strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.insert(0, 0)
    h, m, sec = nums[-3], nums[-2], nums[-1]
    return Seconds(h * 3600 + m * 60 + sec)


def parse_sleep_duration(text: str | None) -> Seconds | None:
    """`6h 23min` -> Seconds."""
    if not text or text.strip() in ("--", ""):
        return None
    h = re.search(r"(\d+)\s*h", text)
    m = re.search(r"(\d+)\s*min", text)
    if not h and not m:
        return None
    return Seconds((int(h[1]) if h else 0) * 3600 + (int(m[1]) if m else 0) * 60)


def _kind(activity_type: str) -> str:
    return re.sub(r"\s+", "_", activity_type.strip().lower())


def parse_activity_row(row: dict[str, str]) -> Activity | None:
    """One row of `Activities (1).csv` -> an Activity, or None without a date."""
    when = row.get("Date", "")
    d = parse_dmy(when)
    if d is None:
        return None
    try:
        start = datetime.fromisoformat(when.strip())
    except ValueError:
        start = datetime(d.year, d.month, d.day)

    dist_km = parse_num(row.get("Distance"), comma_decimal=True)
    return Activity(
        activity_id=f"export-{start.isoformat()}-{_kind(row.get('Activity Type', ''))}",
        start=start,
        kind=_kind(row.get("Activity Type", "unknown")),
        duration=parse_duration_hms(row.get("Time")) or Seconds(0),
        source=Source.GARMIN_EXPORT,
        distance_m=round(dist_km * 1000) if dist_km else None,
        avg_hr=_int(row.get("Avg HR")),
        max_hr=_int(row.get("Max HR")),
        calories=_kcal(row.get("Calories")),
    )


def _int(text: str | None) -> int | None:
    n = parse_num(text)
    return None if n is None else round(n)


def _kcal(text: str | None) -> Kcal | None:
    n = _int(text)
    return None if n is None else Kcal(n)


# ── whole-directory ingest ───────────────────────────────────────────────────

def _read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def parse_activities(export_dir: Path) -> list[Activity]:
    """The richest activities file wins (`Activities (1).csv` over the summary)."""
    candidates = sorted(export_dir.glob("Activities*.csv"),
                        key=lambda p: p.stat().st_size, reverse=True)
    for path in candidates:
        rows = _read_csv(path)
        if not rows or "Activity Type" not in rows[0]:
            continue
        header = rows[0]
        acts = [
            a for a in (
                parse_activity_row(dict(zip(header, r, strict=False)))
                for r in rows[1:] if r
            ) if a
        ]
        if acts:
            return acts
    return []


def parse_daily(export_dir: Path, *, default_year: int) -> list[DailyMetrics]:
    """Merge every daily-metric CSV into one DailyMetrics per date."""
    fields: dict[date, dict] = {}

    def cell(d: date, **kw) -> None:
        fields.setdefault(d, {}).update({k: v for k, v in kw.items() if v is not None})

    def each(name: str):
        path = export_dir / name
        if not path.is_file():
            return
        rows = _read_csv(path)
        for r in rows:
            if r:
                yield r

    # Calories: date, Active, Resting, Total  (Total IS the measured TDEE)
    for r in each("Calories.csv"):
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 4:
            cell(d, calories_active=_kcal(r[1]), calories_total=_kcal(r[3]))

    for r in each("Resting Heart Rate.csv"):
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 2:
            cell(d, resting_hr=_int(r[1]))

    for r in each("HRV Status.csv"):  # Date, Overnight HRV, Baseline, 7d Avg
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 2:
            cell(d, hrv_ms=_int(r[1]))

    for r in each("Steps.csv"):
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 2:
            cell(d, steps=_int(r[1]))

    for r in each("Stress.csv"):
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 2:
            cell(d, stress_avg=_int(r[1]))

    for r in each("VO₂ Max.csv"):
        if len(r) >= 3 and (d := parse_dmy(r[0], default_year=default_year)):
            v = parse_num(r[2])
            cell(d, vo2max_x10=round(v * 10) if v else None)

    # Sleep: date, Score, RHR, BodyBattery, PulseOx, Respiration, HRV, Quality, Duration, ...
    for r in each("Sleep.csv"):
        if (d := parse_dmy(r[0], default_year=default_year)) and len(r) >= 9:
            cell(d, sleep=parse_sleep_duration(r[8]),
                 body_battery_high=_int(r[3]) if len(r) > 3 else None)

    # Weight: date rows (" 22 Jul 2026") followed by a data row with the kg value.
    _parse_weight(export_dir / "Weight.csv", cell)

    return [
        DailyMetrics(on=d, source=Source.GARMIN_EXPORT, **fields[d])
        for d in sorted(fields)
    ]


def _parse_weight(path: Path, cell) -> None:
    if not path.is_file():
        return
    current: date | None = None
    for r in _read_csv(path):
        if not r or not r[0].strip():
            continue
        d = parse_dmy(r[0])
        if d is not None and (len(r) < 2 or not r[1].strip()):
            current = d           # a date header line
            continue
        if current is not None and len(r) >= 2:
            kg = parse_num(r[1])  # "85.0 kg"
            if kg:
                cell(current, weight=Grams(round(kg * 1000)))
                current = None


def _infer_year(export_dir: Path) -> int:
    """Anchor the year for the year-less dates, from a file that carries one."""
    for name in ("Sleep.csv", "Fitness Age.csv"):
        path = export_dir / name
        if path.is_file():
            for r in _read_csv(path)[1:]:
                if r and (d := parse_dmy(r[0])):
                    return d.year
    return datetime.now().year  # only a fallback anchor


def ingest_export(export_dir: Path, db_path: Path) -> dict:
    """Parse an export directory and window-replace it into the store."""
    from ..db import Store

    year = _infer_year(export_dir)
    activities = parse_activities(export_dir)
    days = parse_daily(export_dir, default_year=year)

    summary = {"activities": len(activities), "days": len(days)}
    if not activities and not days:
        return summary

    all_dates = [a.start.date() for a in activities] + [d.on for d in days]
    lo, hi = min(all_dates), max(all_dates)
    summary["range"] = f"{lo}..{hi}"

    with Store(db_path) as store:
        if activities:
            store.ingest_activities(min(a.start.date() for a in activities),
                                    max(a.start.date() for a in activities), activities)
        if days:
            store.ingest_daily(min(d.on for d in days), max(d.on for d in days), days)

    summary["measured_tdee_days"] = sum(1 for d in days if d.calories_total is not None)
    return summary
