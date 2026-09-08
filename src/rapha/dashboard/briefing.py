"""Assemble the full coaching briefing from the store and the extracted protocol.

This is the layer between the pure rules and the portal: it pulls the real data,
runs the rules over it, and returns one structured dict the portal (and Claude)
can read. It performs I/O — reading SQLite, the protocol JSON, the state file — but
delegates every judgment to the pure functions in `rules/`.

⚠️ It reads SQLite and files only. It never imports `rapha.garmin` and holds no
credential (ADR-001) — it is safe for the portal to depend on.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any

from ..db import Store
from ..protocol import catalog
from ..rules import cycle
from ..rules.energy import Direction, recompose_direction
from ..rules.recovery import assess_recovery
from ..units import Grams, Kcal

MEAL_LABELS = {
    1: "Breakfast (post-workout)",
    2: "Lunch",
    3: "Afternoon",
    4: "Dinner",
    5: "Supper",
}


def _state(cfg) -> dict:
    path = cfg.home / "state.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _bodyfat(cfg, st, measurements=None) -> tuple[int | None, str]:
    """Best body-fat estimate (×10) and its source.

    Prefer the Navy formula from the latest tape waist+neck — objective and
    repeatable — over the one-off photo estimate, but keep the photo number in the
    note when the two disagree, because they carry different errors.
    """
    from ..rules.measurements import navy_bodyfat_pct_x10

    tape = _resolve_tape(measurements or [], st)
    height_mm = cfg.athlete_height_mm or 1770
    if tape.get("waist_mm") and tape.get("neck_mm"):
        navy = navy_bodyfat_pct_x10(tape["waist_mm"], tape["neck_mm"], height_mm,
                                    sex=cfg.athlete_sex)
        if navy is not None:
            photo = st.get("bodyfat_pct_x10")
            extra = (f" (photo estimate read ~{photo / 10:.0f}%; the tape is the "
                     "repeatable measure)") if photo else ""
            return navy, f"Navy formula from tape, {tape.get('on', '')}{extra}"
    return st.get("bodyfat_pct_x10"), st.get("bodyfat_source", "")


#: Circumference fields carried on a Measurement, in display order.
_CIRC_ATTRS = ["waist", "neck", "hip", "chest", "arm", "thigh", "shoulders", "calf"]


def _resolve_tape(measurements, st) -> dict:
    """The latest circumference set, in millimetres, from the DB (state.json legacy
    as a last resort). Wingspan is structural, so the most recent non-null wins."""
    latest = next(
        (m for m in reversed(measurements)
         if any(getattr(m, a) for a in _CIRC_ATTRS)),
        None,
    )
    wingspan = next((m.wingspan for m in reversed(measurements) if m.wingspan), None)

    if latest is None:
        legacy = st.get("measurements") or {}
        if not legacy.get("neck_mm"):
            return {}
        return {"on": legacy.get("measured_on", ""),
                "waist_mm": legacy.get("waist_mm"), "neck_mm": legacy.get("neck_mm"),
                "wingspan_mm": legacy.get("wingspan_mm")}

    def mv(q):
        return q.value if q else None

    out = {"on": latest.on.isoformat(), "notes": latest.notes,
           "wingspan_mm": mv(wingspan)}
    for a in _CIRC_ATTRS:
        out[f"{a}_mm"] = mv(getattr(latest, a))
    return out


def _fmt(t: datetime) -> str:
    hour12 = t.hour % 12 or 12          # cross-platform 12-hour, no %-I
    return f"{hour12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _meal_times(anchor: str, n: int, *, session_min: int = 60) -> list[str]:
    """Meal clock times, anchored to when training actually *ends*.

    The anchor is when training STARTS; the post-workout shake lands ~10 min after
    the session finishes (start + session_min + 10), not after the start — the bug
    that put a "post-workout" shake mid-workout. Breakfast follows ~50 min later,
    then the solid meals space across the day.
    """
    try:
        h, m = (int(x) for x in anchor.split(":"))
    except ValueError:
        h, m = 5, 0
    start = datetime.combine(date.today(), time(h, m))
    shake = start + timedelta(minutes=session_min + 10)   # post-workout
    breakfast = shake + timedelta(minutes=50)
    # Fixed clock times for the rest of the day, independent of the anchor.
    fixed = [time(12, 0), time(15, 30), time(18, 30), time(20, 30)]
    times = [shake, breakfast] + [datetime.combine(date.today(), t) for t in fixed]
    return [_fmt(t) for t in times[:n]]


def _portion_text(p: dict) -> str:
    amt = p.get("amount")
    g = amt["value"] if isinstance(amt, dict) else amt
    if g:
        return f"{g} g {p['food']}"
    if p.get("unlimited"):
        return f"{p['food']} (à vontade)"
    return p["food"]


def _series(days, attr, transform=lambda v: v):
    out = []
    for d in days:
        v = getattr(d, attr)
        if v is not None:
            out.append((d.on.isoformat(), transform(v)))
    return out


def build(cfg, *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    st = _state(cfg)
    programmes, diets = catalog.load(cfg.protocol_dir)
    foods = catalog.load_foods(cfg.protocol_dir)

    days: list = []
    acts: list = []
    weight_hist: list = []
    measurements: list = []
    if cfg.db_path.is_file():
        with Store(cfg.db_path) as store:
            # Wide enough for the 1Y/All performance windows; the recovery and meal
            # rules filter down to their own short windows internally.
            days = store.daily_between(today - timedelta(days=400), today)
            acts = store.activities_between(today - timedelta(days=120), today)
            weight_hist = store.weight_history()
            measurements = store.measurements()

    briefing: dict[str, Any] = {
        "generated": today.isoformat(),
        "athlete": {
            "weight_kg": (days[-1].weight.value / 1000
                          if days and days[-1].weight else 85),
            "height_cm": (cfg.athlete_height_mm / 10) if cfg.athlete_height_mm else 177,
            "bodyfat_pct": (st.get("bodyfat_pct_x10", 0) / 10) or None,
            "bodyfat_source": st.get("bodyfat_source"),
            "somatotype": st.get("somatotype"),
        },
    }

    briefing["overview"] = _overview(days, acts, programmes, st, today)
    briefing["vitals"] = _vitals(days)
    briefing["training"] = _training(cfg, programmes, st, today)
    _apply_autoregulation(briefing)
    briefing["meals"] = _meals(days, diets, foods, cfg, st, today, measurements)
    briefing["performance"] = _performance(days, acts, today, cfg.home)
    briefing["volume"] = _volume(cfg, acts, programmes, st, today)
    briefing["progression"] = _progression(cfg)
    briefing["progress"] = _progress(days, st, cfg, today, weight_hist, measurements)
    briefing["data_status"] = _data_status(cfg)
    briefing["exams"] = _exams(cfg, today)
    briefing["session"] = _session_block(cfg, briefing, today)
    briefing["coach"] = _coach(cfg, briefing, today)
    return briefing


def _data_status(cfg) -> dict:
    """Pull freshness for the Data Status tab's first paint.

    The build stays fast and side-effect-free, so it does not probe the debug port
    here — the live ``GET /pull-status`` endpoint does that, and the tab's JS polls it.
    """
    from ..pull_status import pull_status

    return pull_status(cfg.home, check_chrome=False)


def _coach_note(cfg, today) -> dict | None:
    """A Claude-authored daily coach note, if one has been written to %RAPHA_HOME%/coach.md.

    The templated paragraphs are always computed as the fresh fallback; this lets a note
    written *from the same briefing numbers* (the way the photo analysis already works)
    take the lead when it is current. Freshness is the file's own date — a note more than
    a day old is shown, but flagged, never presented as today's read.
    """
    from datetime import datetime

    path = cfg.home / "coach.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    written = datetime.fromtimestamp(path.stat().st_mtime).date()
    # Fresh only on the day it was written. The note is hand-authored (nothing in the
    # hourly refresh regenerates it), so a day-old note would otherwise keep showing
    # yesterday's day-number and numbers while the rest of the page has moved on; when
    # stale it yields to the always-fresh templated coach.
    return {"text": text, "written": written.isoformat(),
            "fresh": written == today}


def _session_block(cfg, briefing, today) -> dict:
    """Workout-state view for the coach card: before the session, what to aim for;
    after it, a review of what was actually lifted against the plan.

    'Done' means today's strength sets have been logged (they land on the next Garmin
    pull). Until then it reads as still-to-do and shows the aims.
    """
    tr = briefing.get("training", {})
    if not tr.get("available"):
        return {"state": "none"}
    if tr.get("rest"):
        return {"state": "rest", "focus": tr.get("focus", "Rest day")}

    exercises = tr.get("exercises", [])
    adj = tr.get("adjustment", {}) or {}
    planned = []
    for ex in exercises:
        c = ex.get("call") or {}
        if c.get("garmin") and c.get("target_reps"):
            planned.append({
                "name": ex["name"], "garmin": c["garmin"],
                "target_reps": c["target_reps"],
                "expected_kg_x10": (round(c["last_kg"] * 10)
                                    if c.get("last_kg") is not None else None),
            })

    logged: dict = {}
    if cfg.db_path.is_file():
        from ..garmin.exercise_store import ExerciseStore

        with ExerciseStore(cfg.db_path) as es:
            logged = es.sets_on(today)
    done = bool(logged)

    if not done:
        aims = []
        for ex in exercises:
            c = ex.get("call") or {}
            dec = c.get("decision")
            if dec == "progress" and c.get("suggested_kg") is not None and not c.get("gated"):
                aims.append(f"{ex['name'].title()} — go for {c['suggested_kg']:g} kg")
            elif dec == "progress" and c.get("gated") and c.get("last_kg") is not None:
                aims.append(f"{ex['name'].title()} — hold {c['last_kg']:g} kg (recovery)")
            elif dec == "hold" and c.get("last_kg") is not None:
                aims.append(f"{ex['name'].title()} — hold {c['last_kg']:g} kg, own the reps")
            elif dec == "establish":
                aims.append(f"{ex['name'].title()} — find your working load")
        return {
            "state": "todo",
            "focus": tr.get("focus", ""),
            "directive": adj.get("load_directive"),
            "reps_in_reserve": adj.get("reps_in_reserve"),
            "headline": adj.get("headline"),
            "aims": aims[:8],
        }

    from ..rules.session_review import review_session

    review = review_session(planned, logged,
                            recovery_status=briefing["overview"]["recovery"]["status"])
    return {
        "state": "done",
        "focus": tr.get("focus", ""),
        "tonnage_kg": review.tonnage_kg,
        "hard_sets": review.hard_sets,
        "strong": review.strong,
        "work_on": review.work_on,
        "advice": review.advice,
    }


def _coach(cfg, b: dict, today: date) -> dict:
    """A plain-language daily read, written the way a trainer would talk to you.

    Everything on the dashboard is a number; this turns the numbers that matter
    *today* into sentences someone with no sports-science background can act on. It
    is generated deterministically from the same computed state (the portal rebuilds
    on a timer, with no Claude in the loop), so it stays observational — it explains
    what the data shows and what the plan calls for, and leaves the call to you.
    """
    ov = b["overview"]
    rec = ov["recovery"]
    meals = b.get("meals", {})
    tr = b.get("training", {})
    wv = b.get("progress", {}).get("weight_view", {})
    paras: list[str] = []

    status = rec["status"]
    if status == "green":
        paras.append(
            "You're well recovered today. The four overnight signals your watch tracks — "
            "heart-rate variability, resting pulse, stress and sleep — are all at or better "
            "than your recent normal. That's your body telling you it's ready, so today is a "
            "good day to train hard and chase your top sets."
        )
    elif status == "amber":
        off = [s["label"].lower() for s in rec["signals"] if s["good"] is False]
        names = " and ".join(off) if off else "one signal"
        paras.append(
            f"You're mostly recovered, but your {names} is off its usual mark this morning. "
            "That's not a red light — it just means train as planned, but leave a rep in the "
            "tank rather than grinding every set to failure."
        )
    else:
        paras.append(
            "Several of your overnight recovery signals are down today. Your body builds the "
            "muscle you trained on the rest days, not the gym days — so a lighter session or a "
            "full rest now will likely make the rest of the week's training better, not worse."
        )

    rate = wv.get("rate_kg_per_week")
    if rate is not None:
        if rate <= -0.2:
            paras.append(
                f"On the scale, you're trending down about {abs(rate)} kg a week since you "
                "started. That's a controlled pace — fast enough to see fat come off, slow "
                "enough to keep the muscle you're working for. Day-to-day weight is mostly "
                "water; the dotted line on the Progress tab is the direction that counts."
            )
        elif rate >= 0.2:
            paras.append(
                f"On the scale, you're trending up about {rate} kg a week. If fat loss is the "
                "aim right now, that's the number to keep an eye on — it usually means the food "
                "is landing a little above what you're burning."
            )
        else:
            paras.append(
                "Your weight is holding roughly steady. In a body recomposition that's normal "
                "and not a worry — the tape measure and the mirror show the change before the "
                "scale does."
            )

    tgt, prot = meals.get("target_kcal"), meals.get("protein_g")
    if tgt:
        paras.append(
            f"On the plate today: aim for around {tgt} calories, and the one number not to miss "
            f"is {prot} grams of protein. Protein is what protects your muscle while you're "
            "eating in a deficit — hit that and the rest of the day has room to flex."
        )

    if tr.get("rest"):
        paras.append(
            "No lifting session is scheduled today — it's a planned rest day, which is when the "
            "work you've already put in actually turns into muscle."
        )
    elif tr.get("focus"):
        paras.append(
            f"Today's session is {tr['focus'].lower()} — {len(tr.get('exercises', []))} "
            "exercises, laid out on the Training tab and ready to send to your watch."
        )

    return {"day": ov["day_of_60"], "status": status, "paragraphs": paras,
            "authored": _coach_note(cfg, today)}


def _recent_weight(days) -> Grams | None:
    for d in reversed(days):
        if d.weight:
            return d.weight
    return None


def _overview(days, acts, programmes, st, today) -> dict:
    recovery = assess_recovery(days, today=today)
    start = date.fromisoformat(st["protocol_start"]) if st.get("protocol_start") else today
    sheet = _live_sheet(programmes, st, today)
    cyc_start = _sheet_cycle_start(st, sheet, start)
    pos = cycle.resolve(sheet, start=cyc_start, today=today) if sheet else None
    return {
        "day_of_60": (today - start).days + 1,
        "week": _protocol_week(st, today),
        "sheet": sheet.get("source_file", "") if sheet else "",
        "sheet_number": sheet.get("sheet_number") if sheet else None,
        "sheet_switch": _sheet_switch(programmes, st, today),
        "focus": (pos.note if pos and not pos.is_rest else "Rest day") if pos else "—",
        "is_rest": bool(pos and pos.is_rest),
        "recovery": {
            "status": recovery.status.value,
            "headline": recovery.headline,
            "signals": [
                {"label": s.label, "latest": s.latest, "baseline": s.baseline,
                 "good": s.good, "note": s.note,
                 "higher_is_better": s.higher_is_better, "recent": s.recent}
                for s in recovery.signals
            ],
        },
    }


def _sheet_weeks(weeks_field) -> set[int]:
    """The protocol weeks a sheet covers, from its `weeks` label.

    Cariani's Intermediário sheets state their weeks explicitly — "1ª,2ª,3ª E 4ª
    SEMANAS" -> {1,2,3,4}, "5ª,6ª,7ª E 8ª SEMANAS" -> {5,6,7,8} — so the number that
    matters is just the digits in the label.
    """
    import re

    return {int(n) for n in re.findall(r"\d+", weeks_field or "")}


def _protocol_week(st, today) -> int | None:
    start = st.get("protocol_start")
    if not start:
        return None
    return max(1, (today - date.fromisoformat(start)).days // 7 + 1)


def _sheet_cycle_start(st, sheet, protocol_start):
    """The date a sheet's rotation restarts from — its first week, not day 1 of 60.

    Sheet 02 covers weeks 5–8, so its cycle begins on the Monday-equivalent of week 5,
    not on the protocol start. Anchoring the cycle here makes "today's session" correct
    the moment the sheet goes live, instead of continuing Sheet 01's count.
    """
    weeks = _sheet_weeks(sheet.get("weeks", "")) if sheet else set()
    first_week = min(weeks) if weeks else 1
    return protocol_start + timedelta(days=(first_week - 1) * 7)


def _live_sheet(programmes, st, today=None) -> dict | None:
    """The sheet for *this* week of the protocol, not just the first one on file.

    Sheet 01 runs weeks 1–4, Sheet 02 weeks 5–8; the app used to always serve the
    first, so it never advanced you. Now it picks the sheet whose week-range covers
    the current protocol week (falling back to the latest sheet that has already
    started, then to the first sheet, then to any sheet with sessions).
    """
    today = today or date.today()
    level = st.get("level", "INTERMEDIÁRIO")
    key = level.split()[0][:6].upper()
    matching = [p for p in programmes if key in p["level"].upper() and p.get("sessions")]
    if not matching:
        return next((p for p in programmes if p.get("sessions")), None)

    week = _protocol_week(st, today)
    if week is not None:
        for p in matching:  # a sheet whose range contains this week (list order wins)
            if week in _sheet_weeks(p.get("weeks", "")):
                return p
        started = [(max(_sheet_weeks(p.get("weeks", "")), default=0), p) for p in matching]
        started = [(mx, p) for mx, p in started if 0 < mx <= week]
        if started:  # else the most-recent sheet that has already begun
            return max(started, key=lambda t: t[0])[1]
    return matching[0]


def _sheet_switch(programmes, st, today) -> dict | None:
    """When the *next* sheet begins, for an early heads-up. None if no switch ahead."""
    week = _protocol_week(st, today)
    current = _live_sheet(programmes, st, today)
    if week is None or current is None:
        return None
    start = date.fromisoformat(st["protocol_start"])
    key = st.get("level", "INTERMEDIÁRIO").split()[0][:6].upper()
    matching = [p for p in programmes if key in p["level"].upper() and p.get("sessions")]
    cur_max = max(_sheet_weeks(current.get("weeks", "")), default=0)
    # the next sheet whose first week is beyond the current sheet's last week
    upcoming = None
    for p in matching:
        weeks = _sheet_weeks(p.get("weeks", ""))
        first = min(weeks, default=0)
        if first > cur_max and (
            upcoming is None
            or first < min(_sheet_weeks(upcoming.get("weeks", "")), default=99)
        ):
            upcoming = p
    if not upcoming:
        return None
    next_first = min(_sheet_weeks(upcoming.get("weeks", "")))
    switch_date = start + timedelta(days=(next_first - 1) * 7)
    days_until = (switch_date - today).days
    return {
        "sheet": upcoming.get("sheet_number"),
        "file": upcoming.get("source_file", ""),
        "starts_week": next_first,
        "starts_on": switch_date.isoformat(),
        "days_until": days_until,
    }


def _session_progression(cfg, session) -> tuple[dict, dict]:
    """Per-exercise double-progression calls for one session, read from real history.

    Returns ``(calls, loads)``: ``calls`` maps an exercise name to a serialised
    :class:`~rapha.rules.progression.NextSessionCall`; ``loads`` maps a Garmin
    exercise name to the suggested load in grams, for pre-filling the watch. Empty
    when there is no set history yet — a new athlete simply establishes loads first.
    """
    from ..mapping.exercises import try_map
    from ..rules.progression import call_from_history

    calls: dict = {}
    loads: dict = {}
    if not cfg.db_path.is_file():
        return calls, loads

    from ..garmin.exercise_store import ExerciseStore

    with ExerciseStore(cfg.db_path) as es:
        for ex in session.get("exercises", []):
            sets = ex.get("sets") or []
            rep_targets = [s.get("reps") for s in sets if isinstance(s.get("reps"), int)]
            if not rep_targets:            # a timed hold — no load progression
                continue
            target = min(rep_targets)      # the heaviest set's rep target
            gm = try_map(ex["name"])
            if not gm or not gm.name:
                continue
            dumbbell = "DUMBBELL" in (gm.name or "") or "DUMBBELL" in (gm.category or "")
            last = es.last_session_sets(gm.name, weighted_only=True)
            call = call_from_history(target, last, using_dumbbells=dumbbell)
            calls[ex["name"]] = {
                "decision": call.decision.value,
                "garmin": gm.name,
                "target_reps": call.target_reps,
                "last_kg": (call.last_weight_kg_x10 / 10
                            if call.last_weight_kg_x10 is not None else None),
                "suggested_kg": (call.suggested_kg_x10 / 10
                                 if call.suggested_kg_x10 is not None else None),
                "bodyweight": call.bodyweight,
                "reasoning": call.reasoning,
            }
            if call.suggested_kg_x10 is not None:
                loads[gm.name] = call.suggested_kg_x10 * 100   # kg×10 -> grams
    return calls, loads


def _training(cfg, programmes, st, today) -> dict:
    from ..garmin.workout import RepStrategy, build_workout
    from ..mapping.exercises import try_map
    from ..rules.methods import method_cue

    sheet = _live_sheet(programmes, st, today)
    start = date.fromisoformat(st["protocol_start"]) if st.get("protocol_start") else today
    if not sheet:
        return {"available": False}

    # Completion-based, not calendar-based: the live session is the next one you have
    # NOT done, so a missed day is picked up rather than skipped, and a day you actually
    # trained never reads as "rest". Rest is a suggestion (below), never a block.
    cyc_start = _sheet_cycle_start(st, sheet, start)
    seq = cycle.training_sequence(sheet)
    trained_today = False
    rest_suggested = False
    streak = 0
    catch_up = False

    # Which Garmin exercises each training day is made of — so a logged session can be
    # matched back to the day it was (you might train the days out of order, or catch up
    # a missed one).
    day_names: dict[int, set] = {}
    for s in sheet["sessions"]:
        names = {gm.name for ex in (s.get("exercises") or [])
                 if (gm := try_map(ex["name"])) and gm.name}
        if names:
            day_names[s["day"]] = names

    def _match(logged: set) -> int | None:
        best, score = None, 0
        for d, names in day_names.items():
            hit = len(names & logged)
            if hit > score:
                best, score = d, hit
        return best

    by_date: dict = {}    # date -> set of logged Garmin exercise names, since block start
    if cfg.db_path.is_file() and day_names:
        from ..garmin.exercise_store import ExerciseStore

        with ExerciseStore(cfg.db_path) as es:
            for r in es.all_sets():
                if r.name and r.on >= cyc_start:
                    by_date.setdefault(r.on, set()).add(r.name)

    trained_today = today in by_date
    last_done: dict[int, date] = {}          # training day -> latest date it was done
    for d in sorted(by_date):
        md = _match(by_date[d])
        if md is not None:
            last_done[md] = d

    if not seq:                               # unparsed rotation — calendar fallback
        pos = cycle.resolve(sheet, start=cyc_start, today=today)
        if pos.is_rest or pos.session_day is None:
            return {"available": True, "rest": True, "focus": "Rest day",
                    "note": pos.note, "level": sheet["level"]}
        session_day = pos.session_day
    elif trained_today and (md := _match(by_date[today])) is not None:
        session_day = md                      # show exactly the session you did today
    else:
        # the session you owe: a never-done day (in cycle order), else the one done
        # longest ago — so a missed session surfaces instead of being skipped.
        never = [d for d in seq if d not in last_done]
        session_day = never[0] if never else min(last_done, key=last_done.get)
        # a catch-up = a due day that is out of its usual turn (missed earlier)
        catch_up = bool(never) and never[0] != seq[len(last_done) % len(seq)]

    probe = today if today in by_date else today - timedelta(days=1)
    while probe in by_date:
        streak += 1
        probe -= timedelta(days=1)
    rest_suggested = not trained_today and bool(seq) and streak >= len(seq)
    position = {"done": len(last_done), "of": len(seq)}

    session = next((s for s in sheet["sessions"] if s["day"] == session_day), None)
    if not session:
        return {"available": True, "rest": False, "focus": "—", "exercises": []}

    exercises = []
    garmin_steps = []
    calls, load_targets = _session_progression(cfg, session)
    for ex in session["exercises"]:
        sets = ex.get("sets") or []
        reps = [s.get("reps") for s in sets]
        durs = [s.get("duration") for s in sets]
        rest = ex.get("rest")
        if all(r is not None for r in reps) and reps:
            scheme = " / ".join(str(r) for r in reps)
        elif any(d for d in durs):
            secs = next((d["value"] if isinstance(d, dict) else d for d in durs if d), 0)
            scheme = f"{len(sets)} × {secs}s hold"
        else:
            scheme = f"{len(sets)} sets"
        exercises.append({
            "name": ex["name"],
            "sets": len(sets),
            "scheme": scheme,
            "rest_s": (rest["value"] if isinstance(rest, dict) else rest),
            "issues": ex.get("issues") or [],
            "call": calls.get(ex["name"]),
            "method": (lambda mc: {"label": mc[0], "cue": mc[1]} if mc else None)(
                method_cue(ex["name"])),
        })
        gm = try_map(ex["name"])
        if gm:
            garmin_steps.append({
                "exercise": ex["name"],
                "garmin_name": gm.name or gm.category,
                "category": gm.category,
                "scheme": scheme,
            })

    workout_name = f"P60D {sheet['level']} D{session['day']} — {session['focus']}"[:60]
    built = build_workout(session, name=workout_name, strategy=RepStrategy.REPS)
    unmapped = sorted(set(built.unmapped))

    return {
        "available": True,
        "rest": False,
        "level": sheet["level"],
        "day": session["day"],
        "focus": session["focus"],
        "trained_today": trained_today,
        "position": position,
        "streak_days": streak,
        "rest_suggested": rest_suggested,
        "catch_up": catch_up,
        "exercises": exercises,
        "progression": (
            "Double progression (Módulo 17): the reps are fixed. Find the load that "
            "hits the target with clean form; add the smallest plate only when the "
            "target comes easily; hold the weight when form breaks before the target."
        ),
        "garmin": {
            "workout_name": workout_name,
            "steps": garmin_steps,
            "unmapped": unmapped,
            "loads_g": load_targets,
        },
    }


def _meals(days, diets, foods, cfg, st, today, measurements=None) -> dict:
    from ..rules.energy import measured_tdee
    from ..rules.targeted_menu import build_targeted_day
    from ..units import Rounding, apply_bps

    weight = _recent_weight(days) or Grams(85_000)
    tdee = measured_tdee(days, window_days=cfg.tdee_window_days, today=today) or Kcal(2450)
    target = Kcal(tdee.value - apply_bps(tdee, cfg.deficit_bps, Rounding.DOWN).value)
    protein_g = weight.value * cfg.protein_g_per_kg_x10 // 10000

    bf10, _ = _bodyfat(cfg, st, measurements)
    direction, why = recompose_direction(bf10)

    # Solve real portions to hit the target exactly, rather than costing a fixed
    # model with fuzzy matches.
    day = build_targeted_day(target, Grams(protein_g))
    anchor = st.get("train_anchor", "05:00")
    times = _meal_times(anchor, len(day.meals),
                        session_min=int(st.get("train_duration_min", 60)))
    meals = [
        {
            "number": m.number,
            "label": m.label,
            "time": times[i] if i < len(times) else "",
            "kcal": m.kcal,
            "protein_g": m.protein_g,
            "free": m.free,
            "items": [
                {"grams": it.grams, "food": it.name_en, "kcal": it.kcal,
                 "protein_g": it.protein_dg // 10}
                for it in m.items
            ],
        }
        for i, m in enumerate(day.meals)
    ]

    split_p = round(day.total_protein.value * 4 / day.total_kcal.value * 100)
    split_c = round(day.total_carb.value * 4 / day.total_kcal.value * 100)
    split_f = round(day.total_fat.value * 9 / day.total_kcal.value * 100)

    return {
        "tdee_kcal": tdee.value,
        "target_kcal": target.value,
        "actual_kcal": day.total_kcal.value,
        "protein_g": protein_g,
        "actual_protein_g": day.total_protein.value,
        "carb_g": day.total_carb.value,
        "fat_g": day.total_fat.value,
        "split": f"{split_p}% P · {split_c}% C · {split_f}% F",
        "deficit_pct": cfg.deficit_bps / 100,
        "direction": direction.value,
        "direction_why": why,
        "is_cut": direction is Direction.CUT,
        "meals": meals,
        "supplements": [
            {"name": s.name, "dose": s.dose, "when": s.when, "source": s.source}
            for s in day.supplements
        ],
        "principles": [
            f"Protein is the anchor: {day.total_protein.value} g today protects muscle "
            "while you strip fat — the one number not to miss.",
            "Carbs cluster around training: your two biggest carb meals are breakfast "
            "(post-workout) and lunch.",
            "Vegetables and salad are free (à vontade) — volume keeps you full in the deficit.",
            "Portions are weighable (nearest 5 g) and swap like-for-like: any lean protein "
            "for another, any starch for another of equal grams.",
            "Coffee is free, black or with sweetener.",
        ],
    }


def _intraday(cfg_home) -> dict:
    """The latest-day heart-rate samples the pull cached, if any."""
    path = cfg_home / "data" / "cache" / "intraday.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _performance(days, acts, today, cfg_home) -> dict:
    strength = [a for a in acts if "strength" in a.kind or "fitness" in a.kind]
    runs = [a for a in acts if "run" in a.kind or "cycl" in a.kind or "swim" in a.kind]
    times = sorted(f"{a.start.hour:02d}:{a.start.minute:02d}" for a in strength)

    def latest(attr, tf=lambda v: v):
        s = _series(days, attr, tf)
        return s[-1][1] if s else None

    return {
        "tdee_series": _series(days, "calories_total", lambda k: k.value),
        "rhr_series": _series(days, "resting_hr"),
        "hrv_series": _series(days, "hrv_ms"),
        "stress_series": _series(days, "stress_avg"),
        "sleep_series": _series(days, "sleep", lambda s: round(s.value / 3600, 1)),
        "steps_series": _series(days, "steps"),
        "intraday": _intraday(cfg_home),
        "vo2max": (latest("vo2max_x10", lambda v: v) or 0) / 10 or None,
        "strength_sessions": len(strength),
        "cardio_sessions": len(runs),
        "typical_train_time": (times[len(times) // 2] if times else None),
        "recent_activities": [
            {"date": a.start.date().isoformat(), "kind": a.kind.replace("_", " "),
             "duration_min": round(a.duration.value / 60),
             "avg_hr": a.avg_hr, "kcal": a.calories.value if a.calories else None}
            for a in sorted(acts, key=lambda a: a.start, reverse=True)[:12]
        ],
    }


def _vitals(days) -> dict:
    """Body Battery, sleep score + stages, and HRV status — all already pulled, none
    shown until now. Reads the most recent non-null value per signal, since the newest
    day can be mid-collection."""
    if not days:
        return {"available": False}

    def latest(getter):
        for d in reversed(days):
            v = getter(d)
            if v is not None:
                return v, d.on
        return None, None

    bb_hi, bb_on = latest(lambda d: d.body_battery_high)
    bb_lo, _ = latest(lambda d: d.body_battery_low)
    score, score_on = latest(lambda d: d.sleep_score)
    hrv_status, _ = latest(lambda d: d.hrv_status)

    def secs(v):
        return v.value if v is not None else None

    # stages come from the same night as the score
    stages = {"deep": None, "light": None, "rem": None, "awake": None}
    for d in reversed(days):
        if d.sleep_score is not None:
            stages = {"deep": secs(d.sleep_deep_s), "light": secs(d.sleep_light_s),
                      "rem": secs(d.sleep_rem_s), "awake": secs(d.sleep_awake_s)}
            break

    if bb_hi is None and score is None and hrv_status is None:
        return {"available": False}
    return {
        "available": True,
        "body_battery": {"high": bb_hi, "low": bb_lo, "on": bb_on.isoformat() if bb_on else None},
        "sleep_score": score,
        "sleep_score_on": score_on.isoformat() if score_on else None,
        "sleep_stages": stages,
        "hrv_status": hrv_status,
    }


def _exams(cfg, today) -> dict:
    """Medical-exam sets with their written reviews, and a simple next-review nudge.

    Keyed by the folder date (when the exam was recorded). ``next_due`` is a light
    annual prompt off the most recent one; the detailed schedule lives in each review,
    which is an observation against the lab's reference ranges — never medical advice.
    """
    from datetime import timedelta

    from ..exams import (
        checklist_status,
        exams_dir,
        files_for,
        parse_covered,
        read_review,
        strip_covered,
    )

    root = exams_dir(cfg)
    sets = []
    covered: dict = {}
    if root.is_dir():
        for d in sorted((x for x in root.iterdir() if x.is_dir()),
                        key=lambda x: x.name, reverse=True):
            files = [f.name for f in files_for(cfg, d.name)]
            review = read_review(d)
            if not (files or review):
                continue
            for key in parse_covered(review or ""):
                if d.name > covered.get(key, ""):   # keep the most recent date per test
                    covered[key] = d.name
            sets.append({"date": d.name, "files": files,
                         "review": strip_covered(review) if review else None})

    # waist is tracked on the Progress tab — tick it here too if there is a reading
    if cfg.db_path.is_file():
        try:
            from ..db import Store

            with Store(cfg.db_path) as store:
                waisted = [m for m in store.measurements() if getattr(m, "waist", None)]
            if waisted:
                covered["waist"] = max(m.on.isoformat() for m in waisted)
        except Exception:
            pass

    latest = sets[0]["date"] if sets else None
    next_due = None
    days_over = None
    if latest:
        try:
            due = date.fromisoformat(latest) + timedelta(days=365)
            next_due = due.isoformat()
            days_over = (today - due).days
        except ValueError:
            pass
    return {
        "available": True,
        "sets": sets,
        "latest": latest,
        "next_due": next_due,
        "review_overdue": (days_over is not None and days_over > 0),
        "checklist": checklist_status(covered),
    }


def _apply_autoregulation(briefing: dict) -> None:
    """Fold this morning's recovery into today's session: an adjustment banner, and a
    gate that holds load (never adds a plate) on an amber/red day."""
    from ..rules.autoregulation import adjust_for_recovery

    rec = briefing.get("overview", {}).get("recovery", {}) or {}
    off = [s["label"] for s in rec.get("signals", []) if s.get("good") is False]
    adj = adjust_for_recovery(rec.get("status", "unknown"), off)

    tr = briefing.get("training", {})
    if not tr.get("available") or tr.get("rest"):
        return
    tr["adjustment"] = {
        "readiness": adj.readiness, "load_directive": adj.load_directive,
        "reps_in_reserve": adj.reps_in_reserve, "gate_progression": adj.gate_progression,
        "headline": adj.headline, "detail": adj.detail,
    }
    if adj.gate_progression:
        for ex in tr.get("exercises", []):
            call = ex.get("call")
            if call and call.get("decision") == "progress":
                call["gated"] = True


def _cycle_shape(sheet) -> tuple[int, int]:
    """(cycle_length, training-days-per-cycle) for a sheet — e.g. (5, 4) for 4-on-1-off."""
    rotation = {e["day"]: e for e in sheet.get("rotation", [])}
    sessions = {s["day"]: s for s in sheet.get("sessions", [])}
    restart = next((d for d, e in rotation.items() if e.get("restarts_cycle")), None)
    highest = max([*sessions, *rotation], default=1)
    cyc_len = (restart - 1) if restart else highest
    train = sum(1 for d, ses in sessions.items()
                if d <= cyc_len and (ses.get("exercises") if "exercises" in ses else True))
    return max(cyc_len, 1), max(train, 1)


def _volume(cfg, acts, programmes, st, today) -> dict:
    """Weekly tonnage + hard sets, and adherence of scheduled vs actually-trained days.

    The two questions a progress block turns on: am I moving more total load over time,
    and am I actually showing up for the sessions the protocol asked for. Both read the
    data already stored — per-set loads and logged strength activities.
    """
    from ..rules.volume import trend, weekly_volume

    out: dict = {"available": False}
    if not cfg.db_path.is_file():
        return out

    from ..garmin.exercise_store import ExerciseStore

    with ExerciseStore(cfg.db_path) as es:
        rows = es.all_sets()
    sets = [(r.on, r.reps, r.weight_g, r.category) for r in rows]
    series = weekly_volume(sets, weeks=12, today=today)
    if not series:
        return out

    latest = series[-1]
    return {
        "available": True,
        "weeks": [{"start": w.week_start.isoformat(), "tonnage_kg": w.tonnage_kg,
                   "hard_sets": w.hard_sets, "sessions": w.sessions} for w in series],
        "trend_kg": trend(series),
        "this_week": {"tonnage_kg": latest.tonnage_kg, "hard_sets": latest.hard_sets,
                      "sessions": latest.sessions},
        "adherence": _adherence(acts, series, programmes, st, today),
        "load": _load_balance(acts, today),
    }


def _load_balance(acts, today) -> dict:
    """Acute:chronic training-load ratio from Garmin's per-activity load score."""
    from ..rules.workload import acwr

    loads = [(a.start.date(), a.training_load_x10) for a in acts]
    lb = acwr(loads, today=today)
    return {"acute": lb.acute, "chronic_weekly": lb.chronic_weekly, "ratio": lb.ratio,
            "band": lb.band, "reliable": lb.reliable}


