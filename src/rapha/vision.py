"""Vision review of progress photos — written the moment they are uploaded, on your
Claude Max plan, not a metered API key.

The static portal server holds no credential and cannot run vision (ADR-001/009). So the
review runs in a **separate, short-lived process** the upload fires — the shape of
``pull-now`` firing the scheduled task: it locates the already-installed **Claude Code
CLI**, asks it (headless, ``claude -p``) to read the day's JPGs and write a physique read,
captures the text into ``analysis.md`` beside the set, and exits. The CLI runs on the
user's Max subscription; nothing here holds an API key and the ``anthropic`` SDK is not a
dependency.

Fully optional: if the Claude CLI can't be found, analysis stays "pending" exactly as
before — nothing on the upload path breaks.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path

#: A front/side/back set is a handful of shots; cap what one review reads.
MAX_IMAGES = 6
#: Vision over several photos can take a while; well clear of a real run, bounded so a
#: wedged CLI can never hang the analysis forever.
TIMEOUT_S = 300

_PROMPT = (
    "You are a physique and body-recomposition coach reviewing a client's progress "
    "photos for the Projeto 60 Dias programme. Read these photos: {paths}. Then write an "
    "honest, encouraging, plain-language review for someone who is NOT a fitness expert. "
    "Note visible changes in muscle definition, posture, and where fat is carried; say "
    "what looks like it is progressing and what to prioritise next. These are OBSERVATIONS "
    "against a training framework — never medical advice, never a judgement of the person; "
    "do NOT estimate a body-fat percentage from a photo. Output ONLY the review: first line "
    "a short encouraging headline, then a blank line, then two to four short paragraphs. "
    "Do not write any preamble, file paths, or commentary about the task."
)


def _env(cfg, key: str) -> str | None:
    from .config import _parse_env_file

    return os.environ.get(key) or _parse_env_file(cfg.home / ".env").get(key)


def find_claude(cfg=None) -> str | None:
    """Locate the Claude Code CLI. Explicit override wins, then PATH, then the usual
    install spots, then the newest VSCode-extension bundle."""
    candidates: list[str] = []
    override = (os.environ.get("CLAUDE_CLI")
                or (_env(cfg, "CLAUDE_CLI") if cfg is not None else None))
    if override:
        candidates.append(override)
    which = shutil.which("claude")
    if which:
        candidates.append(which)
    home = Path.home()
    candidates += [str(home / ".claude" / "local" / "claude.exe"),
                   str(home / ".claude" / "local" / "claude")]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    # The VSCode extension ships a version-pinned binary; pick the most recent install.
    pat = str(home / ".vscode" / "extensions" / "anthropic.claude-code-*"
              / "resources" / "native-binary" / "claude.exe")
    bundles = glob.glob(pat)
    if bundles:
        return max(bundles, key=os.path.getmtime)
    return None


def day_dir(cfg, day: str) -> Path:
    return cfg.home / "data" / "photos" / day


def jpgs_for(cfg, day: str) -> list[Path]:
    d = day_dir(cfg, day)
    jpg = d / "jpg"
    src = jpg if jpg.is_dir() else d
    return sorted(src.glob("*.jpg")) if src.is_dir() else []


def is_configured(cfg) -> bool:
    """True when the Claude CLI can be found — i.e. analysis can actually run."""
    return find_claude(cfg) is not None


def analyze_day(cfg, day: str, *, verbose: bool = False) -> bool:
    """Write ``analysis.md`` for one day's photos via the Claude CLI. True iff written.

    A graceful no-op (False) when there are no photos or the CLI can't be found — the
    portal keeps its 'analysis pending' state rather than anything fabricated.
    """
    def say(m: str) -> None:
        if verbose:
            print(m, flush=True)

    imgs = jpgs_for(cfg, day)[:MAX_IMAGES]
    if not imgs:
        say(f"no photos for {day}")
        return False
    claude = find_claude(cfg)
    if not claude:
        say("Claude Code CLI not found — leaving analysis pending "
            "(set CLAUDE_CLI in %RAPHA_HOME%/.env if it lives somewhere unusual)")
        return False

    prompt = _PROMPT.format(paths=", ".join(str(p) for p in imgs))
    cmd = [claude, "-p", prompt, "--allowedTools", "Read",
           "--permission-mode", "acceptEdits", "--output-format", "text"]
    model = _env(cfg, "RAPHA_VISION_MODEL")
    if model:
        cmd += ["--model", model]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        say(f"Claude CLI failed to run: {e}")
        return False
    text = (result.stdout or "").strip()
    if result.returncode != 0 or not text:
        say(f"no review produced (exit {result.returncode})")
        return False
    (day_dir(cfg, day) / "analysis.md").write_text(text, encoding="utf-8")
    say(f"wrote analysis for {day} from {len(imgs)} photo(s)")
    return True
