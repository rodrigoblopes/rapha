"""Photo ingest: validation, filename safety, and a real decode round-trip.

Fixtures are synthetic images generated in-memory — never a real body photo.
"""

from __future__ import annotations

import io
from datetime import date
from types import SimpleNamespace

import pytest

from rapha import photos


def _png_bytes(size=(8, 8), colour=(200, 100, 50)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes(size=(8, 8), colour=(10, 120, 200)) -> bytes:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="HEIF")
    return buf.getvalue()


@pytest.fixture
def cfg(tmp_path):
    return SimpleNamespace(photos_dir=tmp_path / "photos")


def test_it_rejects_an_unknown_extension(cfg):
    with pytest.raises(photos.PhotoError, match="unsupported"):
        photos.ingest_photo(cfg, "notes.txt", b"whatever")


def test_it_rejects_an_empty_upload(cfg):
    with pytest.raises(photos.PhotoError, match="empty"):
        photos.ingest_photo(cfg, "front.jpg", b"")


def test_it_rejects_an_oversize_upload(cfg, monkeypatch):
    monkeypatch.setattr(photos, "MAX_BYTES", 10)
    with pytest.raises(photos.PhotoError, match="too large"):
        photos.ingest_photo(cfg, "front.png", _png_bytes())


def test_a_png_is_stored_as_jpg_under_the_shoot_date(cfg):
    dest = photos.ingest_photo(cfg, "front.png", _png_bytes(), on=date(2026, 8, 13))
    assert dest.parent == cfg.photos_dir / "2026-08-13" / "jpg"
    assert dest.name == "front.jpg"
    assert dest.read_bytes()[:3] == b"\xff\xd8\xff"  # JPEG SOI marker


def test_an_iphone_heic_is_converted(cfg):
    dest = photos.ingest_photo(cfg, "IMG_4821.HEIC", _heic_bytes(), on=date(2026, 8, 13))
    assert dest.name == "IMG_4821.jpg"
    from PIL import Image

    with Image.open(dest) as im:
        assert im.format == "JPEG"


def test_a_traversal_filename_cannot_escape_the_folder(cfg):
    dest = photos.ingest_photo(cfg, "../../evil.png", _png_bytes(), on=date(2026, 8, 13))
    assert dest.parent == cfg.photos_dir / "2026-08-13" / "jpg"
    assert ".." not in dest.name


def test_a_repeated_name_does_not_clobber_the_first(cfg):
    a = photos.ingest_photo(cfg, "back.png", _png_bytes(colour=(1, 2, 3)), on=date(2026, 8, 13))
    b = photos.ingest_photo(cfg, "back.png", _png_bytes(colour=(9, 9, 9)), on=date(2026, 8, 13))
    assert a != b
    assert a.exists() and b.exists()


def test_undecodable_bytes_with_a_valid_extension_are_rejected(cfg):
    with pytest.raises(photos.PhotoError, match="decode"):
        photos.ingest_photo(cfg, "front.jpg", b"not really a jpeg")