def _adherence(acts, series, programmes, st, today, *, window: int = 28) -> dict:
    """Sessions actually trained vs the protocol's expectation over ``window`` days.

    Expectation is derived from the sheet's own shape (training days per cycle), not a
    guess. ``streak`` is the run of consecutive recent weeks that met a sensible weekly
    minimum — read straight from the weekly session counts, so it survives the rolling
    rest day that a fixed-weekday streak would trip over.
    """
    sheet = _live_sheet(programmes, st, today)
    if not sheet:
        return {"available": False}
    cyc_len, train_per_cycle = _cycle_shape(sheet)
    per_week = train_per_cycle / cyc_len * 7
    expected = round(window / cyc_len * train_per_cycle)

    trained = sorted({a.start.date() for a in acts
                      if "strength" in (a.kind or "").lower()
                      and (today - a.start.date()).days < window})
    done = len(trained)
    last = max(trained) if trained else None

    # A week is "met" at the protocol's pace less a couple of allowed misses. The
    # current (partial) week is excluded — it is not over, so it cannot break a streak.
    threshold = max(3, round(per_week) - 2)
    streak = 0
    for w in reversed(series[:-1]):           # newest COMPLETED week first
        if w.sessions >= threshold:
            streak += 1
        else:
            break

    return {
        "available": True,
        "window_days": window,
        "expected": expected,
        "done": done,
        "rate": round(done / expected, 2) if expected else None,
        "streak_weeks": streak,
        "week_threshold": threshold,
        "days_since_last": (today - last).days if last else None,
        "last_trained": last.isoformat() if last else None,
    }


