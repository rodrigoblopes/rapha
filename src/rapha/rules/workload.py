"""Acute:chronic workload — are you ramping load faster than you're adapting to it.

Garmin already scores every activity's training load; the summary stores it and then
nobody looks. Summed the sports-science way it answers the question a lifter can't feel
until it's too late: this week's load against the rolling four-week average you've
actually built a base for. The acute:chronic ratio (ACWR) is the standard reading —
around 0.8–1.3 is the "sweet spot" where fitness rises without the injury risk that
climbs once a week spikes far above what the body is prepared for.

Pure: a list of (date, load) in, a balance out. Load is Garmin's points ×10 (integer),
reported back as whole points. This is an observation against a named model, not a
verdict — a single hard block can and should breach 1.3 deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class LoadBalance:
    acute: int          # total load over the acute window (7 days), in points
    chronic_weekly: int  # average weekly load over the chronic window (28 days)
    ratio: float | None  # acute / chronic_weekly — the ACWR
    band: str            # detraining | building | optimal | high | spike | unknown
    reliable: bool       # False until enough history exists to trust the ratio


def _band(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio < 0.8:
        return "detraining"
    if ratio <= 1.3:
        return "optimal"
    if ratio <= 1.5:
        return "high"
    return "spike"


def acwr(
    loads: list[tuple[date, int | None]],
    *,
    today: date | None = None,
    acute_days: int = 7,
    chronic_days: int = 28,
) -> LoadBalance:
    """Acute (7-day) vs chronic (mean-weekly over 28-day) training load.

    ``reliable`` is False until at least ``chronic_days`` of span is available — before
    that the chronic base is under-counted and the ratio reads artificially high, so the
    card can say "still building a baseline" rather than cry wolf.
    """
    pts = [(d, (ld or 0) / 10) for d, ld in loads if ld]
    if not pts:
        return LoadBalance(0, 0, None, "unknown", False)
    anchor = today or max(d for d, _ in pts)

    acute = sum(v for d, v in pts if 0 <= (anchor - d).days < acute_days)
    chronic_total = sum(v for d, v in pts if 0 <= (anchor - d).days < chronic_days)
    chronic_weekly = chronic_total / (chronic_days / 7)
    ratio = round(acute / chronic_weekly, 2) if chronic_weekly > 0 else None

    span = (anchor - min(d for d, _ in pts)).days + 1
    reliable = span >= chronic_days
    return LoadBalance(
        acute=round(acute),
        chronic_weekly=round(chronic_weekly),
        ratio=ratio,
        band=_band(ratio),
        reliable=reliable,
    )
