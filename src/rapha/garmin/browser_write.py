"""Create and schedule Garmin **workouts** through the logged-in debug Chrome (ADR-013).

The API write path (`write.py`) needs OAuth tokens that Garmin's rate-limited login
(ADR-007) never let us mint. This does the same job — WORKOUTS ONLY — over the CDP
session the pull already uses: it POSTs to Garmin's own `workout-service` from inside
the authenticated page. Like every write in Rapha it is narrow (ADR-001): it creates,
schedules and deletes workouts and nothing else — never an activity, never health data.

It holds no credential of its own; the session lives in the user's browser. `playwright`
is the optional `browser` extra, imported lazily.
"""

from __future__ import annotations

CDP_URL = "http://127.0.0.1:9222"
GC = "https://connect.garmin.com/gc-api"

_CREATE_JS = """
async ([csrf, body]) => {
  const r = await fetch('https://connect.garmin.com/gc-api/workout-service/workout',
    {method:'POST', headers:{'NK':'NT','connect-csrf-token':csrf,'Content-Type':'application/json'},
     credentials:'include', body: JSON.stringify(body)});
  let j=null; try{ j=await r.json(); }catch(e){}
  return {status:r.status, workoutId: j && j.workoutId};
}"""

_SCHEDULE_JS = """
async ([csrf, id, date]) => {
  const r = await fetch('https://connect.garmin.com/gc-api/workout-service/schedule/'+id,
    {method:'POST', headers:{'NK':'NT','connect-csrf-token':csrf,'Content-Type':'application/json'},
     credentials:'include', body: JSON.stringify({date: date})});
  let j=null; try{ j=await r.json(); }catch(e){}
  return {status:r.status, scheduleId: j && (j.workoutScheduleId || j.id)};
}"""

_DELETE_JS = """
async ([csrf, id]) => {
  const r = await fetch('https://connect.garmin.com/gc-api/workout-service/workout/'+id,
    {method:'DELETE', headers:{'NK':'NT','connect-csrf-token':csrf}, credentials:'include'});
  return {status:r.status};
}"""

_LIST_JS = """
async (csrf) => {
  const r = await fetch('https://connect.garmin.com/gc-api/workout-service/workouts?start=0&limit=200',
    {headers:{'NK':'NT','connect-csrf-token':csrf}, credentials:'include'});
  let j=null; try{ j=await r.json(); }catch(e){}
  return (j || []).map(w => ({id: w.workoutId, name: w.workoutName}));
}"""


class BrowserWriteError(RuntimeError):
    """The debug Chrome was unreachable, or Garmin rejected a write."""


def _strip_exercise_names(payload: dict) -> dict:
    """A copy with every step's exerciseName removed — category only.

    Garmin 400s a workout if any step names a variant outside its taxonomy (e.g. a
    bare BICEPS_CURL). The category alone always validates, and the specific movement
    is already in each step's description, so nothing is lost on the watch.
    """
    import copy

    clone = copy.deepcopy(payload)

    def walk(steps):
        for step in steps:
            if "exerciseName" in step:
                step["exerciseName"] = None
            if step.get("type") == "RepeatGroupDTO":
                walk(step.get("workoutSteps", []))

    for seg in clone.get("workoutSegments", []):
        walk(seg.get("workoutSteps", []))
    return clone


def _attach(pw):
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        raise BrowserWriteError(
            f"could not attach to Chrome on {CDP_URL}. Open the debug Chrome and log "
            "into Garmin first (the Data Status tab has a button)."
        ) from e
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return page


def push(cfg, items: list[dict], *, dry_run: bool = True, verbose: bool = True,
         replace_prefix: str | None = None) -> list[dict]:
    """Create each workout and schedule it on its dates.

    ``items`` is ``[{"name","payload","dates":[iso,...]}, ...]``. On a dry run nothing
    is sent — the plan is returned for inspection. If ``replace_prefix`` is given, any
    existing workout whose name starts with it is deleted first, so re-running is
    idempotent (no duplicates, and its schedule entries go with it). Returns one result
    dict per item with the created ``workout_id`` and the ``scheduled`` dates.
    """
    def say(m):
        # The Windows console is cp1252; keep log output ASCII-safe.
        if verbose:
            print(m.encode("ascii", "replace").decode("ascii"), flush=True)

    if dry_run:
        return [{"name": it["name"], "dates": it["dates"], "dry_run": True}
                for it in items]

    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    csrf: dict[str, str] = {}
    with sync_playwright() as pw:
        page = _attach(pw)
        page.on("request", lambda r: csrf.__setitem__(
            "t", r.headers.get("connect-csrf-token") or csrf.get("t")))
        page.goto("https://connect.garmin.com/modern/", wait_until="domcontentloaded",
                  timeout=45000)
        page.wait_for_timeout(3500)
        token = csrf.get("t")
        if not token:
            raise BrowserWriteError("could not read the CSRF token — is Garmin logged in?")

        if replace_prefix:
            existing = page.evaluate(_LIST_JS, token) or []
            stale = [w for w in existing if (w.get("name") or "").startswith(replace_prefix)]
            for w in stale:
                page.evaluate(_DELETE_JS, [token, w["id"]])
                page.wait_for_timeout(120)
            say(f"cleared {len(stale)} existing '{replace_prefix}*' workouts")

        for it in items:
            res: dict = {"name": it["name"], "scheduled": [], "dates": it["dates"]}
            created = page.evaluate(_CREATE_JS, [token, it["payload"]])
            wid = created.get("workoutId")
            if not wid and created.get("status") == 400:
                # A variant name Garmin won't accept — retry with category only.
                created = page.evaluate(_CREATE_JS, [token, _strip_exercise_names(it["payload"])])
                wid = created.get("workoutId")
                if wid:
                    res["names_stripped"] = True
                    say(f"  (retried {it['name']} with category-only exercises)")
            if not wid:
                res["error"] = f"create failed (HTTP {created.get('status')})"
                say(f"  x {it['name']}: {res['error']}")
                results.append(res)
                continue
            res["workout_id"] = wid
            say(f"  created {it['name']}  (id {wid})")
            for d in it["dates"]:
                sched = page.evaluate(_SCHEDULE_JS, [token, wid, d])
                if sched.get("status") in (200, 201, 204):
                    res["scheduled"].append(d)
                else:
                    res.setdefault("schedule_errors", []).append(
                        {"date": d, "status": sched.get("status")})
                page.wait_for_timeout(150)
            say(f"    scheduled {len(res['scheduled'])}/{len(it['dates'])} dates")
            results.append(res)
    return results


def delete_workout(page, token: str, workout_id: int) -> bool:
    """Remove a workout — the cleanup half of the write surface."""
    r = page.evaluate(_DELETE_JS, [token, workout_id])
    return r.get("status") in (200, 204)
