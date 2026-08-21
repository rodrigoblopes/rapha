"""Photo vision review — the gating and file-discovery logic (no network).

These pin the graceful no-op paths: without a key, without the SDK, or without photos,
analysis writes nothing and the portal keeps showing 'pending'. The API call itself is
not exercised here (it needs a live key)."""

from types import SimpleNamespace

from rapha import vision


def _cfg(tmp_path):
    return SimpleNamespace(home=tmp_path)


def _add_photo(tmp_path, day="2026-08-21"):
    d = tmp_path / "data" / "photos" / day / "jpg"
    d.mkdir(parents=True)
    (d / "front.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    return day


def test_no_photos_is_a_noop(tmp_path):
    assert vision.analyze_day(_cfg(tmp_path), "2026-08-21") is False


def test_photos_but_no_key_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    day = _add_photo(tmp_path)
    assert vision.analyze_day(_cfg(tmp_path), day) is False
    assert not (tmp_path / "data" / "photos" / day / "analysis.md").exists()


def test_jpgs_are_found_under_the_jpg_subdir(tmp_path):
    day = _add_photo(tmp_path)
    found = vision.jpgs_for(_cfg(tmp_path), day)
    assert len(found) == 1 and found[0].name == "front.jpg"


def test_is_configured_is_false_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert vision.is_configured(_cfg(tmp_path)) is False
