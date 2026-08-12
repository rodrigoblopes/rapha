"""Progress-photo ingest: whatever the phone produced in, a web-servable JPG out.

iPhones shoot HEIC; browsers cannot render it and the portal serves JPGs. So an
uploaded photo is decoded (HEIC/HEIF/PNG/JPEG), rotated upright from its EXIF
orientation — iPhones store the sensor orientation in a tag rather than baking it
into the pixels, so skipping this turns half the shots sideways — and re-encoded
as JPEG under ``%RAPHA_HOME%/data/photos/<date>/jpg/``, exactly where the briefing
already looks for them.

`Pillow` + `pillow-heif` are an optional extra (the ``photos`` group), imported
lazily so the core package still installs without them. The whole path is offline
and holds no credential — it only ever touches files under ``%RAPHA_HOME%``.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

#: What a phone camera or a re-share might hand us. HEIC/HEIF need pillow-heif.
ALLOWED_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png"}

#: A generous cap — a 48MP HEIC is a few MB; 30MB is well clear of a real photo
#: yet bounds what a single POST can spend before it is even decoded.
MAX_BYTES = 30 * 1024 * 1024


class PhotoError(ValueError):
    """An upload we will not store: wrong type, empty, oversize, or undecodable."""


def _basename(filename: str) -> str:
    """Last path segment, treating both separators — the client's OS is not ours."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _ext(filename: str) -> str:
    base = _basename(filename)
    return f".{base.rsplit('.', 1)[1].lower()}" if "." in base else ""


def _safe_stem(filename: str) -> str:
    """A filesystem-safe stem. Never a path — an upload cannot escape its folder."""
    base = _basename(filename)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._")
    return (stem or "photo")[:64]


def convert_to_jpg(data: bytes) -> bytes:
    """Decode any allowed image and return upright RGB JPEG bytes."""
    try:
        import pillow_heif
        from PIL import Image, ImageOps
    except ImportError as e:  # pragma: no cover - environment-dependent
        raise PhotoError(
            "image conversion needs Pillow + pillow-heif (the 'photos' extra): "
            "pip install 'rapha[photos]'"
        ) from e

    pillow_heif.register_heif_opener()
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # honour the iPhone orientation tag
        img = img.convert("RGB")
    except Exception as e:
        raise PhotoError(f"could not decode image: {e}") from e

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def _dedupe(path: Path) -> Path:
    """Never clobber an existing photo — a repeated name gets a numeric suffix."""
    if not path.exists():
        return path
    stem, suffix, i = path.stem, path.suffix, 1
    while (candidate := path.with_name(f"{stem}-{i}{suffix}")).exists():
        i += 1
    return candidate


def ingest_photo(cfg, filename: str, data: bytes, *, on: date | None = None) -> Path:
    """Validate, convert to JPG, and store under the shoot date. Returns the path.

    Raises :class:`PhotoError` for anything not worth storing, so the caller can
    turn it into a clean 400 rather than a stack trace.
    """
    ext = _ext(filename)
    if ext not in ALLOWED_EXT:
        raise PhotoError(
            f"unsupported file type {ext or '(none)'}; allowed: "
            f"{', '.join(sorted(ALLOWED_EXT))}"
        )
    if not data:
        raise PhotoError("empty upload")
    if len(data) > MAX_BYTES:
        raise PhotoError(f"file too large ({len(data)} bytes; cap {MAX_BYTES})")

    on = on or date.today()
    jpg = convert_to_jpg(data)
    dest_dir = cfg.photos_dir / on.isoformat() / "jpg"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _dedupe(dest_dir / f"{_safe_stem(filename)}.jpg")
    dest.write_bytes(jpg)
    return dest
