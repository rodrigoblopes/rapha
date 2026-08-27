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
#: An exam upload is usually one multi-page PDF; a couple of files at most.
MAX_EXAM_FILES = 4
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

_EXAM_PROMPT = "You are a health-literate assistant helping a man in his early 40s who trains hard on a strength and body-recomposition programme understand his OWN lab results. Read this medical exam (a pathology report): {paths}. Then write a clear, plain-language review for someone with no medical background, using these markdown sections, each a '## ' heading:\n\n## What the results say - go through the panels; state plainly that the bulk are within the lab's reference range, and flag anything OUTSIDE it by name (the test, the result, the range, and whether high or low). Be specific and factual.\n\n## Impact on your training - for anything notable, explain in general physiological terms how it could relate to training, recovery or nutrition. If the picture supports hard training, say so plainly and why.\n\n## When to review again - suggest a sensible re-testing rhythm for these panels (e.g. a yearly general panel; a shorter recheck for anything out of range).\n\n## Exams worth considering - from his age, sex and these results, suggest which tests to keep doing or add at this life stage, framed as general screening.\n\nHARD RULES you must follow: this is NOT medical advice and you must say so in one line at the end. Read ONLY against the lab's own reference ranges. Do NOT diagnose any condition, do NOT name or dose any drug or supplement, and do NOT give treatment targets. For anything out of range or any decision, tell him to confirm with his GP or doctor. Start with a one-line headline, then the four sections. No jargon without a plain explanation. Finally, as the very LAST line on its own, output COVERED: followed by a comma-separated list of which of these exact tokens the report actually has results for (omit any it lacks): fbc, uec_egfr, lft, hba1c, glucose, insulin, lipids, iron, b12_folate, tsh, vitd, apob, lpa, hscrp, psa."  # noqa: E501



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


def _run_claude(cfg, prompt: str, *, say=lambda m: None) -> str | None:
    """Run the Claude CLI headless on a prompt and return its text, or None on failure.

    Locates the CLI, runs ``claude -p ... --output-format text`` on the Max plan, decodes
    UTF-8. Read-only tools; no key. Shared by the photo and exam reviews."""
    claude = find_claude(cfg)
    if not claude:
        say("Claude Code CLI not found — leaving the review pending "
            "(set CLAUDE_CLI in %RAPHA_HOME%/.env if it lives somewhere unusual)")
        return None
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
        return None
    text = (result.stdout or "").strip()
    if result.returncode != 0 or not text:
        say(f"no output (exit {result.returncode})")
        return None
    return text


def analyze_exam_day(cfg, day: str, *, verbose: bool = False) -> bool:
    """Write ``review.md`` interpreting a day's uploaded medical exam(s). True iff written.

    A graceful no-op (False) with no files or no CLI. The review is an observation against
    the lab's own reference ranges, never medical advice — see the prompt's hard rules."""
    def say(m: str) -> None:
        if verbose:
            print(m, flush=True)

    from .exams import exams_dir, files_for

    files = files_for(cfg, day)[:MAX_EXAM_FILES]
    if not files:
        say(f"no exam files for {day}")
        return False
    text = _run_claude(cfg, _EXAM_PROMPT.format(paths=", ".join(str(f) for f in files)),
                       say=say)
    if not text:
        return False
    (exams_dir(cfg) / day / "review.md").write_text(text, encoding="utf-8")
    say(f"wrote exam review for {day} from {len(files)} file(s)")
    return True


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
    text = _run_claude(cfg, _PROMPT.format(paths=", ".join(str(p) for p in imgs)), say=say)
    if not text:
        return False
    (day_dir(cfg, day) / "analysis.md").write_text(text, encoding="utf-8")
    say(f"wrote analysis for {day} from {len(imgs)} photo(s)")
    return True
