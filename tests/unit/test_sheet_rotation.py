"""Week-based training-sheet rotation. Invented sheets with Cariani-style labels."""

from __future__ import annotations

from datetime import date

from rapha.dashboard.briefing import (
    _live_sheet,
    _protocol_week,
    _sheet_switch,
    _sheet_weeks,
)

PROGS = [
    {"level": "INTERMEDIÁRIO", "sheet_number": 1, "weeks": "1ª,2ª,3ª E 4ª SEMANAS",
     "sessions": [{"day": 1}]},
    {"level": "INTERMEDIÁRIO", "sheet_number": 2, "weeks": "5ª,6ª,7ª E 8ª SEMANAS",
     "sessions": [{"day": 1}]},
    {"level": "INTERMEDIÁRIO", "sheet_number": 3, "weeks": "por 8 SEMANAS",
     "sessions": [{"day": 1}]},
]
ST = {"level": "INTERMEDIÁRIO", "protocol_start": "2026-07-23"}


def test_weeks_label_parses_to_a_set():
    assert _sheet_weeks("1ª,2ª,3ª E 4ª SEMANAS") == {1, 2, 3, 4}
    assert _sheet_weeks("5ª,6ª,7ª E 8ª SEMANAS") == {5, 6, 7, 8}
    assert _sheet_weeks("") == set()


def test_protocol_week_counts_from_start():
    assert _protocol_week(ST, date(2026, 7, 23)) == 1   # day 1
    assert _protocol_week(ST, date(2026, 8, 16)) == 4   # day 25
    assert _protocol_week(ST, date(2026, 8, 20)) == 5   # day 29


def test_week_four_serves_sheet_one():
    assert _live_sheet(PROGS, ST, date(2026, 8, 16))["sheet_number"] == 1


def test_week_five_advances_to_sheet_two():
    assert _live_sheet(PROGS, ST, date(2026, 8, 20))["sheet_number"] == 2


def test_week_eight_stays_on_sheet_two_not_three():
    # Sheet 3 ("por 8 SEMANAS" -> {8}) also mentions week 8; list order keeps Sheet 2.
    assert _live_sheet(PROGS, ST, date(2026, 9, 9))["sheet_number"] == 2


def test_past_the_last_block_keeps_the_latest_started_sheet():
    # Week 9 (day 57-63) — no sheet's range contains it; fall back to Sheet 2.
    assert _live_sheet(PROGS, ST, date(2026, 9, 20))["sheet_number"] == 2


def test_switch_announces_the_next_sheet_and_date():
    sw = _sheet_switch(PROGS, ST, date(2026, 8, 16))
    assert sw["sheet"] == 2
    assert sw["starts_on"] == "2026-08-20"
    assert sw["days_until"] == 4


def test_no_switch_once_on_the_final_block():
    assert _sheet_switch(PROGS, ST, date(2026, 8, 25)) is None


def test_no_protocol_start_falls_back_to_first_sheet():
    assert _live_sheet(PROGS, {"level": "INTERMEDIÁRIO"}, date(2026, 8, 16))[
        "sheet_number"] == 1
