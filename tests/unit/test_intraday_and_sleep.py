"""The long-history sleep backfill and the intraday cache. Invented data only."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from rapha.dashboard.briefing import _intraday
from rapha.garmin.browser_pull import _sleep_seconds_by_date, _write_intraday_cache


def test_sleep_range_maps_dates_to_seconds():
    payload = [
        {"calendarDate": "2026-08-13", "sleepTimeSeconds": 25080},
        {"calendarDate": "2026-08-12", "sleepTimeSeconds": 26100},
        {"calendarDate": "2026-08-11", "sleepTimeSeconds": None},  # unmeasured night
        {"sleepTimeSeconds": 20000},                               # no date -> dropped
    ]
    out = _sleep_seconds_by_date(payload)
    assert out[date(2026, 8, 13)] == 25080
    assert out[date(2026, 8, 12)] == 26100
    assert date(2026, 8, 11) not in out  # a null night is absent, not zero


def test_sleep_range_tolerates_none():
    assert _sleep_seconds_by_date(None) == {}


def test_intraday_cache_round_trips_and_drops_gaps(tmp_path):
    cfg = SimpleNamespace(home=tmp_path)
    payload = {
        "calendarDate": "2026-08-13",
        "heartRateValues": [[1786545000000, 49], [1786545120000, None], [1786545240000, 53]],
    }
    _write_intraday_cache(cfg, payload)
    written = json.loads((tmp_path / "data" / "cache" / "intraday.json").read_text())
    assert written["date"] == "2026-08-13"
    assert written["hr"] == [[1786545000000, 49], [1786545240000, 53]]  # null bpm dropped

    # …and the briefing reads exactly that back.
    assert _intraday(tmp_path) == written


def test_intraday_reader_is_empty_when_absent(tmp_path):
    assert _intraday(tmp_path) == {}


def test_intraday_cache_handles_missing_values(tmp_path):
    cfg = SimpleNamespace(home=tmp_path)
    _write_intraday_cache(cfg, None)
    written = json.loads((tmp_path / "data" / "cache" / "intraday.json").read_text())
    assert written == {"date": "", "hr": []}
