"""Export every workout in a sheet, ready to build in Garmin Connect.

Produces two artefacts for the whole rotation, not just today:

- ``workouts.md`` — a human- and Claude-readable instruction sheet. Hand it to
  Claude in the Chrome extension and it can build each workout in Garmin Connect's
  UI step by step, or you enter them yourself.
- ``workouts.json`` — the structured Garmin workout payloads (ADR-001 strategy),
  for any tool that can post them directly.

Pure: a parsed sheet in, the two strings out. No I/O, no credential.
"""

from __future__ import annotations

import json
import re

from ..garmin.workout import RepStrategy, build_workout
from ..mapping.exercises import try_map

# A ficha row that is really a stray "4 séries" header, not an exercise.
_NOISE = re.compile(r"^\s*\d+\s*s[ée]ries?\s*$", re.IGNORECASE)


def _scheme(ex: dict) -> str:
    sets = ex.get("sets") or []
    reps = [s.get("reps") for s in sets]
    if reps and all(r is not None for r in reps):
        return " / ".join(str(r) for r in reps)
    durs = [s.get("duration") for s in sets]
    if any(durs):
        secs = next((d["value"] if isinstance(d, dict) else d for d in durs if d), 0)
        return f"{len(sets)} × {secs}s hold"
    return f"{len(sets)} sets"


def _real_exercises(session: dict) -> list[dict]:
    return [e for e in session.get("exercises", []) if not _NOISE.match(e["name"])]


def build_sheet_workouts(sheet: dict) -> list[dict]:
    """One structured workout per distinct training day in the sheet."""
    out = []
    for session in sheet.get("sessions", []):
        exercises = _real_exercises(session)
        name = f"P60D {sheet['level']} D{session['day']} — {session['focus']}"[:60]
        steps = []
        unmapped = []
        for ex in exercises:
            gm = try_map(ex["name"])
            rest = ex.get("rest")
            rest_s = rest["value"] if isinstance(rest, dict) else rest
            if gm is None:
                unmapped.append(ex["name"])
            steps.append({
                "exercise": ex["name"],
                "garmin_category": gm.category if gm else None,
                "garmin_name": (gm.name or gm.category) if gm else None,
                "scheme": _scheme(ex),
                "rest_s": rest_s,
                "video_url": ex.get("video_url"),
            })
        payload = build_workout(
            {"exercises": exercises}, name=name, strategy=RepStrategy.REPS
        ).payload
        out.append({
            "day": session["day"],
            "focus": session["focus"],
            "name": name,
            "steps": steps,
            "unmapped": sorted(set(unmapped)),
            "payload": payload,
        })
    return out


def _rotation_line(sheet: dict) -> str:
    days = sorted(s["day"] for s in sheet.get("sessions", []))
    seq = " → ".join(f"Day {d}" for d in days)
    rot = sheet.get("rotation", [])
    rest_days = [e["day"] for e in rot if e.get("is_rest")]
    rest = f", rest on day {', '.join(map(str, rest_days))}" if rest_days else ""
    return f"{seq}{rest}, then repeat."


def to_markdown(sheet: dict, workouts: list[dict]) -> str:
    lines = [
        f"# Projeto 60 Dias — {sheet['level']} "
        f"(sheet {sheet.get('sheet_number', '?')}, {sheet.get('weeks', '')})",
        "",
        "Build these workouts in **Garmin Connect → Training → Workouts → "
        "Create a Workout → Strength**. One workout per training day.",
        "",
        f"**Rotation:** {_rotation_line(sheet)}",
        "",
        "For each exercise: add a step, set the exercise (the Garmin name below), "
        "set the target to the reps shown, and the rest to the seconds shown. "
        "Reps that change per set (e.g. `15 / 15 / 12 / 12`) mean one set at each "
        "number, descending as the load rises (Cariani's pyramid). **Paste the "
        "video link into the step's Notes / Description field** so the demo is on "
        "your watch and in Connect.",
        "",
    ]
    for w in workouts:
        lines.append(f"## {w['name']}")
        lines.append("")
        lines.append("| # | Exercise (PT) | Garmin exercise | Sets × reps | Rest | Video (put in Notes) |")
        lines.append("|---|---------------|-----------------|-------------|------|----------------------|")
        for i, s in enumerate(w["steps"], 1):
            gm = s["garmin_name"] or "— (add manually)"
            rest = f"{s['rest_s']}s" if s["rest_s"] else "—"
            vid = s.get("video_url") or "—"
            lines.append(
                f"| {i} | {s['exercise'].title()} | {gm} | {s['scheme']} | {rest} | {vid} |"
            )
        if w["unmapped"]:
            lines.append("")
            lines.append(f"> Not auto-mapped, enter by hand: {', '.join(w['unmapped'])}")
        lines.append("")
    return "\n".join(lines)


def to_json(sheet: dict, workouts: list[dict]) -> str:
    return json.dumps(
        {
            "level": sheet["level"],
            "sheet_number": sheet.get("sheet_number"),
            "weeks": sheet.get("weeks"),
            "rotation": _rotation_line(sheet),
            "note": "Each step carries a video_url — paste it into the Garmin step's "
                    "Notes/Description field.",
            "workouts": [
                {k: w[k] for k in ("day", "focus", "name", "steps", "unmapped", "payload")}
                for w in workouts
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