def _pretty_exercise(raw: str) -> str:
    """`BARBELL_BENCH_PRESS` -> `Barbell Bench Press`; `_90_DEGREE_X` -> `90 Degree X`."""
    return " ".join(w.capitalize() for w in raw.strip("_").split("_") if w)


def _progression(cfg, *, top_n: int = 16, window: int = 6) -> dict:
    """Per-exercise load history from the ExerciseStore, most-trained movements first.

    ⚠️ Weight and the exercise name are Garmin's *auto-detection* from the watch,
    not a logged prescription — a machine set can be mislabelled and its plate-stack
    weight guessed. So the honest signal is the trend across sessions where the
    movement is consistent, not any single number. The card says as much.
    """
    from ..garmin.exercise_store import ExerciseStore

    if not cfg.db_path.is_file():
        return {"available": False, "exercises": [], "total": 0}

    exercises = []
    with ExerciseStore(cfg.db_path) as es:
        summaries = es.exercises()
        for e in summaries:
            prog = es.progression(e.name)  # newest first
            if not prog:
                continue
            recent = list(reversed(prog[:window]))  # oldest -> newest for the spark
            series = [(s.on.isoformat(), round((s.top_weight_g or 0) / 1000, 1))
                      for s in recent]
            weighted = [p for p in prog if p.top_weight_g]
            trend_g = (weighted[0].top_weight_g - weighted[-1].top_weight_g
                       if len(weighted) >= 2 else None)
            latest = prog[0]
            exercises.append({
                "name": _pretty_exercise(e.name),
                "raw": e.name,
                "category": e.category,
                "sessions": e.sessions,
                "last_seen": e.last_seen.isoformat(),
                "top_kg": (round(latest.top_weight_g / 1000, 1)
                           if latest.top_weight_g else None),
                "reps": latest.reps_at_top,
                "bodyweight": latest.top_weight_g is None,
                "trend_kg": (round(trend_g / 1000, 1) if trend_g is not None else None),
                "series": series,
            })

    exercises.sort(key=lambda x: (x["sessions"], x["last_seen"]), reverse=True)
    return {
        "available": True,
        "total": len(exercises),
        "exercises": exercises[:top_n],
        "note": (
            "Loads are read from Garmin's on-watch exercise detection, not a logged "
            "sheet — a machine set can be mislabelled or its weight guessed, so read "
            "the trend across sessions, not any single figure. This is the raw "
            "material for Módulo 17's double-progression: when reps hit the top of "
            "the range at a weight, the next step is to add load."
        ),
    }


