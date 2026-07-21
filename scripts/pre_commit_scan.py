"""Pre-commit guard for Rapha.

The repo holds code only (ADR-002). This blocks the two ways that rule gets broken in
practice: committing a file that is data rather than code, and pasting a credential into
one that is. It reads only the *staged* content, so it cannot be fooled by a clean
working tree.

Installed by scripts/install_hooks.py into .git/hooks/pre-commit.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath

# Files that are data, not code. Committing any of these means the boundary slipped.
BLOCKED_SUFFIXES = {
    ".db": "a database",
    ".sqlite": "a database",
    ".sqlite3": "a database",
    ".fit": "a Garmin activity/workout file",
    ".tcx": "a Garmin activity file",
    ".gpx": "a GPS track",
    ".pdf": "course material or a statement",
    ".mp4": "course video",
    ".mov": "course video",
    ".mkv": "course video",
    ".webm": "course video",
    ".srt": "a transcript",
    ".vtt": "a transcript",
}

# Directories that only ever hold real data or purchased material.
#
# Anchored at the repo root on purpose. `src/rapha/protocol/` is the *parser
# package*; `protocol/` at the root would be extracted course material. Matching
# the name anywhere in the path blocked the source tree, and a guard that blocks
# legitimate code is a guard that gets bypassed.
BLOCKED_DIRS = ("data/", "photos/", "protocol/", "transcripts/", "dist/")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# Names that announce themselves. Learned the hard way: a real Garmin password
# arrived as `pwd.txt.txt`, which has no `key = value` for the content scanner to
# match, so it sailed straight through. Content matching alone was never enough.
CREDENTIAL_NAME_HINTS = (
    "pwd",
    "passwd",
    "password",
    "secret",
    "credential",
    "id_rsa",
    "id_ed25519",
    "htpasswd",
)
KEY_MATERIAL_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("a Garmin OAuth token blob", re.compile(r"\"oauth[12]_token\"\s*:")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-.]{20,}")),
]

# An assignment to a credential-shaped name. Two deliberate choices:
#
# No \b around the keyword — `_` is a word character, so \bpassword\b does NOT
# match GARMIN_PASSWORD, precisely the name a real leak would use.
#
# The value must be a quoted literal or a bare token running to end of line.
# Without that anchor, `password = sys.stdin.read().strip()` matches and the guard
# blocks its own source.
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?im)(?:password|passwd|secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret)[a-z0-9_-]*\s*[:=]\s*"
    r"(?P<value>[\"'][^\"'\n]{8,}[\"']|[A-Za-z0-9_\-./+]{8,})\s*,?\s*$"
)


def _looks_like_a_secret(value: str) -> bool:
    """Does the assigned value have the shape of a credential, or of code?

    `password=password,` in a function call is a variable name, not a leak, and
    flagging it trains people to bypass the hook. Real credentials essentially
    always carry a digit or mixed case; identifiers written in snake_case do not.

    This is a heuristic and it has a hole: an all-lowercase-letters password would
    slip through. It is defence in depth behind the filename rules and .gitignore,
    not the only thing standing between a secret and the remote.
    """
    v = value.strip("\"'")
    if len(v) < 8:
        return False
    has_digit = any(c.isdigit() for c in v)
    has_upper = any(c.isupper() for c in v)
    has_lower = any(c.islower() for c in v)
    return has_digit or (has_upper and has_lower)

ALLOWED_PATHS = {".env.example", "scripts/pre_commit_scan.py"}

# A test that proves the guard catches credentials must contain things that look
# like credentials. Rather than allowlisting whole files by path -- which turns
# them into permanent blind spots -- a test file may opt out of *content* scanning
# by carrying this marker. Path rules still apply, and the pragma is only honoured
# under tests/, so it can never silence a scan in src/.
FIXTURE_PRAGMA = "pre-commit-scan: fixtures-are-invented"


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def staged_blob(path: str) -> bytes:
    out = subprocess.run(
        ["git", "show", f":{path}"], capture_output=True, check=False
    )
    return out.stdout


def check_path(path: str) -> str | None:
    if path in ALLOWED_PATHS:
        return None

    p = PurePosixPath(path)
    lowered = path.lower()

    if p.name == ".env" or (p.name.startswith(".env.") and path not in ALLOWED_PATHS):
        return "an environment file — the real .env belongs in %RAPHA_HOME%"

    name = p.name.lower()

    if "token" in name and p.suffix == ".json":
        return "a token store"

    if p.suffix.lower() in KEY_MATERIAL_SUFFIXES:
        return "key material"

    if any(hint in name for hint in CREDENTIAL_NAME_HINTS):
        return "a credential file, by its name"

    suffix_reason = BLOCKED_SUFFIXES.get(p.suffix.lower())
    if suffix_reason:
        return suffix_reason

    if any(lowered.startswith(seg) for seg in BLOCKED_DIRS):
        return "inside a data/protocol directory"

    if p.suffix.lower() in IMAGE_SUFFIXES and "test" not in lowered:
        return "an image — body photos belong in %RAPHA_HOME%\\data\\photos"

    return None


def check_content(path: str, blob: bytes) -> list[str]:
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if path.startswith("tests/") and FIXTURE_PRAGMA in text:
        return []

    found = [reason for reason, pattern in SECRET_PATTERNS if pattern.search(text)]

    if any(
        _looks_like_a_secret(m.group("value"))
        for m in CREDENTIAL_ASSIGNMENT.finditer(text)
    ):
        found.insert(0, "an assigned credential")

    return found


def main() -> int:
    problems: list[str] = []

    for path in staged_files():
        reason = check_path(path)
        if reason:
            problems.append(f"  {path}\n      blocked: looks like {reason}")
            continue
        for reason in check_content(path, staged_blob(path)):
            problems.append(f"  {path}\n      blocked: contains what looks like {reason}")

    if not problems:
        return 0

    print("\nRapha pre-commit: refusing this commit.\n", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    print(
        "\nThe repo holds code only (ADR-002). Real data, tokens, photos and course\n"
        "material live in %RAPHA_HOME%, outside OneDrive.\n\n"
        "If this is genuinely a false positive, commit with --no-verify and say so in\n"
        "the commit body.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
