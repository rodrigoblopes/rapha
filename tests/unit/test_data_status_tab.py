"""The Data Status tab renders the real element IDs its JS drives.

Regression guard: the value slots were once passed as raw HTML into a helper that
HTML-escapes, so the IDs never became real elements (they showed as literal
'<span id="lastpull">' text and the JS could never fill them). These assertions pin
that the IDs the tab's JS looks up exist as genuine attributes.
"""

from __future__ import annotations

from rapha.dashboard import portal

# Every id the Data Status JS resolves with getElementById.
_JS_IDS = ["statusdot", "statustext", "statussub", "lastpull", "pullage",
           "chromestate", "launchstatus", "pullnowstatus"]


def _tab(**ds):
    return portal._data_status_tab({"data_status": ds})


def test_the_value_slots_are_real_elements_not_escaped_text():
    html = _tab(fresh=True, last_pull_at="2026-08-14T10:19:44", age_seconds=23,
                fresh_minutes=60, summary={"activities": 100})
    assert '<div class="n" id="lastpull">' in html
    assert '<div class="n" id="pullage">' in html
    # the bug looked like this — an escaped tag rendered as text
    assert "&lt;span id=" not in html


def test_every_js_target_id_is_present():
    html = _tab(fresh=False, age_seconds=None, fresh_minutes=60)
    for element_id in _JS_IDS:
        assert f'id="{element_id}"' in html, f"missing #{element_id}"


def test_the_action_buttons_are_wired():
    html = _tab(fresh=True)
    assert "forcePull(this)" in html      # Pull now
    assert "launchChrome(this)" in html   # Open Chrome on Garmin login


def test_it_renders_without_a_data_status_section():
    # A briefing with no data_status must still produce a tab, not raise.
    html = portal._data_status_tab({})
    assert 'id="datastatus"' in html


def test_tab_navigation_is_an_underline_not_a_pill():
    css = portal.CSS
    # the redesign uses an underline nav: the active tab carries an accent bottom border
    assert "nav button:hover:not(.on)" in css
    assert "nav button.on{color:var(--ink);border-bottom-color:var(--accent)}" in css


def test_data_status_tab_has_its_own_health_colours():
    css = portal.CSS
    # Data Status keeps its own health colours: ok = accent2 (blue), bad = --bad
    assert "nav button.statusok" in css and "var(--accent2)" in css
    assert "nav button.statusbad" in css and "var(--bad)" in css
