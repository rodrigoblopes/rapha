"""`rapha` — the command line.

    rapha login     interactive Garmin login; stores OAuth tokens, never a password
    rapha sync      pull Garmin data into SQLite
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
    from .dashboard import render
    from .protocol import catalog

    cfg = config.load()
    programmes, diets = catalog.load(cfg.protocol_dir)
    garmin = _garmin_summary(cfg)

    body = render.render(programmes, diets, garmin)
    path = render.write(cfg.dist_dir, body)
    render.write_briefing(
        cfg.dist_dir,
        {
            "generated": date.today().isoformat(),
            "garmin": garmin,
            "programmes": programmes,
            "diets": diets,
        },
    )
    print(f"portal written to {path}")
    if not programmes:
        print("  (no protocol yet — run `rapha extract`)")
    if not garmin:
        print("  (no Garmin data yet — run `rapha login` then `rapha sync`)")
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

    p_extract = sub.add_parser(
        "extract", help="parse the course into %RAPHA_HOME%/protocol"
    )
    p_extract.add_argument("--course", help="override COURSE_DIR")

    for name, help_text in [
        ("assess", "decide the Projeto 60 Dias level from training history"),
        ("plan", "next week's fichas and menu"),
        ("push", "create workouts in Garmin Connect (dry-run by default)"),
        ("report", "render the portal"),
        ("serve", "serve the portal on 127.0.0.1"),
    ]:
        sub.add_parser(name, help=help_text)

    return parser


HANDLERS = {
    "login": cmd_login,
    "sync": cmd_sync,
    "extract": cmd_extract,
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
