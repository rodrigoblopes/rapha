"""Render the portal to `%RAPHA_HOME%/dist`.

Pure: state in, HTML out. No I/O beyond writing the file, no clock reads inside
the rendering functions, no database. The portal holds no credential and must
never import `rapha.garmin` (ADR-001).
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

CSS = """
:root {
  --bg:#0f1115; --panel:#171a21; --line:#262b36; --ink:#e6e9ef; --dim:#98a2b3;
  --accent:#7dd3a0; --warn:#e5b567; --bad:#e07a7a;
}
@media (prefers-color-scheme: light) {
  :root { --bg:#f6f7f9; --panel:#fff; --line:#e3e6ec; --ink:#1a1d24; --dim:#5b6474; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
header { padding:28px 32px 18px; border-bottom:1px solid var(--line); }
h1 { margin:0; font-size:22px; letter-spacing:-.02em; }
.sub { color:var(--dim); font-size:13px; margin-top:6px; }
main { padding:24px 32px 64px; max-width:1100px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:26px; }
.tile { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.tile .n { font-size:26px; font-weight:600; letter-spacing:-.02em; }
.tile .l { color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.06em; margin-top:2px; }
section { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; margin-bottom:18px; }
section h2 { margin:0 0 12px; font-size:15px; letter-spacing:.01em; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th,td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--dim); font-weight:500; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
.scroll { overflow-x:auto; }
.warn { color:var(--warn); }
.bad { color:var(--bad); }
.ok { color:var(--accent); }
.empty { color:var(--dim); font-style:italic; }
code { background:rgba(125,211,160,.10); padding:1px 5px; border-radius:4px; font-size:13px; }
.note { color:var(--dim); font-size:13px; margin-top:10px; }
"""


def _e(text: Any) -> str:
    return html.escape(str(text))


def _tile(n: Any, label: str, cls: str = "") -> str:
    return f'<div class="tile"><div class="n {cls}">{_e(n)}</div><div class="l">{_e(label)}</div></div>'


def _sets_summary(exercise: dict) -> str:
    sets = exercise.get("sets") or []
    if not sets:
        return "—"
    if all(s.get("reps") is None for s in sets):
        secs = [s.get("duration") for s in sets if s.get("duration")]
        return f"{len(sets)} × {secs[0]}s" if secs else f"{len(sets)} sets"
    reps = [str(s.get("reps")) for s in sets if s.get("reps") is not None]
    return f"{len(sets)} × " + "/".join(reps)


def _rotation_summary(rotation: list[dict]) -> str:
    if not rotation:
        return '<span class="empty">no rotation page found in this sheet</span>'
    bits = []
    for e in rotation:
        if e.get("is_rest"):
            bits.append(f"day {e['day']}: rest")
        elif e.get("restarts_cycle"):
            bits.append(f"day {e['day']}: restart cycle")
        elif e.get("repeats_day"):
            bits.append(f"day {e['day']} → day {e['repeats_day']}")
    return " &nbsp;·&nbsp; ".join(_e(b) for b in bits)


def render_protocol_section(programmes: list[dict]) -> str:
    if not programmes:
        return (
            '<section><h2>Training protocol</h2>'
            '<p class="empty">Nothing extracted yet — run <code>rapha extract</code>.</p>'
            "</section>"
        )

    by_level: dict[str, list[dict]] = {}
    for p in programmes:
        by_level.setdefault(p.get("level") or "DESCONHECIDO", []).append(p)

    rows = []
    for level, progs in sorted(by_level.items()):
        sessions = sum(len(p["sessions"]) for p in progs)
        exercises = sum(len(s["exercises"]) for p in progs for s in p["sessions"])
        warned = sum(1 for p in progs if p["warnings"])
        flag = (
            f'<span class="warn">{warned} need review</span>'
            if warned
            else '<span class="ok">clean</span>'
        )
        rows.append(
            f"<tr><td><strong>{_e(level)}</strong></td><td>{len(progs)}</td>"
            f"<td>{sessions}</td><td>{exercises}</td><td>{flag}</td></tr>"
        )

    return (
        "<section><h2>Training protocol — Projeto 60 Dias</h2><div class='scroll'><table>"
        "<tr><th>Level</th><th>Sheets</th><th>Days</th><th>Exercises</th><th>Parse</th></tr>"
        + "".join(rows)
        + "</table></div></section>"
    )


def render_sample_session(programmes: list[dict]) -> str:
    """Show one fully parsed day, so the numbers above are inspectable."""
    best = None
    for p in programmes:
        for s in p["sessions"]:
            if len(s["exercises"]) >= 8 and not p["warnings"]:
                best = (p, s)
                break
        if best:
            break
    if not best:
        return ""

    prog, session = best
    rows = "".join(
        f"<tr><td>{_e(ex['name'])}</td><td>{_e(_sets_summary(ex))}</td>"
        f"<td>{_e(str(ex['rest']) + 's' if ex.get('rest') else '—')}</td>"
        f"<td class='warn'>{_e('; '.join(ex.get('issues') or []))}</td></tr>"
        for ex in session["exercises"]
    )
    return (
        f"<section><h2>Sample day — {_e(prog['level'])} sheet "
        f"{_e(prog.get('sheet_number') or '?')}, day {_e(session['day'])}: "
        f"{_e(session['focus'])}</h2><div class='scroll'><table>"
        "<tr><th>Exercise</th><th>Sets × reps</th><th>Rest</th><th>Notes</th></tr>"
        f"{rows}</table></div>"
        f"<p class='note'>Cycle: {_rotation_summary(prog.get('rotation') or [])}</p>"
        "</section>"
    )


def render_diets_section(diets: list[dict]) -> str:
    if not diets:
        return ""
    usable = [d for d in diets if d.get("kcal") and not d["warnings"]]
    rows = "".join(
        f"<tr><td>{_e(d['kcal'])} kcal</td><td>{len(d['meals'])}</td>"
        f"<td>{sum(len(a['portions']) for m in d['meals'] for a in m['alternatives'])}</td>"
        f"<td>{_e(d['name'][:46])}</td></tr>"
        for d in sorted(usable, key=lambda x: x["kcal"])
    )
    flagged = len(diets) - len(usable)
    note = (
        f"<p class='note warn'>{flagged} of {len(diets)} models are not usable as-is "
        "— either no calorie level in the filename or too few foods read. They are "
        "excluded rather than silently half-parsed.</p>"
        if flagged
        else ""
    )
    return (
        "<section><h2>Diet models — selectable by calorie target</h2><div class='scroll'><table>"
        "<tr><th>Level</th><th>Meals</th><th>Foods</th><th>Model</th></tr>"
        f"{rows}</table></div>{note}</section>"
    )


def render_garmin_section(summary: dict[str, Any] | None) -> str:
    if not summary or not summary.get("days"):
        return (
            "<section><h2>Garmin</h2>"
            '<p class="empty">No Garmin data yet — run <code>rapha login</code> '
            "then <code>rapha sync</code>.</p></section>"
        )
    return (
        "<section><h2>Garmin</h2><div class='scroll'><table>"
        f"<tr><th>Days stored</th><td>{_e(summary['days'])}</td></tr>"
        f"<tr><th>Activities</th><td>{_e(summary.get('activities', 0))}</td></tr>"
        f"<tr><th>Range</th><td>{_e(summary.get('range', '—'))}</td></tr>"
        f"<tr><th>Measured TDEE ({_e(summary.get('window_days','?'))}d avg)</th>"
        f"<td>{_e(summary.get('tdee', '—'))} kcal</td></tr>"
        "</table></div></section>"
    )


def render(
    programmes: list[dict],
    diets: list[dict],
    garmin: dict[str, Any] | None = None,
    *,
    today: date | None = None,
) -> str:
    stamp = (today or date.today()).isoformat()
    prog_warned = sum(1 for p in programmes if p["warnings"])

    tiles = "".join(
        [
            _tile(sum(len(p["sessions"]) for p in programmes), "training days"),
            _tile(
                sum(len(s["exercises"]) for p in programmes for s in p["sessions"]),
                "exercises",
            ),
            _tile(len([d for d in diets if d.get("kcal") and not d["warnings"]]), "diet models"),
            _tile(
                prog_warned,
                "sheets to review",
                "warn" if prog_warned else "ok",
            ),
            _tile((garmin or {}).get("days", 0), "garmin days",
                  "" if (garmin or {}).get("days") else "dim"),
        ]
    )

    return (
        f"<style>{CSS}</style>"
        "<header><h1>Rapha</h1>"
        f'<div class="sub">Projeto 60 Dias &middot; macro-first recomposition '
        f"&middot; built {_e(stamp)}</div></header><main>"
        f'<div class="tiles">{tiles}</div>'
        + render_garmin_section(garmin)
        + render_protocol_section(programmes)
        + render_sample_session(programmes)
        + render_diets_section(diets)
        + "<p class='note'>Observations against a named protocol and published "
        "nutrition science. Not medical advice — every decision is yours.</p>"
        "</main>"
    )


def write(dist: Path, body: str, title: str = "Rapha") -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    path = dist / "index.html"
    path.write_text(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    return path


def write_briefing(dist: Path, payload: dict[str, Any]) -> Path:
    """The machine-readable half — what Claude reads to do the coaching."""
    dist.mkdir(parents=True, exist_ok=True)
    path = dist / "briefing.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
