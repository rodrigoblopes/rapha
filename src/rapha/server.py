"""`rapha serve` — the local portal.

⚠️ **This module holds no credential and must never import `rapha.garmin`'s token
holders** (`auth`, `read`, `write`, `browser_pull`) — ADR-001. `rapha login`,
`rapha sync` and `rapha pull` are the only code that authenticate to anything. A
process listening on a port therefore has no credential in it, which makes that a
structural property rather than a promise. (Re-rendering the portal after an upload
imports `dashboard.build`, which reaches only `briefing`/`portal`/`photos` — all of
which read files and never a token — so the boundary holds.)

Security properties, all deliberate:

- Binds ``127.0.0.1`` by default. ``PORTAL_HOST=0.0.0.0`` opts into LAN exposure
  (ADR-016) — no auth, every device on the network can view health data and hit the
  mutating endpoints; only the machine's own addresses are added to the Host allowlist
  so DNS-rebinding to a foreign host is still refused.
- Validates the ``Host`` header. DNS rebinding is the real attack against
  localhost services: a malicious page in your browser can otherwise reach them.
- Emits no CORS headers, so a cross-origin page cannot read a response even if it
  manages to send a request.
- **Mutating endpoints, all offline and credential-free**, each refusing cross-origin
  POSTs (``Sec-Fetch-Site`` + ``Origin`` checks): ``POST /upload/photo`` (ADR-010)
  saves a progress photo under ``%RAPHA_HOME%``; ``POST /measurement`` (ADR-011)
  upserts a manual body measurement into SQLite; ``POST /launch-chrome`` (ADR-012)
  opens a debug-enabled Chrome on Garmin's *login* page; ``POST /pull-now`` (ADR-012)
  fires the hourly pull task on demand. The last two are fixed commands with no
  request input (no injection surface) and hold no credential — the server asks the
  OS to start a job or a browser; it never runs the pull or logs in itself. None of
  them moves money, edits a Garmin record, or writes outside ``%RAPHA_HOME%``.
- ``GET /pull-status`` is read-only: pull freshness (a timestamp file) plus whether
  the debug Chrome is reachable (a local TCP probe). It never touches Garmin.
"""

from __future__ import annotations

import json
import socket
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _log(message: str) -> None:
    """Write to stderr if there is one.

    Under ``pythonw`` there is no console and ``sys.stderr`` is None, so an
    unguarded write raises *inside the request handler*: the port keeps listening
    while every response dies mid-flight, and it looks healthy right up until you
    load the page. MrW hit exactly this.
    """
    stream = getattr(sys, "stderr", None)
    if stream is not None:
        try:
            stream.write(message + "\n")
            stream.flush()
        except (ValueError, OSError):
            pass


class PortalHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        _log(f"{self.address_string()} {fmt % args}")

    def _host_is_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        allowed = getattr(self.server, "rapha_allowed_hosts", None) or ALLOWED_HOSTS
        return host in allowed

    def do_GET(self) -> None:
        if not self._host_is_allowed():
            # DNS rebinding defence. An attacker's page resolves their domain to
            # 127.0.0.1 and then talks to this server with their Host header.
            self.send_error(403, "Host not allowed")
            return
        if self.path == "/pull-status":
            self._pull_status()
            return
        if self.path.startswith("/photo-analysis"):
            self._photo_analysis()
            return
        if self.path.startswith("/exam-review"):
            self._exam_review()
            return
        super().do_GET()

    def _pull_status(self) -> None:
        """Live pull freshness + debug-Chrome reachability, for the Data Status tab.

        Read-only and credential-free — it reads a timestamp file and probes a local
        port; it never touches Garmin.
        """
        from .pull_status import pull_status

        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        self._json(200, pull_status(cfg.home))

    def _photo_analysis(self) -> None:
        """Whether a day's photo review has been written yet, and its text.

        Read-only and credential-free — it reads analysis.md from disk so the upload
        UI can poll for the review the fired subprocess is writing. Never touches a key.
        """
        import re
        from urllib.parse import parse_qs, urlparse

        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        day = (parse_qs(urlparse(self.path).query).get("date") or [""])[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            self._json(400, {"ok": False, "error": "bad date"})
            return
        from .dashboard.briefing import _read_photo_analysis

        analysis = _read_photo_analysis(cfg.home / "data" / "photos" / day)
        self._json(200, {"ready": analysis is not None, "analysis": analysis})

    def _exam_review(self) -> None:
        """Whether a day's exam review is written yet, and its text. Read-only."""
        import re
        from urllib.parse import parse_qs, urlparse

        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        day = (parse_qs(urlparse(self.path).query).get("date") or [""])[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            self._json(400, {"ok": False, "error": "bad date"})
            return
        from .exams import exams_dir, read_review

        review = read_review(exams_dir(cfg) / day)
        self._json(200, {"ready": review is not None, "review": review})

    def do_HEAD(self) -> None:
        if not self._host_is_allowed():
            self.send_error(403, "Host not allowed")
            return
        super().do_HEAD()

    # ── the one mutating endpoint (ADR-010) ──────────────────────────────────

    def _is_same_origin(self) -> bool:
        """Refuse a cross-origin POST. Two independent signals, either sufficient.

        ``Sec-Fetch-Site`` is set by the browser and cannot be spoofed by page JS;
        ``Origin`` pins the port. A cross-origin page also cannot set our required
        ``X-Filename`` header without a CORS preflight, which we never answer — so
        this is defence in depth, not a single point of failure.
        """
        site = self.headers.get("Sec-Fetch-Site")
        if site and site != "same-origin":
            return False
        origin = self.headers.get("Origin")
        if origin:
            port = getattr(self.server, "rapha_port", None)
            allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if origin not in allowed:
                return False
        return True

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._host_is_allowed():
            self.send_error(403, "Host not allowed")
            return
        if not self._is_same_origin():
            self.send_error(403, "cross-origin POST refused")
            return
        if self.path == "/upload/photo":
            self._handle_photo_upload()
        elif self.path == "/measurement":
            self._handle_measurement()
        elif self.path == "/launch-chrome":
            self._handle_launch_chrome()
        elif self.path == "/pull-now":
            self._handle_pull_now()
        elif self.path == "/analyze-photos":
            self._handle_analyze_photos()
        elif self.path == "/upload/exam":
            self._handle_exam_upload()
        elif self.path == "/analyze-exams":
            self._handle_analyze_exams()
        else:
            self.send_error(404, "no such endpoint")

    def _read_capped_body(self, cap: int) -> bytes | None:
        """Read the body if its declared length is within cap; else send the error."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "bad Content-Length")
            return None
        if length <= 0 or length > cap:
            self.send_error(413, "empty or oversize body")
            return None
        return self.rfile.read(length)

    def _rerender(self, cfg) -> bool:
        """Re-render the portal after a good write. Never raises — a render failure
        must not lose the write, so it is reported, not thrown."""
        try:
            from .dashboard.build import render

            render(cfg)
            return True
        except Exception as e:
            _log(f"rebuild after write failed: {e}")
            return False

    def _handle_photo_upload(self) -> None:
        from .photos import MAX_BYTES, PhotoError, ingest_photo

        data = self._read_capped_body(MAX_BYTES)
        if data is None:
            return
        filename = self.headers.get("X-Filename", "")
        if not filename:
            self._json(400, {"ok": False, "error": "missing X-Filename header"})
            return
        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        try:
            dest = ingest_photo(cfg, filename, data)
        except PhotoError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        rendered = self._rerender(cfg)
        _log(f"stored progress photo {dest}")
        self._json(200, {"ok": True, "saved": dest.name, "rendered": rendered,
                         "date": dest.parent.parent.name})

    def _handle_exam_upload(self) -> None:
        from .exams import MAX_BYTES, ExamError, ingest_exam

        data = self._read_capped_body(MAX_BYTES)
        if data is None:
            return
        filename = self.headers.get("X-Filename", "")
        if not filename:
            self._json(400, {"ok": False, "error": "missing X-Filename header"})
            return
        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        try:
            dest = ingest_exam(cfg, filename, data)
        except ExamError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        rendered = self._rerender(cfg)
        _log(f"stored medical exam {dest}")
        self._json(200, {"ok": True, "saved": dest.name, "rendered": rendered,
                         "date": dest.parent.name})

    def _handle_analyze_exams(self) -> None:
        """Fire the exam-review subprocess for a date (ADR-015 pattern)."""
        import re
        import subprocess
        import sys as _sys
        from datetime import date as _date

        day = self.headers.get("X-Date", "") or _date.today().isoformat()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            self._json(400, {"ok": False, "error": "bad date"})
            return
        try:
            subprocess.Popen(
                [_sys.executable, "-m", "rapha.cli", "analyze-exam", day],
                close_fds=True)
        except OSError as e:
            self._json(500, {"ok": False, "error": f"could not start analysis: {e}"})
            return
        _log(f"started exam analysis for {day}")
        self._json(200, {"ok": True, "analyzing": True, "date": day})

    def _handle_analyze_photos(self) -> None:
        """Fire the photo-analysis subprocess for a date (ADR-015).

        Mirrors launch-chrome/pull-now: the server asks the OS to start a short-lived
        job and returns immediately. That job — not this listening process — reads the
        Anthropic key from %RAPHA_HOME%/.env, writes analysis.md, re-renders, and exits.
        The date is validated to YYYY-MM-DD and passed as an argv element (no shell), so
        there is no injection surface. A no-key install simply writes nothing.
        """
        import re
        import subprocess
        import sys as _sys
        from datetime import date as _date

        day = self.headers.get("X-Date", "") or _date.today().isoformat()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            self._json(400, {"ok": False, "error": "bad date"})
            return
        try:
            subprocess.Popen(
                [_sys.executable, "-m", "rapha.cli", "analyze-photo", day],
                close_fds=True)
        except OSError as e:
            self._json(500, {"ok": False, "error": f"could not start analysis: {e}"})
            return
        _log(f"started photo analysis for {day}")
        self._json(200, {"ok": True, "analyzing": True, "date": day})

    def _handle_measurement(self) -> None:
        from .db import Store
        from .measurement_input import MeasurementError, measurement_from_form

        data = self._read_capped_body(16 * 1024)  # a form is tiny; cap hard
        if data is None:
            return
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"ok": False, "error": "body is not valid JSON"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "expected a JSON object"})
            return
        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        try:
            m = measurement_from_form(payload)
        except MeasurementError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        with Store(cfg.db_path) as store:
            store.record_measurement(m)
        rendered = self._rerender(cfg)
        _log(f"recorded measurement for {m.on}")
        self._json(200, {"ok": True, "date": m.on.isoformat(), "rendered": rendered})

    def _handle_launch_chrome(self) -> None:
        """Open a debug-enabled Chrome on Garmin's sign-in page (ADR-012).

        The portal runs as the logged-in user (ADR-016 reverted to a logon task), so a
        launched Chrome opens on the real desktop where the user can sign in. The command
        is **fixed** — no request input flows into it — so there is no injection surface;
        the worst a (same-origin-only) trigger can do is open a browser window. It holds
        no credential: the user types the password into Chrome, never into Rapha, and the
        pull only ever *attaches* to the session.
        """
        import subprocess

        from .pull_status import find_chrome, launch_command

        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return
        chrome = find_chrome()
        if not chrome:
            self._json(404, {"ok": False,
                             "error": "Chrome not found in the usual locations"})
            return
        profile = str(cfg.home / "chrome-debug")
        try:
            subprocess.Popen(launch_command(chrome, profile), close_fds=True)
        except OSError as e:
            self._json(500, {"ok": False, "error": f"could not launch Chrome: {e}"})
            return
        _log("launched debug Chrome on the Garmin sign-in page")
        self._json(200, {"ok": True,
                         "message": "Chrome is opening on the Garmin sign-in page — "
                                    "log in, then the hourly pull can attach."})

    def _handle_pull_now(self) -> None:
        """Fire the hourly pull task on demand (ADR-012).

        The server does not run the pull — it asks the OS to start the registered
        "Rapha Pull" task, which runs in its own process. So the credential-free
        server never imports the pull path; the fixed command carries no request
        input. The pull still needs the debug Chrome open, exactly as the hourly run.
        """
        import subprocess

        from .pull_status import run_task_command

        try:
            result = subprocess.run(run_task_command(), capture_output=True,
                                    text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as e:
            self._json(500, {"ok": False, "error": f"could not start the pull: {e}"})
            return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip() \
                or f"schtasks exited {result.returncode}"
            self._json(500, {"ok": False,
                             "error": f"could not start the pull ({detail}) — is the "
                                      "'Rapha Pull' task registered?"})
            return
        _log("triggered an on-demand pull")
        self._json(200, {"ok": True,
                         "message": "Pull started — it takes about a minute. It needs "
                                    "the Garmin browser session open to succeed."})

    def end_headers(self) -> None:
        # No CORS. No caching of a page that changes every rebuild.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def _lan_addresses() -> set[str]:
    """Best-effort local names/IPs to accept in the Host header when bound to the LAN.

    Adding the machine's own addresses (not "any host") keeps the DNS-rebinding defence:
    a foreign Host like attacker.com is still rejected even with the portal on the LAN.
    """
    hosts: set[str] = set()
    try:
        name = socket.gethostname()
        hosts.add(name.lower())
        for info in socket.getaddrinfo(name, None):
            hosts.add(info[4][0].lower())
    except OSError:
        pass
    try:  # the primary outbound-route IP — no packet is actually sent
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        hosts.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return hosts


def serve(cfg, *, forever: bool = True) -> int:
    dist: Path = cfg.dist_dir
    if not (dist / "index.html").is_file():
        _log(f"nothing to serve in {dist} — run `rapha report` first")
        return 1

    handler = partial(PortalHandler, directory=str(dist))
    httpd = ThreadingHTTPServer((cfg.portal_host, cfg.portal_port), handler)
    # The upload handler reads these off the server instance (self.server).
    httpd.rapha_cfg = cfg
    httpd.rapha_port = cfg.portal_port

    allowed = set(ALLOWED_HOSTS)
    lan = cfg.portal_host not in ("127.0.0.1", "localhost")
    if lan:
        # ⚠️ LAN exposure (ADR-016): no auth — every device on the network can view
        # health data and hit the mutating endpoints. Deliberate, user-confirmed.
        addrs = _lan_addresses()
        allowed |= addrs
        allowed |= {h.strip().lower()
                    for h in cfg.portal_allowed_hosts.split(",") if h.strip()}
    httpd.rapha_allowed_hosts = allowed

    if lan:
        ips = sorted(a for a in _lan_addresses() if a[:1].isdigit())
        where = ", ".join(f"http://{a}:{cfg.portal_port}" for a in ips) or "the LAN"
        _log(f"⚠ Rapha portal EXPOSED ON THE LAN (no auth) at {where}  "
             f"(bound {cfg.portal_host}:{cfg.portal_port}, serving {dist})")
    else:
        _log(f"Rapha portal on http://127.0.0.1:{cfg.portal_port}  (serving {dist})")
    if not forever:
        httpd.server_close()
        return 0
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("stopping")
    finally:
        httpd.server_close()
    return 0
