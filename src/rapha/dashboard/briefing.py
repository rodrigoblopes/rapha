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
from ..rules import cycle, menu
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


def _meal_times(anchor: str, n: int) -> list[str]:
    """Space the day's meals out from ~90 min after the training anchor."""
    try:
        h, m = (int(x) for x in anchor.split(":"))
    except ValueError:
        h, m = 5, 0
    first = datetime.combine(date.today(), time(h, m)) + timedelta(minutes=90)
    gaps = [0, 5.5, 9, 13.5, 15.5]  # hours after the first meal, per meal index
    out = []
    for i in range(n):
        t = first + timedelta(hours=gaps[i] if i < len(gaps) else 3 * i)
        hour12 = t.hour % 12 or 12          # cross-platform 12-hour, no %-I
        out.append(f"{hour12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}")
    return out


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
    if cfg.db_path.is_file():
        with Store(cfg.db_path) as store:
            days = store.daily_between(today - timedelta(days=120), today)
            acts = store.activities_between(today - timedelta(days=120), today)

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
    briefing["training"] = _training(programmes, st, today)
    briefing["meals"] = _meals(days, diets, foods, cfg, st, today)
    briefing["performance"] = _performance(days, acts, today)
    briefing["progress"] = _progress(days, st, cfg, today)
    return briefing


def _recent_weight(days) -> Grams | None:
    for d in reversed(days):
        if d.weight:
            return d.weight
    return None


def _overview(days, acts, programmes, st, today) -> dict:
    recovery = assess_recovery(days, today=today)
    start = date.fromisoformat(st["protocol_start"]) if st.get("protocol_start") else today
    sheet = _live_sheet(programmes, st)
    pos = cycle.resolve(sheet, start=start, today=today) if sheet else None
    return {
        "day_of_60": (today - start).days + 1,
        "focus": (pos.note if pos and not pos.is_rest else "Rest day") if pos else "—",
        "is_rest": bool(pos and pos.is_rest),
        "recovery": {
            "status": recovery.status.value,
            "headline": recovery.headline,
            "signals": [
                {"label": s.label, "latest": s.latest, "baseline": s.baseline,
                 "good": s.good, "note": s.note}
                for s in recovery.signals
            ],
        },
    }


def _live_sheet(programmes, st) -> dict | None:
    level = st.get("level", "INTERMEDIÁRIO")
    for p in programmes:
        if level.split()[0][:6].upper() in p["level"].upper() and p["sessions"]:
            return p
    return next((p for p in programmes if p["sessions"]), None)


def _training(programmes, st, today) -> dict:
    from ..garmin.workout import RepStrategy, build_workout
    from ..mapping.exercises import try_map

    sheet = _live_sheet(programmes, st)
    start = date.fromisoformat(st["protocol_start"]) if st.get("protocol_start") else today
    if not sheet:
        return {"available": False}
    pos = cycle.resolve(sheet, start=start, today=today)
    if pos.is_rest or pos.session_day is None:
        return {"available": True, "rest": True, "focus": "Rest day",
                "note": pos.note, "level": sheet["level"]}

    session = next((s for s in sheet["sessions"] if s["day"] == pos.session_day), None)
    if not session:
        return {"available": True, "rest": False, "focus": "—", "exercises": []}

    exercises = []
    garmin_steps = []
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
        },
    }


def _meals(days, diets, foods, cfg, st, today) -> dict:
    weight = _recent_weight(days) or Grams(85_000)
    # Measured TDEE over the window, minus the deficit.
    from ..rules.energy import measured_tdee
    tdee = measured_tdee(days, window_days=cfg.tdee_window_days, today=today)
    if tdee is None:
        tdee = Kcal(2450)
    from ..units import Rounding, apply_bps
    target = Kcal(tdee.value - apply_bps(tdee, cfg.deficit_bps, Rounding.DOWN).value)
    protein_g = weight.value * cfg.protein_g_per_kg_x10 // 10000

    bf10 = st.get("bodyfat_pct_x10")
    direction, why = recompose_direction(bf10)

    model = menu.choose_model(diets, target)
    meals = []
    if model:
        anchor = st.get("train_anchor", "05:00")
        times = _meal_times(anchor, len(model["meals"]))
        for i, m in enumerate(model["meals"]):
            alt = m["alternatives"][0] if m["alternatives"] else None
            foods_txt = [_portion_text(p) for p in (alt["portions"] if alt else [])]
            meals.append({
                "number": m["number"],
                "label": MEAL_LABELS.get(m["number"], f"Meal {m['number']}"),
                "time": times[i] if i < len(times) else "",
                "foods": foods_txt,
            })
        subs = {k: [[_portion_text(p) for p in a["portions"]] for a in v]
                for k, v in (model.get("substitutions") or {}).items()}
    else:
        subs = {}

    return {
        "tdee_kcal": tdee.value,
        "target_kcal": target.value,
        "protein_g": protein_g,
        "deficit_pct": cfg.deficit_bps / 100,
        "direction": direction.value,
        "direction_why": why,
        "is_cut": direction is Direction.CUT,
        "model_kcal": model["kcal"] if model else None,
        "meals": meals,
        "substitutions": subs,
        "principles": [
            f"Protein is the anchor: ~{protein_g} g/day protects muscle during the cut.",
            "Carbohydrate around training; keep the biggest carb meals near your session.",
            "Vegetables 'à vontade' — volume without calories keeps you full in a deficit.",
            "Coffee is free (black or with sweetener).",
        ],
    }


def _performance(days, acts, today) -> dict:
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


def _progress(days, st, cfg, today) -> dict:
    weights = [(d.on.isoformat(), round(d.weight.value / 1000, 1))
               for d in days if d.weight]

    photos = []
    pdir = cfg.home / "data" / "photos"
    if pdir.is_dir():
        for day_dir in sorted(pdir.iterdir(), reverse=True):
            jpg = day_dir / "jpg"
            src = jpg if jpg.is_dir() else day_dir
            imgs = sorted(p.name for p in src.glob("*.jpg"))
            if imgs:
                photos.append({"date": day_dir.name, "images": imgs,
                               "subdir": "jpg" if jpg.is_dir() else ""})

    return {
        "bodyfat_pct": (st.get("bodyfat_pct_x10", 0) / 10) or None,
        "bodyfat_source": st.get("bodyfat_source"),
        "somatotype": st.get("somatotype"),
        "weight_series": weights,
        "measurements": st.get("measurements", {}),
        "photo_sets": photos,
        "note": (
            "Recomposition shows up in the mirror and the tape before the scale. "
            "Re-shoot the same set every 15 days — same room, light and distance."
        ),
    }
