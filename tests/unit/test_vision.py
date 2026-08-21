"""Photo vision review — gating and file discovery (no CLI actually invoked).

These pin the graceful no-op paths: without photos, or without a locatable Claude CLI,
analysis writes nothing and the portal keeps showing 'pending'. The CLI call itself is
not exercised here."""

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


def test_photos_but_no_cli_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "find_claude", lambda cfg=None: None)
    day = _add_photo(tmp_path)
    assert vision.analyze_day(_cfg(tmp_path), day) is False
    assert not (tmp_path / "data" / "photos" / day / "analysis.md").exists()


def test_jpgs_are_found_under_the_jpg_subdir(tmp_path):
    day = _add_photo(tmp_path)
    found = vision.jpgs_for(_cfg(tmp_path), day)
    assert len(found) == 1 and found[0].name == "front.jpg"


def test_an_explicit_cli_override_is_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI", raising=False)
    fake = tmp_path / "claude.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CLI", str(fake))
    assert vision.find_claude(_cfg(tmp_path)) == str(fake)
    assert vision.is_configured(_cfg(tmp_path)) is True
