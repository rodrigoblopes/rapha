"""The one mutating endpoint (ADR-010): POST /upload/photo, and its refusals.

The handler is driven directly — built with ``__new__`` to skip the socket setup —
and its response methods are stubbed to record what it decided. That pins the
security decisions (cross-origin refusal, path, size, header) without a live port.
"""

from __future__ import annotations

import io
import json
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


class TestMeasurementEndpoint:
    def test_a_good_measurement_is_stored_and_rendered(self, tmp_path, monkeypatch):
        cfg = SimpleNamespace(db_path=tmp_path / "r.db", photos_dir=tmp_path / "p",
                              dist_dir=tmp_path / "d")
        recorded = {}

        class FakeStore:
            def __init__(self, path):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def record_measurement(self, m):
                recorded["waist"] = m.waist.value if m.waist else None
                recorded["date"] = m.on.isoformat()

        import rapha.dashboard.build as build_mod
        import rapha.db as db_mod
        monkeypatch.setattr(db_mod, "Store", FakeStore)
        monkeypatch.setattr(build_mod, "render", lambda cfg: (tmp_path / "i.html", {}))

        body = json.dumps({"date": "2026-08-13", "waist": "93.5"}).encode()
        h, rec = _handler(
            _same_origin({"Content-Length": str(len(body)), "Content-Type": "application/json"}),
            body=body, cfg=cfg,
        )
        h.path = "/measurement"
        h.do_POST()

        assert rec.json == (200, {"ok": True, "date": "2026-08-13", "rendered": True})
        assert recorded == {"waist": 935, "date": "2026-08-13"}

    def test_invalid_json_is_400(self, tmp_path):
        cfg = SimpleNamespace(db_path=tmp_path / "r.db")
        h, rec = _handler(_same_origin({"Content-Length": "3"}), body=b"{ x", cfg=cfg)
        h.path = "/measurement"
        h.do_POST()
        assert rec.json[0] == 400

    def test_a_measurement_with_a_bad_value_is_400(self, tmp_path):
        cfg = SimpleNamespace(db_path=tmp_path / "r.db")
        body = json.dumps({"waist": "abc"}).encode()
        h, rec = _handler(_same_origin({"Content-Length": str(len(body))}), body=body, cfg=cfg)
        h.path = "/measurement"
        h.do_POST()
        assert rec.json[0] == 400

    def test_a_cross_origin_measurement_is_refused(self, tmp_path):
        body = json.dumps({"waist": "90"}).encode()
        h, rec = _handler(
            _same_origin({"Sec-Fetch-Site": "cross-site", "Content-Length": str(len(body))}),
            body=body,
        )
        h.path = "/measurement"
        h.do_POST()
        assert rec.error[0] == 403


class TestLaunchChrome:
    def test_it_launches_a_fixed_command_and_reports_ok(self, tmp_path, monkeypatch):
        cfg = SimpleNamespace(home=tmp_path)
        calls = {}

        import subprocess
        monkeypatch.setattr("rapha.pull_status.find_chrome", lambda: r"C:\chrome.exe")
        monkeypatch.setattr(subprocess, "Popen",
                            lambda cmd, **kw: calls.setdefault("cmd", cmd))

        h, rec = _handler(_same_origin(), cfg=cfg)
        h.path = "/launch-chrome"
        h.do_POST()

        assert rec.json[0] == 200 and rec.json[1]["ok"] is True
        assert calls["cmd"][0] == r"C:\chrome.exe"
        assert "--remote-debugging-port=9222" in calls["cmd"]

    def test_missing_chrome_is_404(self, tmp_path, monkeypatch):
        cfg = SimpleNamespace(home=tmp_path)
        monkeypatch.setattr("rapha.pull_status.find_chrome", lambda: None)
        h, rec = _handler(_same_origin(), cfg=cfg)
        h.path = "/launch-chrome"
        h.do_POST()
        assert rec.json[0] == 404

    def test_a_cross_origin_launch_is_refused(self):
        h, rec = _handler(_same_origin({"Sec-Fetch-Site": "cross-site"}))
        h.path = "/launch-chrome"
        h.do_POST()
        assert rec.error[0] == 403


class TestPullNow:
    def test_it_triggers_the_task_and_reports_ok(self, monkeypatch):
        import subprocess
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return SimpleNamespace(returncode=0, stdout="SUCCESS", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        h, rec = _handler(_same_origin())
        h.path = "/pull-now"
        h.do_POST()
        assert rec.json[0] == 200 and rec.json[1]["ok"] is True
        assert captured["cmd"] == ["schtasks", "/run", "/tn", "Rapha Pull"]

    def test_a_missing_task_is_reported(self, monkeypatch):
        import subprocess
        monkeypatch.setattr(
            subprocess, "run",
            lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="",
                                              stderr="ERROR: task not found"),
        )
        h, rec = _handler(_same_origin())
        h.path = "/pull-now"
        h.do_POST()
        assert rec.json[0] == 500
        assert "task not found" in rec.json[1]["error"]

    def test_a_cross_origin_pull_is_refused(self):
        h, rec = _handler(_same_origin({"Sec-Fetch-Site": "cross-site"}))
        h.path = "/pull-now"
        h.do_POST()
        assert rec.error[0] == 403


class TestPullStatusEndpoint:
    def test_it_serves_the_status_json(self, tmp_path):
        from rapha import pull_status as ps
        ps.record_pull(tmp_path, {"days": 45})
        cfg = SimpleNamespace(home=tmp_path)
        h, rec = _handler(_same_origin(), cfg=cfg)
        h.path = "/pull-status"
        h.do_GET()
        assert rec.json[0] == 200
        assert rec.json[1]["summary"] == {"days": 45}
        assert "fresh" in rec.json[1]


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
