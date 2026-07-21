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
        help="how far back to sync (default: 365, a full year of history)",
    )

    for name, help_text in [
        ("extract", "parse the course into %RAPHA_HOME%/protocol"),
        ("assess", "decide the Projeto 60 Dias level from training history"),
        ("plan", "next week's fichas and menu"),
        ("push", "create workouts in Garmin Connect (dry-run by default)"),
        ("report", "render the portal"),
        ("serve", "serve the portal on 127.0.0.1"),
    ]:
        sub.add_parser(name, help=help_text)

    return parser


HANDLERS = {"login": cmd_login, "sync": cmd_sync}


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