def _weight_view(weight_hist, today, *, protocol_start=None,
                 trend_days: int = 70, project_days: int = 21) -> dict:
    """Actual weigh-ins plus a dotted least-squares trend over the relevant window.

    Weight day-to-day is mostly water; the honest signal is the slope through the
    recent points, not the last reading. The window that matters is *since the
    protocol started* — fitting across the pre-cut period would blend a rise and a
    fall into a meaningless near-flat line. So we prefer weigh-ins from
    ``protocol_start`` on, fall back to the last ``trend_days`` if too few, and extend
    the fit ``project_days`` past today. Where the next real weigh-ins land against
    that dotted line is the feedback on whether the deficit is doing what maths says.
    """
    actual = [(d.isoformat(), round(g / 1000, 1)) for d, g in weight_hist]
    view = {"actual": actual, "estimate": [], "rate_kg_per_week": None,
            "projected_kg": None, "trend_note": "", "basis": ""}
    if len(weight_hist) < 2:
        view["trend_note"] = "Two weigh-ins are enough to start a trend line."
        return view

    origin = weight_hist[0][0]
    recent, basis = [], ""
    if protocol_start:
        recent = [(d, g) for d, g in weight_hist if d >= protocol_start]
        basis = "since the protocol started"
    if len(recent) < 2:
        recent = [(d, g) for d, g in weight_hist if (today - d).days <= trend_days]
        basis = f"over the last {trend_days} days"
    if len(recent) < 2:
        recent = weight_hist[-4:]  # last resort: the last few points
        basis = "over the last few weigh-ins"
    view["basis"] = basis

    xs = [(d - origin).days for d, _ in recent]
    ys = [g / 1000 for _, g in recent]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return view
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denom
    intercept = mean_y - slope * mean_x

    def at(d: date) -> float:
        return round(intercept + slope * (d - origin).days, 1)

    start = recent[0][0]
    end = today + timedelta(days=project_days)
    view["estimate"] = [(start.isoformat(), at(start)), (end.isoformat(), at(end))]
    view["rate_kg_per_week"] = round(slope * 7, 2)
    view["projected_kg"] = at(end)
    direction = "down" if slope < 0 else "up" if slope > 0 else "flat"
    view["trend_note"] = (
        f"Trend {basis}: {view['rate_kg_per_week']:+} kg/week ({direction}). Dotted line "
        f"carries that trend {project_days} days past today (~{view['projected_kg']} kg) — "
        "an estimate from the data, not a target. Where the next weigh-ins land against "
        "it tells you if it holds."
    )
    return view


