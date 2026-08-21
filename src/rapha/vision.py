"""Vision review of progress photos — written the moment they are uploaded.

The static portal server holds no credential and cannot run vision (ADR-001/009). So
this runs as a **separate, short-lived process** the upload flow fires — the same shape
as ``pull-now`` firing the scheduled task: it reads the day's JPGs, asks Claude to write
a physique-progress read, and saves it to ``analysis.md`` beside the set, which the
portal already renders. The listening server never holds the Anthropic key; this
subprocess reads it, uses it, and exits.

Optional by design. It needs the ``anthropic`` SDK (the ``vision`` extra) and an
``ANTHROPIC_API_KEY`` in ``%RAPHA_HOME%/.env``. Without either, analysis simply stays
"pending" exactly as before — nothing on the upload path breaks.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

#: Default model. Override per-install with RAPHA_VISION_MODEL (e.g. a cheaper tier).
DEFAULT_MODEL = "claude-opus-5"
#: A front/side/back set is a handful of shots; cap what one review sends.
MAX_IMAGES = 6

_SYSTEM = (
    "You are a physique and body-recomposition coach reviewing a client's progress "
    "photos for the Projeto 60 Dias programme. Give an honest, encouraging, plain-"
    "language read for someone who is not a fitness expert. Note visible changes in "
    "muscle definition, posture, and where fat is carried; say what looks like it is "
    "progressing and what to prioritise next. These are OBSERVATIONS against a training "
    "framework — never medical advice, never a judgement of the person. Do NOT estimate "
    "a body-fat percentage from a photo. Output a one-line headline, a blank line, then "
    "two to four short paragraphs."
)
_PROMPT = (
    "These are today's progress photos. Write the review now: first line a short, "
    "encouraging headline, then a blank line, then 2-4 short paragraphs of observations "
    "and what to focus on next."
)


def _env(cfg, key: str) -> str | None:
    """A value from the real environment, else %RAPHA_HOME%/.env — same order as config."""
    from .config import _parse_env_file

    return os.environ.get(key) or _parse_env_file(cfg.home / ".env").get(key)


def day_dir(cfg, day: str) -> Path:
    return cfg.home / "data" / "photos" / day


def jpgs_for(cfg, day: str) -> list[Path]:
    d = day_dir(cfg, day)
    jpg = d / "jpg"
    src = jpg if jpg.is_dir() else d
    return sorted(src.glob("*.jpg")) if src.is_dir() else []


def is_configured(cfg) -> bool:
    """True when a key is present AND the SDK is importable — i.e. analysis can run."""
    if not _env(cfg, "ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def analyze_day(cfg, day: str, *, verbose: bool = False) -> bool:
    """Write ``analysis.md`` for one day's photos. Returns True only if one was written.

    A graceful no-op (returns False) when there are no photos, no key, or no SDK — the
    portal keeps showing the 'analysis pending' state rather than anything fabricated.
    """
    def say(m: str) -> None:
        if verbose:
            print(m, flush=True)

    imgs = jpgs_for(cfg, day)[:MAX_IMAGES]
    if not imgs:
        say(f"no photos for {day}")
        return False
    key = _env(cfg, "ANTHROPIC_API_KEY")
    if not key:
        say("no ANTHROPIC_API_KEY (%RAPHA_HOME%/.env) — leaving analysis pending")
        return False
    try:
        import anthropic
    except ImportError:
        say("anthropic SDK not installed — pip install 'rapha[vision]'")
        return False

    content: list[dict] = []
    for p in imgs:
        b64 = base64.standard_b64encode(p.read_bytes()).decode("ascii")
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": b64}})
    content.append({"type": "text", "text": _PROMPT})

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=_env(cfg, "RAPHA_VISION_MODEL") or DEFAULT_MODEL,
        max_tokens=900,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in msg.content
                   if getattr(b, "type", None) == "text").strip()
    if not text:
        say("empty response — nothing written")
        return False
    (day_dir(cfg, day) / "analysis.md").write_text(text, encoding="utf-8")
    say(f"wrote analysis for {day} from {len(imgs)} photo(s)")
    return True
