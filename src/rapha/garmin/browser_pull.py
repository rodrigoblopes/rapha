"""Pull Garmin data by attaching to a logged-in Chrome over CDP.

This is the fallback rung that actually worked when the API was IP-blocked and the
Chrome cookies were App-Bound-encrypted: you log into Garmin once in a real Chrome
started with --remote-debugging-port (Cloudflare trusts a human session), and this
*attaches* to it — no automation flags, no password, no cookie decryption. It then
calls Garmin's own `/gc-api` endpoints from inside that authenticated page (session
cookies + the page's CSRF token) and normalises the results into the same canonical
records the API adapter emits (`Source.GARMIN_BROWSER`).

⚠️ Read-only. It fetches; it never posts. And like every ingest path, it holds no
credential of its own — the session lives in the user's browser, not here.

`playwright` is an optional extra (the `extract`/`browser` group), imported lazily,
so the core package still installs with just garminconnect + pdfplumber.
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta

from ..db import Store
from ..models import Activity, DailyMetrics, Source
from .read import activity_from_payload, daily_from_payloads

CDP_URL = "http://127.0.0.1:9222"
GC = "https://connect.garmin.com/gc-api"

# One JS pass: pull activities, then per-day wellness, weight, and the exercise
# sets for each strength activity. Fewer round-trips than driving each call from
# Python. Returns a plain object Playwright hands back as a dict.
_FETCH_JS = r"""
async ({dn, csrf, dates, days_meta}) => {
  const H = {'NK':'NT','connect-csrf-token':csrf,'DI-Backend':'connectapi.garmin.com'};
  const j = async (p) => {
    try { const r = await fetch('https://connect.garmin.com/gc-api'+p,
            {headers:H, credentials:'include'});
          return r.ok ? await r.json() : null; }
    catch(e) { return null; }
  };
  const buf = 'nonSleepBufferMinutes=60';
  const days = [];
  for (const d of dates) {
    days.push({
      date: d,
      summary: await j(`/usersummary-service/usersummary/daily/${dn}?calendarDate=${d}`),
      sleep:   await j(`/wellness-service/wellness/dailySleepData/${dn}?date=${d}&${buf}`),
      hrv:     await j(`/hrv-service/hrv/${d}`),
      maxmet:  await j(`/metrics-service/metrics/maxmet/daily/${d}/${d}`),
    });
  }
  const last = dates[dates.length - 1];
  const weight = await j(`/weight-service/weight/range/${dates[0]}/${last}?includeAll=true`);
  const exerciseSets = {};
  for (const m of days_meta) {
    exerciseSets[m.id] = await j(`/activity-service/activity/${m.id}/exerciseSets`);
  }
  return {days, weight, exerciseSets};
};
"""


def _connect(pw, page_ready):
    browser = pw.chromium.connect_over_cdp(CDP_URL)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return browser, page


def pull(cfg, *, activity_days: int = 365, metric_days: int = 45, verbose: bool = True):
    """Attach to the debug Chrome, pull everything, and ingest. Returns a summary."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright is not installed. `pip install playwright` (it's in the "
            "'browser' extra), then start Chrome with --remote-debugging-port=9222 "
            "and log into Garmin."
        ) from e

    def say(m):
        if verbose:
            print(m, flush=True)

    csrf: dict[str, str] = {}
    activities_raw: list = []
    bundle: dict = {}

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            raise RuntimeError(
                f"could not attach to Chrome on {CDP_URL}. Start Chrome with "
                "--remote-debugging-port=9222 and log into Garmin first."
            ) from e
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req):
            t = req.headers.get("connect-csrf-token")
            if t:
                csrf["token"] = t

        def on_response(resp):
            if "activitylist-service/activities/search" in resp.url:
                try:
                    data = resp.json()
                    if isinstance(data, list):
                        activities_raw.extend(data)
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        say("attaching and loading activities...")
        page.goto("https://connect.garmin.com/modern/activities",
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)

        if not csrf.get("token"):
            raise RuntimeError("could not read the CSRF token — is the Garmin page "
                               "logged in?")
        token = csrf["token"]

        display_name = page.evaluate(
            """async (t) => {
                const r = await fetch('https://connect.garmin.com/gc-api/userprofile-service/socialProfile',
                    {headers:{'NK':'NT','connect-csrf-token':t}, credentials:'include'});
                const j = await r.json(); return j.displayName;
            }""", token)

        # A fuller activity list (the page loads only ~20).
        more = page.evaluate(
            """async (t) => {
                const r = await fetch('https://connect.garmin.com/gc-api/activitylist-service/activities/search/activities?limit=100&start=0',
                    {headers:{'NK':'NT','connect-csrf-token':t}, credentials:'include'});
                return r.ok ? await r.json() : [];
            }""", token)
        if isinstance(more, list) and more:
            activities_raw[:] = more

        today = date.today()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(metric_days)]
        strength_ids = [
            a["activityId"] for a in activities_raw
            if (a.get("activityType") or {}).get("typeKey", "") in
            ("strength_training", "indoor_cardio") and a.get("activityId")
        ][:20]
        days_meta = [{"id": i} for i in strength_ids]

        say(f"pulling {metric_days} days of wellness + {len(strength_ids)} exercise sets...")
        bundle = page.evaluate(_FETCH_JS, {
            "dn": display_name, "csrf": token, "dates": dates, "days_meta": days_meta,
        })

    return _ingest(cfg, activities_raw, bundle, activity_days, say)


