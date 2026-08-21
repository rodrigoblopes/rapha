"""The Claude-authored coach note: markdown rendering + freshness override."""

import os
from datetime import date
from types import SimpleNamespace

from rapha.dashboard.briefing import _coach_note
from rapha.dashboard.portal import _bold, _md_lite


class TestMarkdownLite:
    def test_bold_wraps_double_star(self):
        assert _bold("try 100 **kg** now") == "try 100 <strong>kg</strong> now"

    def test_paragraphs_and_bullets(self):
        html = _md_lite("Line one.\n\n- a\n- b")
        assert "<p" in html and "<ul" in html and html.count("<li>") == 2

    def test_bold_is_balanced_when_stars_are_odd(self):
        # A stray ** should not crash or swallow the rest of the note.
        assert "<strong>" in _bold("a **b** c **d** e")


class TestCoachNoteFreshness:
    def _cfg(self, tmp_path):
        return SimpleNamespace(home=tmp_path)

    def test_absent_file_is_none(self, tmp_path):
        assert _coach_note(self._cfg(tmp_path), date(2026, 8, 20)) is None

    def test_todays_note_is_fresh(self, tmp_path):
        (tmp_path / "coach.md").write_text("Train hard.", encoding="utf-8")
        note = _coach_note(self._cfg(tmp_path), date.today())
        assert note is not None and note["fresh"] is True

    def test_yesterdays_note_is_not_fresh(self, tmp_path):
        # A note is only today's read on the day it was written — otherwise it would
        # show yesterday's day-number while the live page has moved on.
        from datetime import timedelta
        f = tmp_path / "coach.md"
        f.write_text("Yesterday's advice.", encoding="utf-8")
        y = date.today() - timedelta(days=1)
        ts = __import__("time").mktime(y.timetuple())
        os.utime(f, (ts, ts))
        note = _coach_note(self._cfg(tmp_path), date.today())
        assert note is not None and note["fresh"] is False

    def test_an_old_note_is_read_but_not_fresh(self, tmp_path):
        f = tmp_path / "coach.md"
        f.write_text("Old advice.", encoding="utf-8")
        old = date(2000, 1, 1)
        ts = __import__("time").mktime(old.timetuple())
        os.utime(f, (ts, ts))
        note = _coach_note(self._cfg(tmp_path), date.today())
        assert note is not None and note["fresh"] is False
