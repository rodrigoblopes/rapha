"""Pull freshness and the browser session it depends on — for the Data Status tab.

The CDP pull (ADR-008) can only run while a human-authenticated Chrome is open on the
debug port. Nothing here holds a credential: it records *when* a pull last succeeded,
checks whether that Chrome is currently reachable, and knows the command to launch it
on Garmin's sign-in page. The user does the logging-in; Rapha only ever attaches.

Split out so the portal and the server can both read pull freshness, and so the pure
parts (freshness maths, the launch command) are testable without a socket or a browser.
"""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

#: Where a human logs into Garmin. connect.garmin.com redirects to the SSO page.
GARMIN_SIGNIN = "https://connect.garmin.com/signin"
DEBUG_PORT = 9222
#: A pull older than this reads as stale — the Data Status dot goes red.
FRESH_MINUTES = 60
#: The scheduled task the "Pull now" button fires — the same hourly job, on demand.
PULL_TASK_NAME = "Rapha Pull"


def run_task_command(task_name: str = PULL_TASK_NAME) -> list[str]:
    """The fixed argv that triggers a scheduled task now (Windows ``schtasks``).

    The button fires the *already-registered* hourly pull rather than running it in
    the server, so the credential-free server (ADR-001) never imports the pull path —
    it only asks the OS to start a job that lives in its own process.
    """
    return ["schtasks", "/run", "/tn", task_name]


def _marker(home) -> Path:
    return Path(home) / "data" / "cache" / "last_pull.json"


def record_pull(home, summary: dict) -> None:
    """Stamp a successful pull with the wall-clock time and what it brought in."""
    now = datetime.now()
    payload = {"at": now.isoformat(timespec="seconds"),
               "epoch": int(now.timestamp()), "summary": summary}
    path = _marker(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_last_pull(home) -> dict | None:
    path = _marker(home)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def chrome_debug_up(port: int = DEBUG_PORT, *, timeout: float = 0.4) -> bool:
    """Is a Chrome listening on the debug port right now? A cheap TCP connect."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def pull_status(home, *, now_epoch: int | None = None,
                fresh_minutes: int = FRESH_MINUTES, check_chrome: bool = True) -> dict:
    """Everything the Data Status tab needs: freshness, age, and session reachability.

    ``fresh`` is True only when a pull landed within ``fresh_minutes``. ``chrome_up``
    is None when the caller skips the live check (the build does, to stay fast and
    side-effect-free; the /pull-status endpoint does the live check).
    """
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    last = read_last_pull(home)
    epoch = int(last["epoch"]) if last and last.get("epoch") else None
    age = None if epoch is None else max(0, now_epoch - epoch)
    return {
        "last_pull_at": last.get("at") if last else None,
        "age_seconds": age,
        "fresh": age is not None and age < fresh_minutes * 60,
        "fresh_minutes": fresh_minutes,
        "summary": last.get("summary") if last else None,
        "chrome_up": chrome_debug_up() if check_chrome else None,
    }


def find_chrome() -> str | None:
    """The Chrome executable, or None if it isn't where Windows usually puts it."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
    ]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def launch_command(chrome: str, profile_dir: str, *,
                   port: int = DEBUG_PORT, url: str = GARMIN_SIGNIN) -> list[str]:
    """The exact, fixed argv to open a debug-enabled Chrome on Garmin's login.

    A dedicated profile keeps it apart from the user's everyday Chrome, and — unlike
    a Playwright-launched browser — a plain Chrome sets no automation flags, so
    Cloudflare treats the human session that logs in here as human (ADR-008).
    """
    return [chrome, f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}", url]
