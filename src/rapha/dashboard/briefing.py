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


def _bodyfat(cfg, st) -> tuple[int | None, str]:
    """Best body-fat estimate (×10) and its source.

    Prefer the Navy formula from tape measurements — objective and repeatable —
    over the one-off photo estimate, but keep the photo number in the note when the
    two disagree, because they carry different errors.
    """
    from ..rules.measurements import navy_bodyfat_pct_x10

    m = st.get("measurements") or {}
    height_mm = cfg.athlete_height_mm or 1770
    if m.get("waist_mm") and m.get("neck_mm"):
        navy = navy_bodyfat_pct_x10(m["waist_mm"], m["neck_mm"], height_mm,
                                    sex=cfg.athlete_sex)
        if navy is not None:
            photo = st.get("bodyfat_pct_x10")
            extra = (f" (photo estimate read ~{photo / 10:.0f}%; the tape is the "
                     "repeatable measure)") if photo else ""
            return navy, f"Navy formula from tape, {m.get('measured_on', '')}{extra}"
    return st.get("bodyfat_pct_x10"), st.get("bodyfat_source", "")


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
    from ..rules.energy import measured_tdee
    from ..rules.targeted_menu import build_targeted_day
    from ..units import Rounding, apply_bps

    weight = _recent_weight(days) or Grams(85_000)
    tdee = measured_tdee(days, window_days=cfg.tdee_window_days, today=today) or Kcal(2450)
    target = Kcal(tdee.value - apply_bps(tdee, cfg.deficit_bps, Rounding.DOWN).value)
    protein_g = weight.value * cfg.protein_g_per_kg_x10 // 10000

    bf10, _ = _bodyfat(cfg, st)
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
    from ..rules.measurements import biotype

    weights = [(d.on.isoformat(), round(d.weight.value / 1000, 1))
               for d in days if d.weight]

    bf10, bf_src = _bodyfat(cfg, st)
    m = st.get("measurements") or {}
    height_mm = cfg.athlete_height_mm or 1770
    tape = {}
    if m.get("neck_mm"):
        tape = {
            "measured_on": m.get("measured_on", ""),
            "neck_cm": m["neck_mm"] / 10,
            "waist_cm": m["waist_mm"] / 10 if m.get("waist_mm") else None,
            "wingspan_cm": m["wingspan_mm"] / 10 if m.get("wingspan_mm") else None,
            "biotype": biotype(m["wingspan_mm"], height_mm) if m.get("wingspan_mm") else None,
        }

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
        "bodyfat_pct": (bf10 / 10) if bf10 is not None else None,
        "bodyfat_source": bf_src,
        "somatotype": st.get("somatotype"),
        "biotype": tape.get("biotype"),
        "weight_series": weights,
        "tape": tape,
        "photo_sets": photos,
        "note": (
            "Recomposition shows up in the tape and the mirror before the scale. "
            "Re-measure and re-shoot the same set every 15 days — same room, light "
            "and distance."
        ),
    }