def _read_photo_analysis(day_dir) -> dict | None:
    """The written physique review for one photo set, if it has been done.

    A body photo needs eyes on it — the credential-free static server cannot run
    vision — so the review is written (by Claude, in session) to ``analysis.md`` next
    to the set, and the portal renders whatever is there. A set with no file yet shows
    a 'pending' state rather than a fabricated read. First line is the headline; the
    rest are paragraphs split on blank lines.
    """
    path = day_dir / "analysis.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return {"headline": blocks[0] if blocks else "", "paragraphs": blocks[1:]}


#: (attr, label, unit) for the measurement UI/history, in display order.
_MEASURE_UI = [
    ("weight", "Weight", "kg"), ("waist", "Waist", "cm"), ("neck", "Neck", "cm"),
    ("chest", "Chest", "cm"), ("shoulders", "Shoulders", "cm"), ("arm", "Arm", "cm"),
    ("thigh", "Thigh", "cm"), ("hip", "Hip", "cm"), ("calf", "Calf", "cm"),
    ("wingspan", "Wingspan", "cm"),
]


def _measurement_views(measurements, today, protocol_start=None) -> dict:
    """Per-field history + a since-protocol change, for the tape trends and the form.

    ``series`` feeds tiny charts; ``latest`` prefills the edit form; ``changes`` is
    the recomposition read — waist down while an arm holds is the story the scale
    can't tell. The change is measured from the protocol start (falling back to the
    first reading) so it lines up with the weight trend rather than blending in a
    pre-cut bulk. weight is kg, the rest cm; the store keeps grams/mm.
    """
    def human(q, attr):
        if q is None:
            return None
        return round(q.value / 1000, 1) if attr == "weight" else round(q.value / 10, 1)

    series: dict[str, list] = {}
    latest: dict[str, float] = {}
    for attr, _label, _unit in _MEASURE_UI:
        pts = [(m.on.isoformat(), human(getattr(m, attr), attr))
               for m in measurements if getattr(m, attr) is not None]
        if pts:
            series[attr] = pts
            latest[attr] = pts[-1][1]

    changes = []
    for attr, label, unit in _MEASURE_UI:
        pts = series.get(attr)
        if not pts or len(pts) < 2:
            continue
        scoped = ([p for p in pts if date.fromisoformat(p[0]) >= protocol_start]
                  if protocol_start else pts)
        if len(scoped) < 2:
            scoped = pts
        first, last = scoped[0][1], scoped[-1][1]
        changes.append({"attr": attr, "label": label, "unit": unit,
                        "first": first, "latest": last,
                        "delta": round(last - first, 1), "points": len(scoped)})
    return {"series": series, "latest": latest, "changes": changes}


