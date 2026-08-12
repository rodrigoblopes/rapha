"""The one mutating endpoint (ADR-010): POST /upload/photo, and its refusals.

The handler is driven directly — built with ``__new__`` to skip the socket setup —
and its response methods are stubbed to record what it decided. That pins the
security decisions (cross-origin refusal, path, size, header) without a live port.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

from rapha import photos, server


class Recorder:
    """Captures whichever response method the handler chose to call."""

    def __init__(self):
        self.error = None
        self.json = None


def _handler(headers: dict, body: bytes = b"", cfg=None, port=8766):
    h = server.PortalHandler.__new__(server.PortalHandler)
    h.headers = headers
    h.rfile = io.BytesIO(body)
    h.server = SimpleNamespace(rapha_cfg=cfg, rapha_port=port)
    rec = Recorder()
    h.send_error = lambda code, msg="": setattr(rec, "error", (code, msg))
    h._json = lambda code, payload: setattr(rec, "json", (code, payload))
    return h, rec


def _same_origin(extra=None, **kw):
    base = {"Host": "127.0.0.1", "Sec-Fetch-Site": "same-origin",
            "Origin": "http://127.0.0.1:8766"}
    base.update(extra or {})
    return base


class TestCrossOriginRefusal:
    def test_a_cross_site_fetch_is_refused(self):
        h, rec = _handler(_same_origin({"Sec-Fetch-Site": "cross-site"}))
        h.do_POST()
        assert rec.error[0] == 403

    def test_a_foreign_origin_is_refused(self):
        h, rec = _handler(_same_origin({"Origin": "http://evil.example"}))
        h.do_POST()
        assert rec.error[0] == 403

    def test_same_origin_with_no_fetch_metadata_is_allowed(self):
        # Old browsers omit Sec-Fetch-Site; absence must not be treated as hostile.
        assert server.PortalHandler._is_same_origin(
            _handler({"Host": "127.0.0.1"})[0]
        )


class TestRequestShape:
    def test_a_wrong_path_is_404(self):
        h, rec = _handler(_same_origin())
        h.path = "/upload/bank"
        h.do_POST()
        assert rec.error[0] == 404

    def test_a_zero_length_body_is_413(self):
        h, rec = _handler(_same_origin({"Content-Length": "0"}))
        h.path = "/upload/photo"
        h.do_POST()
        assert rec.error[0] == 413

    def test_an_oversize_body_is_413_before_it_is_read(self):
        h, rec = _handler(_same_origin({"Content-Length": str(photos.MAX_BYTES + 1)}))
        h.path = "/upload/photo"
        h.do_POST()
        assert rec.error[0] == 413

    def test_a_missing_filename_header_is_400(self):
        h, rec = _handler(_same_origin({"Content-Length": "3"}), body=b"abc")
        h.path = "/upload/photo"
        h.do_POST()
        assert rec.json[0] == 400
        assert "X-Filename" in rec.json[1]["error"]


class TestHappyPath:
    def test_a_good_upload_is_stored_and_rendered(self, tmp_path, monkeypatch):
        cfg = SimpleNamespace(photos_dir=tmp_path / "photos", dist_dir=tmp_path / "dist")
        saved = {}
        monkeypatch.setattr(
            photos, "ingest_photo",
            lambda cfg, name, data: (saved.update(name=name, n=len(data))
                                     or (tmp_path / "photos" / "2026-08-13" / "jpg" / "front.jpg")),
        )
        # Stub the re-render so the test does not need a real store.
        import rapha.dashboard.build as build_mod
        monkeypatch.setattr(build_mod, "render", lambda cfg: (tmp_path / "dist" / "index.html", {}))

        h, rec = _handler(
            _same_origin({"Content-Length": "5", "X-Filename": "front.heic"}),
            body=b"hello", cfg=cfg,
        )
        h.path = "/upload/photo"
        h.do_POST()

        assert rec.json[0] == 200
        assert rec.json[1] == {"ok": True, "saved": "front.jpg", "rendered": True,
                               "date": "2026-08-13"}
        assert saved == {"name": "front.heic", "n": 5}

    def test_a_render_failure_still_reports_the_save(self, tmp_path, monkeypatch):
        cfg = SimpleNamespace(photos_dir=tmp_path / "photos", dist_dir=tmp_path / "dist")
        monkeypatch.setattr(
            photos, "ingest_photo",
            lambda cfg, name, data: tmp_path / "photos" / "2026-08-13" / "jpg" / "back.jpg",
        )
        import rapha.dashboard.build as build_mod

        def boom(cfg):
            raise RuntimeError("render exploded")

        monkeypatch.setattr(build_mod, "render", boom)

        h, rec = _handler(
            _same_origin({"Content-Length": "5", "X-Filename": "back.heic"}),
            body=b"world", cfg=cfg,
        )
        h.path = "/upload/photo"
        h.do_POST()

        assert rec.json[0] == 200  # the save is not lost
        assert rec.json[1]["ok"] is True
        assert rec.json[1]["rendered"] is False


def test_the_upload_path_never_imports_a_garmin_token_holder():
    """ADR-001 still holds with a mutating endpoint present.

    The re-render reaches dashboard.build -> briefing/portal/photos, none of which
    import garmin's auth/read/write/browser_pull. If that ever changes, the server
    starts holding a credential and this is what catches it.
    """
    import rapha.dashboard.build as build_mod

    src = build_mod.render.__code__.co_filename
    text = __import__("pathlib").Path(src).read_text(encoding="utf-8")
    for token_holder in ("garmin.auth", "garmin.read", "garmin.write", "browser_pull"):
        assert token_holder not in text
