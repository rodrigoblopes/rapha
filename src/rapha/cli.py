"""`rapha` — the command line.

    rapha login     interactive Garmin login; stores OAuth tokens, never a password
    rapha sync      pull Garmin data into SQLite (unofficial API)
    rapha pull      pull Garmin data via a logged-in Chrome over CDP (API fallback)
    rapha extract   parse the course into %RAPHA_HOME%\\protocol
    rapha assess    decide the Projeto 60 Dias level from real training history
    rapha plan      next week's fichas and menu
    rapha push      create workouts in Garmin Connect (dry-run by default)
    rapha report    render the portal
    rapha serve     serve the portal on 127.0.0.1
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config


def _add_login(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("login", help="authenticate to Garmin and store OAuth tokens")
    p.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of prompting "
        "(so it never appears in shell history or a process listing)",
    )
    p.add_argument(
        "--mfa-file",
        type=Path,
        help="wait for the MFA code to appear in this file instead of prompting; "
        "the file is deleted once read",
    )
    p.add_argument(
        "--mfa-wait",
        type=int,
        default=900,
        help="how long to wait for --mfa-file, in seconds (default: 900)",
    )


def cmd_login(args: argparse.Namespace) -> int:
    from .garmin import auth

    cfg = config.load()

    if args.password_stdin:
        password = sys.stdin.read().strip()
        if not password:
            print("no password on stdin", file=sys.stderr)
            return 2
    else:
        password = getpass.getpass(f"Garmin password for {cfg.garmin_email}: ")

    mfa_prompt = (
        auth.file_mfa_prompt(args.mfa_file, args.mfa_wait) if args.mfa_file else None
    )

    try:
        who = auth.mint_tokens(cfg, password, mfa_prompt=mfa_prompt)
    finally:
        # Not security theatre against a determined attacker — Python strings are
        # immutable and this only drops the reference. It is here so that a later
        # traceback, a debugger, or a repr of locals cannot casually surface it.
        del password

    print(f"authenticated as {who}")
    print(f"tokens stored in {cfg.token_store}")
    print("\nNo password was written to disk. Future runs refresh from these tokens.")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    from .garmin import read as garmin_read

    cfg = config.load()
    end = date.today()
    start = end - timedelta(days=args.days)
    return garmin_read.sync(cfg, start, end, verbose=True)


def cmd_pull(args: argparse.Namespace) -> int:
    """Pull Garmin data by attaching to a logged-in Chrome (ADR-006 fallback).

    The primary `sync` path uses the unofficial API. When that is IP-blocked and
    Chrome's cookies are App-Bound-encrypted, this attaches over CDP to a Chrome
    the user started with --remote-debugging-port=9222 and logged into by hand —
    Cloudflare trusts the human session; Playwright only reads from it.
    """
    from .garmin import browser_pull

    cfg = config.load()
    print(
        f"Attaching to Chrome on {browser_pull.CDP_URL}.\n"
        "  (Start it once with:  chrome --remote-debugging-port=9222 "
        "--user-data-dir=<a non-default dir>  and log into Garmin.)\n"
    )
    try:
        summary = browser_pull.pull(
            cfg,
            activity_days=args.days,
            metric_days=args.metric_days,
            verbose=True,
        )
    except RuntimeError as e:
        print(f"\n{e}", file=sys.stderr)
        return 2

    print(
        f"\ndone: {summary['activities']} activities, {summary['days']} days "
        f"({summary['measured_tdee_days']} with TDEE), "
        f"{summary['exercise_set_rows']} exercise-set rows."
    )
    print("\nnow: rapha assess   rapha plan   rapha report")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    from .protocol import catalog

    cfg = config.load()
    course = Path(args.course) if args.course else cfg.course_dir
    if not course or not course.is_dir():
        print(
            "COURSE_DIR is not set or does not exist. Add it to %RAPHA_HOME%\\.env "
            "or pass --course.",
            file=sys.stderr,
        )
        return 2

    print(f"extracting {course} -> {cfg.protocol_dir}")
    summary = catalog.extract(course, cfg.protocol_dir)

    print(
        f"  {summary['programmes']} sheets, {summary['sessions']} training days, "
        f"{summary['exercises']} exercises"
    )
    print(f"  {summary['diets']} diet models")
    print(f"  {summary['foods']} foods in the TACO table")
    if summary["programmes_with_warnings"] or summary["diets_with_warnings"]:
        print(
            f"  {summary['programmes_with_warnings']} sheets and "
            f"{summary['diets_with_warnings']} diet models need review — see "
            f"{cfg.protocol_dir}\\programmes.json"
        )
    return 0


def _garmin_summary(cfg) -> dict | None:
    """Read-only DB summary for the portal. Never touches Garmin."""
    from datetime import timedelta

    from .db import Store
    from .rules.energy import measured_tdee

    if not cfg.db_path.is_file():
        return None
    with Store(cfg.db_path) as store:
        end = date.today()
        days = store.daily_between(end - timedelta(days=400), end)
        acts = store.activities_between(end - timedelta(days=400), end)
        if not days:
            return None
        tdee = measured_tdee(days, window_days=cfg.tdee_window_days, today=end)
        return {
            "days": len(days),
            "activities": len(acts),
            "range": f"{days[0].on} to {days[-1].on}",
            "window_days": cfg.tdee_window_days,
            "tdee": tdee.value if tdee else "—",
        }


def cmd_report(args: argparse.Namespace) -> int:
    import shutil

    from .dashboard import briefing as briefing_mod
    from .dashboard import portal

    cfg = config.load()
    b = briefing_mod.build(cfg)

    # Copy converted progress photos into dist so the portal can serve them
    # (dist is inside %RAPHA_HOME%, outside OneDrive, served on localhost only).
    src_root = cfg.home / "data" / "photos"
    dst_root = cfg.dist_dir / "photos"
    if src_root.is_dir():
        for pset in b["progress"].get("photo_sets", []):
            src = src_root / pset["date"] / (pset.get("subdir") or "")
            dst = dst_root / pset["date"]
            dst.mkdir(parents=True, exist_ok=True)
            for img in pset["images"]:
                if (src / img).is_file():
                    shutil.copy2(src / img, dst / img)

    path = portal.write(cfg.dist_dir, b)
    print(f"portal written to {path}")
    print(f"  Today: day {b['overview']['day_of_60']}, recovery "
          f"{b['overview']['recovery']['status']}, target "
          f"{b['meals'].get('target_kcal','—')} kcal")
    if not b["training"].get("available"):
        print("  (no protocol yet — run `rapha extract`)")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """Ingest a Garmin Connect web-export directory (the manual fallback)."""
    from .ingest.garmin_csv import ingest_export

    cfg = config.load()
    export_dir = Path(args.dir) if args.dir else cfg.home / "exports"
    if not export_dir.is_dir():
        print(f"no export directory at {export_dir}. Point --dir at your Garmin "
              "export, or drop the CSVs there.", file=sys.stderr)
        return 2

    print(f"ingesting {export_dir}")
    summary = ingest_export(export_dir, cfg.db_path)
    if not summary.get("range"):
        print("  nothing recognised — are these Garmin Connect export CSVs?", file=sys.stderr)
        return 1
    print(f"  {summary['activities']} activities, {summary['days']} days "
          f"({summary['range']})")
    print(f"  {summary['measured_tdee_days']} days carry a measured TDEE")
    print("\nnow: rapha assess   rapha plan   rapha report")
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    from datetime import timedelta

    from .db import Store
    from .rules.level import assess_level

    cfg = config.load()
    if not cfg.db_path.is_file():
        print("no Garmin data yet — run `rapha login` then `rapha sync`", file=sys.stderr)
        return 2

    today = date.today()
    with Store(cfg.db_path) as store:
        acts = store.activities_between(today - timedelta(weeks=53), today)

    ev = assess_level(acts, today=today)
    print(f"\nRecommended level: {ev.recommendation}  ->  {ev.module}\n")
    print(f"  strength sessions (52wk):  {ev.strength_sessions}")
    print(f"  sessions/week:             {ev.sessions_per_week}")
    print(f"  weeks with a session:      {ev.active_weeks}/{ev.weeks_observed} "
          f"({ev.consistency:.0%})")
    print(f"  longest gap:               {ev.longest_gap_days} days")
    print("\n  reasoning:")
    for r in ev.reasoning:
        print(f"    - {r}")
    for n in ev.notes:
        print(f"    ! {n}")
    if ev.provisional:
        print("\n  This is provisional. It is a values-and-safety call, not a verdict —")
        print("  the final level is yours.")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Today's training day and a menu for the calorie target."""
    from datetime import timedelta

    from .protocol import catalog
    from .rules import cycle, menu
    from .rules.energy import predicted_bmr, recompose_direction
    from .units import Grams, Kcal

    cfg = config.load()
    programmes, diets = catalog.load(cfg.protocol_dir)
    foods = catalog.load_foods(cfg.protocol_dir)
    if not programmes:
        print("no protocol yet — run `rapha extract` first", file=sys.stderr)
        return 2

    today = date.today()
    start = date.fromisoformat(args.start) if args.start else today

    # Training: pick the level's sheet (or the first trustworthy one) and resolve today.
    sheet = next(
        (p for p in programmes
         if p["sessions"] and (not args.level or args.level.lower() in p["level"].lower())),
        None,
    )
    print(f"\n=== Day {(today - start).days + 1} of 60 ===")
    if sheet:
        pos = cycle.resolve(sheet, start=start, today=today)
        print(f"\nTraining ({sheet['level']}):")
        if pos.is_rest:
            print("  rest day")
        elif pos.session_day is not None:
            sess = next((s for s in sheet["sessions"] if s["day"] == pos.session_day), None)
            print(f"  day {pos.session_day}: {pos.note}"
                  + (f"  ({len(sess['exercises'])} exercises)" if sess else ""))
        else:
            print(f"  {pos.note}")

    # Nutrition: measured TDEE if Garmin is present, else predicted BMR as a
    # clearly-labelled fallback (ADR-005 keeps the formula a sanity check only).
    target = None
    basis = ""
    if cfg.db_path.is_file():
        from .db import Store
        from .rules.energy import targets as energy_targets

        with Store(cfg.db_path) as store:
            days = store.daily_between(today - timedelta(days=60), today)
            weight = store.latest_weight() or Grams(85_000)
        et = energy_targets(
            days, weight, window_days=cfg.tdee_window_days,
            deficit_bps=cfg.deficit_bps, protein_g_per_kg_x10=cfg.protein_g_per_kg_x10,
            today=today, height_mm=cfg.athlete_height_mm,
            age_years=(today.year - cfg.athlete_birth_year) if cfg.athlete_birth_year else None,
            sex=cfg.athlete_sex,
        )
        if et:
            target, basis = et.intake, f"measured TDEE {et.tdee.value} kcal"
    if target is None and cfg.athlete_height_mm and cfg.athlete_birth_year:
        bmr = predicted_bmr(
            Grams(85_000), cfg.athlete_height_mm,
            today.year - cfg.athlete_birth_year, cfg.athlete_sex,
        )
        target = Kcal(bmr.value * 15 // 10)  # BMR x1.5 fallback, labelled below
        basis = f"predicted BMR {bmr.value} x1.5 (NO Garmin data — a rough fallback)"

    if target is None:
        print("\nNutrition: need Garmin data or ATHLETE_* set for a calorie target.")
        return 0

    model = menu.choose_model(diets, target)
    print(f"\nNutrition (target {target.value} kcal, from {basis}):")
    dir_, why = recompose_direction(args.bodyfat_x10)
    print(f"  direction: {dir_.value} — {why}")
    if model:
        index = menu.build_food_index(foods)
        portions = [menu.cost_portion(p, foods, index) for p in menu.primary_portions(model)]
        totals = menu.total_day(portions)
        print(f"  model: {model['kcal']} kcal ({model['name'][:40]})")
        print(f"  costed total: {totals.kcal.value} kcal  "
              f"P{totals.protein.value}g C{totals.carb.value}g F{totals.fat.value}g")
        if totals.unmatched:
            print(f"  unmatched foods (macros not counted): {totals.unmatched}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    """Create workouts in Garmin Connect. Dry-run by default (ADR-001)."""
    from .garmin.workout import RepStrategy, build_workout, describe
    from .protocol import catalog

    cfg = config.load()
    programmes, _ = catalog.load(cfg.protocol_dir)
    if not programmes:
        print("no protocol yet — run `rapha extract` first", file=sys.stderr)
        return 2

    # Pick the requested sheet, or the first trustworthy one.
    chosen = None
    for p in programmes:
        if args.sheet and args.sheet.lower() not in p["source_file"].lower():
            continue
        if p["sessions"]:
            chosen = p
            break
    if chosen is None:
        print("no matching sheet with sessions", file=sys.stderr)
        return 1

    strategy = RepStrategy.REPS if args.reps else RepStrategy.TIME
    day_filter = args.day
    built = []
    for session in chosen["sessions"]:
        if day_filter and session["day"] != day_filter:
            continue
        name = f"P60D {chosen['level']} D{session['day']} — {session['focus']}"[:60]
        built.append((session, build_workout(session, name=name, strategy=strategy)))

    print(f"\nsheet: {chosen['source_file']}  ({chosen['level']})")
    print(f"strategy: {strategy.value}"
          + ("" if args.reps else "  (reps ride in the step note; see ADR-001)"))
    for _, result in built:
        print("\n" + describe(result))

    if not args.confirm:
        print(
            "\n-- DRY RUN. Nothing was sent to Garmin. --\n"
            "Re-run with --confirm to create these workouts. If reps do not render "
            "on your watch, drop --reps and the rep counts stay in each step's note."
        )
        return 0

    from .garmin import write
    from .garmin.auth import NotAuthenticated

    try:
        created = []
        for session, result in built:
            if result.unmapped:
                print(f"  day {session['day']}: skipping unmapped "
                      f"{sorted(set(result.unmapped))}")
            wid = write.create_workout(cfg, result.payload)
            created.append(wid)
            if args.schedule:
                write.schedule_workout(cfg, wid, args.schedule)
            print(f"  created workout {wid} for day {session['day']}"
                  + (f", scheduled {args.schedule}" if args.schedule else ""))
        print(f"\ncreated {len(created)} workouts.")
    except NotAuthenticated as e:
        print(f"\n{e}", file=sys.stderr)
        return 2
    return 0


def cmd_workouts(args: argparse.Namespace) -> int:
    """Export every workout in the current sheet, ready for Garmin Connect."""
    from .dashboard import workouts_export
    from .dashboard.briefing import _live_sheet, _state
    from .protocol import catalog

    cfg = config.load()
    programmes, _ = catalog.load(cfg.protocol_dir)
    if not programmes:
        print("no protocol yet — run `rapha extract` first", file=sys.stderr)
        return 2

    st = _state(cfg)
    if args.sheet:
        sheet = next((p for p in programmes
                      if str(args.sheet) in p["source_file"] and p["sessions"]), None)
    else:
        sheet = _live_sheet(programmes, st)
    if not sheet:
        print("no matching sheet with sessions", file=sys.stderr)
        return 1

    workouts = workouts_export.build_sheet_workouts(sheet)
    md = workouts_export.to_markdown(sheet, workouts)
    js = workouts_export.to_json(sheet, workouts)

    cfg.dist_dir.mkdir(parents=True, exist_ok=True)
    (cfg.dist_dir / "workouts.md").write_text(md, encoding="utf-8")
    (cfg.dist_dir / "workouts.json").write_text(js, encoding="utf-8")

    print(f"{len(workouts)} workouts from {sheet['source_file']} ({sheet['level']}):")
    for w in workouts:
        flag = f"  ⚠ {len(w['unmapped'])} to enter by hand" if w["unmapped"] else ""
        print(f"  {w['name']}  ({len(w['steps'])} exercises){flag}")
    print(f"\nwritten to:\n  {cfg.dist_dir / 'workouts.md'}\n  {cfg.dist_dir / 'workouts.json'}")
    print(f"served at:\n  http://127.0.0.1:{cfg.portal_port}/workouts.md")
    print("\nHand workouts.md to Claude in Chrome to build them in Garmin Connect.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    cfg = config.load()
    return serve(cfg)


def _not_yet(name: str):
    def run(args: argparse.Namespace) -> int:
        print(f"`rapha {name}` is not built yet.", file=sys.stderr)
        return 1

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rapha", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    _add_login(sub)

    p_sync = sub.add_parser("sync", help="pull Garmin data into SQLite")
    p_sync.add_argument(
        "--days",
        type=int,
        default=365,
        help="how far back to sync activities (default: 365, a full year)",
    )
    p_sync.add_argument(
        "--metric-days",
        type=int,
        default=60,
        help="how far back to sync per-day metrics (default: 60). Activities come "
        "from one bulk call; calories, sleep and HRV are per-day endpoints, so a "
        "year of those would be ~1400 requests against an unpublished rate limit.",
    )

    p_pull = sub.add_parser(
        "pull", help="pull Garmin data via a logged-in Chrome over CDP (API fallback)"
    )
    p_pull.add_argument(
        "--days", type=int, default=365,
        help="how far back to pull activities (default: 365)",
    )
    p_pull.add_argument(
        "--metric-days", type=int, default=45,
        help="how far back to pull per-day metrics (default: 45)",
    )

    p_extract = sub.add_parser(
        "extract", help="parse the course into %%RAPHA_HOME%%/protocol"
    )
    p_extract.add_argument("--course", help="override COURSE_DIR")

    p_import = sub.add_parser(
        "import", help="ingest a Garmin Connect web-export directory"
    )
    p_import.add_argument("--dir", help="export directory (default: %%RAPHA_HOME%%/exports)")

    p_push = sub.add_parser(
        "push", help="create workouts in Garmin Connect (dry-run by default)"
    )
    p_push.add_argument("--sheet", help="filter to a sheet by filename fragment")
    p_push.add_argument("--day", type=int, help="only this training day")
    p_push.add_argument(
        "--reps",
        action="store_true",
        help="use rep-based end conditions (UNVERIFIED on the watch — ADR-001); "
        "without it, reps ride in each step's note and the step is lap-button",
    )
    p_push.add_argument("--schedule", metavar="YYYY-MM-DD", help="schedule to a date")
    p_push.add_argument(
        "--confirm",
        action="store_true",
        help="actually create the workouts (otherwise dry-run)",
    )

    p_plan = sub.add_parser("plan", help="today's training day and a menu")
    p_plan.add_argument("--start", metavar="YYYY-MM-DD", help="protocol start date")
    p_plan.add_argument("--level", help="filter to a level (e.g. Intermediário)")
    p_plan.add_argument(
        "--bodyfat-x10", type=int,
        help="body-fat %% ×10 (e.g. 180 for 18%%) for the cut/bulk direction",
    )

    p_workouts = sub.add_parser(
        "workouts", help="export all workouts in the current sheet for Garmin Connect"
    )
    p_workouts.add_argument("--sheet", help="sheet filename fragment (default: current)")

    for name, help_text in [
        ("assess", "decide the Projeto 60 Dias level from training history"),
        ("report", "render the portal"),
        ("serve", "serve the portal on 127.0.0.1"),
    ]:
        sub.add_parser(name, help=help_text)

    return parser


HANDLERS = {
    "login": cmd_login,
    "sync": cmd_sync,
    "pull": cmd_pull,
    "extract": cmd_extract,
    "import": cmd_import,
    "assess": cmd_assess,
    "plan": cmd_plan,
    "push": cmd_push,
    "workouts": cmd_workouts,
    "report": cmd_report,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = HANDLERS.get(args.command, _not_yet(args.command))
    try:
        return handler(args)
    except config.ConfigError as e:
        print(f"\nconfiguration error:\n{e}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