def _progress(days, st, cfg, today, weight_hist=None, measurements=None) -> dict:
    from ..rules.measurements import biotype

    weight_hist = weight_hist or []
    measurements = measurements or []
    pstart = (date.fromisoformat(st["protocol_start"])
              if st.get("protocol_start") else None)
    weight_view = _weight_view(weight_hist, today, protocol_start=pstart)
    weights = weight_view["actual"]

    raw_tape = _resolve_tape(measurements, st)
    bf10, bf_src = _bodyfat(cfg, st, measurements)
    height_mm = cfg.athlete_height_mm or 1770

    def cm(key):
        return raw_tape[key] / 10 if raw_tape.get(key) else None

    tape = {}
    if any(raw_tape.get(f"{a}_mm") for a in _CIRC_ATTRS) or raw_tape.get("wingspan_mm"):
        tape = {
            "measured_on": raw_tape.get("on", ""),
            "neck_cm": cm("neck_mm"), "waist_cm": cm("waist_mm"),
            "chest_cm": cm("chest_mm"), "arm_cm": cm("arm_mm"),
            "thigh_cm": cm("thigh_mm"), "shoulders_cm": cm("shoulders_mm"),
            "hip_cm": cm("hip_mm"), "calf_cm": cm("calf_mm"),
            "wingspan_cm": cm("wingspan_mm"),
            "biotype": (biotype(raw_tape["wingspan_mm"], height_mm)
                        if raw_tape.get("wingspan_mm") else None),
            "notes": raw_tape.get("notes"),
        }

    measure = _measurement_views(measurements, today, pstart)

    photos = []
    pdir = cfg.home / "data" / "photos"
    if pdir.is_dir():
        for day_dir in sorted(pdir.iterdir(), reverse=True):
            jpg = day_dir / "jpg"
            src = jpg if jpg.is_dir() else day_dir
            imgs = sorted(p.name for p in src.glob("*.jpg"))
            if imgs:
                photos.append({"date": day_dir.name, "images": imgs,
                               "subdir": "jpg" if jpg.is_dir() else "",
                               "analysis": _read_photo_analysis(day_dir)})

    return {
        "bodyfat_pct": (bf10 / 10) if bf10 is not None else None,
        "bodyfat_source": bf_src,
        "somatotype": st.get("somatotype"),
        "biotype": tape.get("biotype"),
        "weight_series": weights,
        "weight_view": weight_view,
        "tape": tape,
        "measure": measure,
        "photo_sets": photos,
        "note": (
            "Recomposition shows up in the tape and the mirror before the scale. "
            "Re-measure and re-shoot the same set every 15 days — same room, light "
            "and distance."
        ),
    }
