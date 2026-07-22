"""Render the multi-tab portal from a briefing dict.

Pure: briefing in, one self-contained HTML string out. No I/O. Everything is inline
(CSS, JS, SVG sparklines) because the server enforces a strict same-origin policy
and the page must work with no network (ADR-009). Vanilla JS only — no framework, in
keeping with the project's stdlib-first constraint.

Tabs: Today · Training · Meals · Performance · Progress.
"""

from __future__ import annotations

import html
import json
from typing import Any


def _e(x: Any) -> str:
    return html.escape(str(x))


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1017;--card:#161b24;--card2:#1b212c;--line:#28303d;--ink:#e8ecf3;
  --dim:#95a0b3;--accent:#7dd3a0;--amber:#e5b567;--red:#e0776f;--blue:#6cb6e5;
  --shadow:0 1px 3px rgba(0,0,0,.4)
}
@media(prefers-color-scheme:light){:root{
  --bg:#f4f6f9;--card:#fff;--card2:#f7f9fc;--line:#e4e8ef;--ink:#1a1f28;--dim:#5c6675;
  --accent:#2e9e6b;--amber:#b8862d;--red:#c9564c;--blue:#2f7cb5;--shadow:0 1px 3px rgba(0,0,0,.08)}}
body{background:var(--bg);color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
header{padding:20px 20px 0;max-width:900px;margin:0 auto}
h1{font-size:20px;letter-spacing:-.02em;display:flex;align-items:center;gap:9px}
h1 .dot{width:9px;height:9px;border-radius:50%}
.sub{color:var(--dim);font-size:13px;margin-top:3px}
nav{position:sticky;top:0;z-index:10;background:var(--bg);
  padding:12px 20px;max-width:900px;margin:0 auto;display:flex;gap:6px;overflow-x:auto}
nav button{flex:0 0 auto;background:transparent;border:1px solid var(--line);color:var(--dim);
  padding:8px 15px;border-radius:999px;font-size:14px;font-weight:500;cursor:pointer;white-space:nowrap}
nav button.on{background:var(--accent);border-color:var(--accent);color:#0d1017}
main{max-width:900px;margin:0 auto;padding:4px 20px 80px}
.tab{display:none}.tab.on{display:block;animation:f .2s ease}
@keyframes f{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:18px;margin-bottom:14px;box-shadow:var(--shadow)}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);margin-bottom:12px}
.big{font-size:30px;font-weight:650;letter-spacing:-.02em}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:120px;background:var(--card2);border:1px solid var(--line);
  border-radius:11px;padding:13px 14px}
.stat .n{font-size:23px;font-weight:650;letter-spacing:-.02em}
.stat .l{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-top:3px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;
  font-size:13px;font-weight:600}
.pill.green{background:rgba(125,211,160,.16);color:var(--accent)}
.pill.amber{background:rgba(229,181,103,.16);color:var(--amber)}
.pill.red{background:rgba(224,119,111,.16);color:var(--red)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.sig{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
.sig:last-child{border:none}
.sig .v{font-weight:600;font-variant-numeric:tabular-nums}
.good{color:var(--accent)}.warn{color:var(--amber)}.bad{color:var(--red)}
.meal{border-left:3px solid var(--accent);padding:4px 0 4px 14px;margin-bottom:14px}
.meal .t{color:var(--accent);font-weight:600;font-size:13px}
.meal .lbl{font-weight:600;margin:2px 0}
.meal ul{list-style:none;margin-top:5px}.meal li{color:var(--dim);padding:2px 0}
.ex{display:flex;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}
.ex:last-child{border:none}.ex .nm{font-weight:550}.ex .sc{color:var(--dim);font-size:13px;margin-top:2px}
.ex .rt{color:var(--dim);font-size:12px;white-space:nowrap}
.note{color:var(--dim);font-size:13px;line-height:1.6;margin-top:8px}
.gsheet{background:var(--card2);border:1px dashed var(--line);border-radius:11px;padding:14px;
  font:13px/1.7 ui-monospace,"SF Mono",Menlo,monospace;white-space:pre-wrap;overflow-x:auto}
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.photos img{width:100%;border-radius:10px;border:1px solid var(--line);display:block}
button.copy{background:var(--accent);color:#0d1017;border:none;border-radius:8px;
  padding:8px 14px;font-weight:600;cursor:pointer;font-size:13px;margin-top:10px}
.spark{display:block}
.tag{display:inline-block;background:var(--card2);border:1px solid var(--line);
  border-radius:6px;padding:2px 8px;font-size:12px;color:var(--dim);margin:2px 4px 2px 0}
.disclaimer{color:var(--dim);font-size:12px;text-align:center;padding:16px;line-height:1.6}
"""

JS = """
function tab(id,btn){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('nav button').forEach(b=>b.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  btn.classList.add('on');
  window.scrollTo(0,0);
}
function copyGarmin(){
  const el=document.getElementById('gsheet');
  navigator.clipboard.writeText(el.innerText).then(()=>{
    const b=document.getElementById('copybtn');b.innerText='Copied ✓';
    setTimeout(()=>b.innerText='Copy workout for Garmin Connect',1500);
  });
}
"""


def _spark(series: list, *, w=260, h=40, color="var(--accent)", lower_better=False) -> str:
    """A tiny inline SVG sparkline. Series is [(label, value), ...]."""
    vals = [v for _, v in series if v is not None]
    if len(vals) < 2:
        return '<span class="note">not enough data yet</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = " ".join(
        f"{round(i / (n - 1) * w, 1)},{round(h - (v - lo) / rng * h, 1)}"
        for i, v in enumerate(vals)
    )
    last = vals[-1]
    cx = w
    cy = h - (last - lo) / rng * h
    return (
        f'<svg class="spark" width="{w}" height="{h + 6}" viewBox="0 0 {w} {h + 6}">'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" points="{pts}"/>'
        f'<circle cx="{round(cx, 1)}" cy="{round(cy, 1)}" r="3" fill="{color}"/></svg>'
    )


def _stat(n: Any, label: str) -> str:
    return f'<div class="stat"><div class="n">{_e(n)}</div><div class="l">{_e(label)}</div></div>'


# ── tabs ─────────────────────────────────────────────────────────────────────

def _today_tab(b: dict) -> str:
    ov = b["overview"]
    rec = ov["recovery"]
    tr = b.get("training", {})
    meals = b.get("meals", {})

    sig_rows = ""
    for s in rec["signals"]:
        cls = "good" if s["good"] else ("bad" if s["good"] is False else "warn")
        sig_rows += (
            f'<div class="sig"><span>{_e(s["label"])}</span>'
            f'<span class="v {cls}">{_e(s["note"])}</span></div>'
        )

    first_meal = meals["meals"][0] if meals.get("meals") else None
    train_line = (
        "Rest day" if tr.get("rest")
        else f'Day {tr.get("day","")}: <strong>{_e(tr.get("focus",""))}</strong> '
             f'({len(tr.get("exercises",[]))} exercises)'
    )
    return f"""
<div class="tab on" id="today">
  <div class="card">
    <h2>Today · Day {ov["day_of_60"]} of 60</h2>
    <div class="pill {rec['status']}">{_recovery_emoji(rec['status'])} {_e(rec['headline'])}</div>
    <div style="margin-top:14px">{sig_rows}</div>
  </div>
  <div class="row">
    <div class="card" style="flex:1;min-width:240px">
      <h2>Train</h2>
      <div>{train_line}</div>
      <div class="note">{_e(tr.get("progression","")[:150])}{'…' if tr.get('progression') else ''}</div>
    </div>
    <div class="card" style="flex:1;min-width:240px">
      <h2>Eat · {meals.get('target_kcal','—')} kcal · {meals.get('protein_g','—')} g protein</h2>
      <div class="pill {'green' if meals.get('is_cut') else 'amber'}">{_e(meals.get('direction','').upper() or '—')}</div>
      {f'<div class="note"><strong>{_e(first_meal["time"])}</strong> — {_e(first_meal["label"])}: {_e("; ".join(str(it["grams"]) + "g " + it["food"] for it in first_meal.get("items", [])))}</div>' if first_meal else ''}
    </div>
  </div>
</div>"""


def _recovery_emoji(status: str) -> str:
    return {"green": "●", "amber": "●", "red": "●"}.get(status, "●")


def _training_tab(b: dict) -> str:
    tr = b.get("training", {})
    if not tr.get("available"):
        return '<div class="tab" id="training"><div class="card">No protocol extracted yet.</div></div>'
    if tr.get("rest"):
        return (f'<div class="tab" id="training"><div class="card"><h2>Training</h2>'
                f'<div class="big">Rest day</div><div class="note">{_e(tr.get("note",""))}</div>'
                '</div></div>')

    ex_rows = ""
    for ex in tr["exercises"]:
        rest = f'{ex["rest_s"]}s rest' if ex.get("rest_s") else ""
        warn = (f'<div class="note bad">⚠ {_e("; ".join(ex["issues"]))}</div>'
                if ex.get("issues") else "")
        ex_rows += (
            f'<div class="ex"><div><div class="nm">{_e(ex["name"].title())}</div>'
            f'<div class="sc">{ex["sets"]} sets · reps {_e(ex["scheme"])}</div>{warn}</div>'
            f'<div class="rt">{rest}</div></div>'
        )

    g = tr.get("garmin", {})
    sheet_lines = [f'Workout: {g.get("workout_name","")}', ""]
    for i, s in enumerate(g.get("steps", []), 1):
        sheet_lines.append(f'{i:>2}. {s["exercise"].title()}  →  {s["garmin_name"]}  ({s["scheme"]} reps)')
    if g.get("unmapped"):
        sheet_lines += ["", "Not auto-mapped (enter manually): " + ", ".join(g["unmapped"])]
    sheet = _e("\n".join(sheet_lines))

    return f"""
<div class="tab" id="training">
  <div class="card">
    <h2>{_e(tr["level"])} · Day {tr["day"]} · {_e(tr["focus"])}</h2>
    {ex_rows}
    <div class="note"><strong>Progression:</strong> {_e(tr["progression"])}</div>
  </div>
  <div class="card">
    <h2>Set this in Garmin Connect</h2>
    <div class="note">Open <strong>Garmin Connect → Training → Workouts → Create a Workout</strong>
      (Strength), then add each step below. Or ask Claude in Chrome to enter it for you —
      paste this sheet.</div>
    <div class="gsheet" id="gsheet">{sheet}</div>
    <button class="copy" id="copybtn" onclick="copyGarmin()">Copy workout for Garmin Connect</button>
  </div>
</div>"""


def _meals_tab(b: dict) -> str:
    m = b.get("meals", {})
    meal_html = ""
    for meal in m.get("meals", []):
        items = "".join(
            f'<li><strong>{_e(it["grams"])} g</strong> {_e(it["food"])} '
            f'<span style="color:var(--dim)">· {_e(it["kcal"])} kcal</span></li>'
            for it in meal.get("items", [])
        )
        meal_html += (
            f'<div class="meal"><div class="t">{_e(meal["time"])} · '
            f'{_e(meal["kcal"])} kcal · {_e(meal["protein_g"])} g protein</div>'
            f'<div class="lbl">{_e(meal["label"])}</div><ul>{items}'
            f'<li style="color:var(--accent)">+ {_e(meal.get("free",""))}</li></ul></div>'
        )
    principles = "".join(f"<li>{_e(p)}</li>" for p in m.get("principles", []))

    return f"""
<div class="tab" id="meals">
  <div class="card">
    <h2>Today · hits your target exactly</h2>
    <div class="row">
      {_stat(str(m.get("actual_kcal","—")) + " kcal", f"target {m.get('target_kcal','—')}")}
      {_stat(str(m.get("actual_protein_g","—")) + " g", "protein")}
      {_stat(str(m.get("carb_g","—")) + " g", "carbs")}
      {_stat(str(m.get("fat_g","—")) + " g", "fat")}
    </div>
    <div class="note"><strong>Split:</strong> {_e(m.get("split",""))} &nbsp;·&nbsp;
      Measured TDEE {_e(m.get("tdee_kcal","—"))} kcal, {_e(m.get("deficit_pct",""))}% deficit</div>
    <div style="margin-top:8px"><span class="pill {'green' if m.get('is_cut') else 'amber'}">{_e(m.get("direction","").upper())}</span></div>
    <div class="note">{_e(m.get("direction_why",""))}</div>
  </div>
  <div class="card">
    <h2>Meals · weighed portions, timed to your training</h2>
    {meal_html}
  </div>
  <div class="card">
    <h2>How to use it</h2>
    <ul class="note" style="padding-left:18px">{principles}</ul>
  </div>
</div>"""


def _performance_tab(b: dict) -> str:
    p = b.get("performance", {})

    def block(label, series, unit="", color="var(--accent)", lower=False):
        vals = [v for _, v in series if v is not None]
        latest = vals[-1] if vals else "—"
        avg = round(sum(vals) / len(vals), 1) if vals else "—"
        return (
            f'<div class="card"><h2>{_e(label)}</h2>'
            f'<div class="row" style="align-items:center">'
            f'<div><div class="big">{_e(latest)}{_e(unit)}</div>'
            f'<div class="l" style="color:var(--dim);font-size:12px">avg {_e(avg)}{_e(unit)}</div></div>'
            f'<div style="flex:1;text-align:right">{_spark(series, color=color)}</div>'
            f'</div></div>'
        )

    act_rows = ""
    for a in p.get("recent_activities", []):
        act_rows += (
            f'<tr><td>{_e(a["date"])}</td><td>{_e(a["kind"].title())}</td>'
            f'<td class="num">{_e(a["duration_min"])} min</td>'
            f'<td class="num">{_e(a["avg_hr"] or "—")}</td>'
            f'<td class="num">{_e(a["kcal"] or "—")}</td></tr>'
        )

    return f"""
<div class="tab" id="performance">
  <div class="card">
    <h2>Snapshot</h2>
    <div class="row">
      {_stat(p.get("vo2max","—"), "VO₂ max")}
      {_stat(p.get("strength_sessions","—"), "Strength (12wk)")}
      {_stat(p.get("cardio_sessions","—"), "Cardio (12wk)")}
      {_stat(p.get("typical_train_time","—"), "Usual start")}
    </div>
  </div>
  {block("Energy burned (TDEE)", p.get("tdee_series",[]), " kcal")}
  {block("HRV — overnight", p.get("hrv_series",[]), " ms", "var(--blue)")}
  {block("Resting heart rate", p.get("rhr_series",[]), "", "var(--amber)", True)}
  {block("Sleep", p.get("sleep_series",[]), " h", "var(--blue)")}
  {block("Stress", p.get("stress_series",[]), "", "var(--amber)", True)}
  <div class="card"><h2>Recent sessions</h2>
    <table><tr><th>Date</th><th>Type</th><th class="num">Time</th><th class="num">Avg HR</th><th class="num">kcal</th></tr>
    {act_rows}</table>
  </div>
</div>"""


def _progress_tab(b: dict) -> str:
    pr = b.get("progress", {})
    ath = b.get("athlete", {})

    photo_html = ""
    for pset in pr.get("photo_sets", []):
        imgs = "".join(
            f'<img src="/photos/{_e(pset["date"])}/{_e(img)}" alt="progress photo" loading="lazy">'
            for img in pset["images"]
        )
        photo_html += f'<h2>{_e(pset["date"])}</h2><div class="photos">{imgs}</div>'

    weights = pr.get("weight_series", [])
    meas = pr.get("measurements", {})
    meas_html = ("".join(f'<span class="tag">{_e(k)}: {_e(v)}</span>' for k, v in meas.items())
                 or '<div class="note">No tape measurements yet — waist + neck lets me track '
                    'body fat by the Navy formula every 15 days.</div>')

    return f"""
<div class="tab" id="progress">
  <div class="card">
    <h2>Body composition</h2>
    <div class="row">
      {_stat(f'{ath.get("weight_kg","—")} kg', "Weight")}
      {_stat(f'~{pr.get("bodyfat_pct","—")}%', "Body fat (est.)")}
      {_stat(pr.get("somatotype","—") or "—", "Somatotype")}
    </div>
    <div class="note">{_e(pr.get("bodyfat_source",""))}</div>
  </div>
  <div class="card">
    <h2>Weight trend</h2>
    {_spark(weights, w=560, color="var(--accent)")}
    <div class="note">{'Latest ' + str(weights[-1][1]) + ' kg' if weights else 'No weigh-ins yet'}</div>
  </div>
  <div class="card"><h2>Measurements</h2>{meas_html}</div>
  <div class="card">
    <h2>Progress photos</h2>
    {photo_html or '<div class="note">Drop photos in %RAPHA_HOME%\\\\data\\\\photos\\\\&lt;date&gt;\\\\</div>'}
    <div class="note">{_e(pr.get("note",""))}</div>
  </div>
</div>"""


def render(b: dict) -> str:
    status = b["overview"]["recovery"]["status"]
    dot = {"green": "var(--accent)", "amber": "var(--amber)", "red": "var(--red)"}.get(status, "var(--dim)")
    return (
        f"<style>{CSS}</style>"
        f'<header><h1><span class="dot" style="background:{dot}"></span>Rapha</h1>'
        f'<div class="sub">Day {b["overview"]["day_of_60"]} of 60 · '
        f'{_e(b["generated"])} · Projeto 60 Dias</div></header>'
        '<nav>'
        '<button class="on" onclick="tab(\'today\',this)">Today</button>'
        '<button onclick="tab(\'training\',this)">Training</button>'
        '<button onclick="tab(\'meals\',this)">Meals</button>'
        '<button onclick="tab(\'performance\',this)">Performance</button>'
        '<button onclick="tab(\'progress\',this)">Progress</button>'
        '</nav><main>'
        + _today_tab(b)
        + _training_tab(b)
        + _meals_tab(b)
        + _performance_tab(b)
        + _progress_tab(b)
        + '<div class="disclaimer">Observations against Projeto 60 Dias and published '
          'nutrition science — not medical advice. Every decision is yours.</div>'
        '</main>'
        f"<script>{JS}</script>"
    )


def write(dist, b: dict) -> Any:
    from pathlib import Path
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Rapha</title></head><body>" + render(b) + "</body></html>",
        encoding="utf-8",
    )
    (dist / "briefing.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dist / "index.html"
