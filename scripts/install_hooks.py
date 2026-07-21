"""Install Rapha's git hooks.

Git hooks are not versioned, so the hook itself lives in scripts/ and this drops a
one-line shim into .git/hooks/pre-commit. Run once after cloning:

    python scripts/install_hooks.py
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

SHIM = """#!/bin/sh
exec python "$(git rev-parse --show-toplevel)/scripts/pre_commit_scan.py"
"""


def main() -> int:
    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )

    hook = root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(SHIM, encoding="utf-8", newline="\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"installed {hook}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