def _ingest(cfg, activities_raw, bundle, activity_days, say) -> dict:
    # Activities. `activity_from_payload` tags them GARMIN_API; rebuild each with
    # the browser source. Activity is a frozen slots dataclass, so `replace`, not
    # `__dict__`. Dedupe by activity_id first: the page's own fetch and the
    # intercepted response can surface the same activity twice, and window-replace
    # inserts a batch in one shot — a repeated id trips the PRIMARY KEY.
    from dataclasses import replace

    by_id: dict[str, Activity] = {}
    for r in activities_raw:
        a = activity_from_payload(r)
        if a:
            by_id[a.activity_id] = replace(a, source=Source.GARMIN_BROWSER)
    acts: list[Activity] = list(by_id.values())

    # Daily metrics
    weights = _weights_by_date(bundle.get("weight") or {})
    days: list[DailyMetrics] = []
    for d in bundle.get("days", []):
        try:
            on = date.fromisoformat(d["date"])
        except Exception:
            continue
        mm = d.get("maxmet")
        if isinstance(mm, list):
            mm = mm[0] if mm else None
        days.append(daily_from_payloads(on, d.get("summary"), d.get("sleep"),
                                        d.get("hrv"), mm, weights.get(on)))
        days[-1] = replace(days[-1], source=Source.GARMIN_BROWSER)

    with Store(cfg.db_path) as store:
        if acts:
            store.ingest_activities(min(a.start.date() for a in acts),
                                    max(a.start.date() for a in acts), acts)
        if days:
            store.ingest_daily(min(d.on for d in days), max(d.on for d in days), days)

    # Exercise sets -> stored for progression
    n_sets = _store_exercise_sets(cfg, activities_raw, bundle.get("exerciseSets") or {})

    measured = sum(1 for d in days if d.calories_total is not None)
    summary = {
        "activities": len(acts),
        "days": len(days),
        "measured_tdee_days": measured,
        "exercise_set_rows": n_sets,
    }
    say(f"ingested {len(acts)} activities, {len(days)} days "
        f"({measured} with TDEE), {n_sets} exercise-set rows")
    return summary


def _weights_by_date(weight_json: dict) -> dict[date, int]:
    out: dict[date, int] = {}
    for d in (weight_json.get("dailyWeightSummaries") or []):
        stamp = d.get("summaryDate")
        w = (d.get("latestWeight") or {}).get("weight")  # grams, sometimes a float
        if stamp and w:
            with contextlib.suppress(ValueError, TypeError):
                out[date.fromisoformat(stamp)] = round(w)
    return out


def _store_exercise_sets(cfg, activities_raw, sets_by_id: dict) -> int:
    """Persist per-exercise sets (reps + weight) so progression can be tracked."""
    from .exercise_store import ExerciseStore

    by_id = {a.get("activityId"): a for a in activities_raw}
    rows = 0
    with ExerciseStore(cfg.db_path) as es:
        for aid, payload in sets_by_id.items():
            if not payload:
                continue
            meta = by_id.get(int(aid)) or by_id.get(aid) or {}
            start = str(meta.get("startTimeLocal", ""))[:10]
            try:
                on = date.fromisoformat(start) if start else None
            except Exception:
                on = None
            if on is None:
                continue
            rows += es.record_activity(int(aid), on, payload)
    return rows
