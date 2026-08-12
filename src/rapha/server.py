"""`rapha serve` — the local portal.

⚠️ **This module holds no credential and must never import `rapha.garmin`'s token
holders** (`auth`, `read`, `write`, `browser_pull`) — ADR-001. `rapha login`,
`rapha sync` and `rapha pull` are the only code that authenticate to anything. A
process listening on a port therefore has no credential in it, which makes that a
structural property rather than a promise. (Re-rendering the portal after an upload
imports `dashboard.build`, which reaches only `briefing`/`portal`/`photos` — all of
which read files and never a token — so the boundary holds.)

Security properties, all deliberate:

- Binds ``127.0.0.1`` only. Never ``0.0.0.0``.
- Validates the ``Host`` header. DNS rebinding is the real attack against
  localhost services: a malicious page in your browser can otherwise reach them.
- Emits no CORS headers, so a cross-origin page cannot read a response even if it
  manages to send a request.
- **Exactly ONE mutating endpoint (ADR-008): ``POST /upload/photo`` saves a
  progress photo (HEIC/JPG/PNG) under ``%RAPHA_HOME%`` and re-renders.** It refuses
  cross-origin POSTs (``Sec-Fetch-Site`` + ``Origin`` checks, and it needs a custom
  header a cross-origin page cannot set without a preflight we never answer),
  size-caps the body before reading it, sanitises the filename, and touches no bank,
  no watch and no token. Nothing else mutates.
"""

from __future__ import annotations

import json
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
        host = (self.headers.get("Host") or "").split(":")[0].strip()
        return host in ALLOWED_HOSTS

    def do_GET(self) -> None:
        if not self._host_is_allowed():
            # DNS rebinding defence. An attacker's page resolves their domain to
            # 127.0.0.1 and then talks to this server with their Host header.
            self.send_error(403, "Host not allowed")
            return
        super().do_GET()

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
        from .photos import MAX_BYTES, PhotoError, ingest_photo

        if not self._host_is_allowed():
            self.send_error(403, "Host not allowed")
            return
        if not self._is_same_origin():
            self.send_error(403, "cross-origin POST refused")
            return
        if self.path != "/upload/photo":
            self.send_error(404, "no such endpoint")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "bad Content-Length")
            return
        # Cap on the declared size, before reading a byte of the body.
        if length <= 0 or length > MAX_BYTES:
            self.send_error(413, "empty or oversize upload")
            return

        filename = self.headers.get("X-Filename", "")
        if not filename:
            self._json(400, {"ok": False, "error": "missing X-Filename header"})
            return

        data = self.rfile.read(length)
        cfg = getattr(self.server, "rapha_cfg", None)
        if cfg is None:  # pragma: no cover - serve() always sets it
            self._json(500, {"ok": False, "error": "server misconfigured"})
            return

        try:
            dest = ingest_photo(cfg, filename, data)
        except PhotoError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return

        # Re-render so the new photo shows in the gallery immediately. A failure
        # here must not lose the saved file — report saved-but-not-rendered.
        try:
            from .dashboard.build import render

            render(cfg)
        except Exception as e:
            _log(f"rebuild after upload failed: {e}")
            self._json(200, {"ok": True, "saved": dest.name, "rendered": False,
                             "date": dest.parent.parent.name})
            return

        _log(f"stored progress photo {dest}")
        self._json(200, {"ok": True, "saved": dest.name, "rendered": True,
                         "date": dest.parent.parent.name})

    def end_headers(self) -> None:
        # No CORS. No caching of a page that changes every rebuild.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def serve(cfg, *, forever: bool = True) -> int:
    dist: Path = cfg.dist_dir
    if not (dist / "index.html").is_file():
        _log(f"nothing to serve in {dist} — run `rapha report` first")
        return 1

    handler = partial(PortalHandler, directory=str(dist))
    httpd = ThreadingHTTPServer(("127.0.0.1", cfg.portal_port), handler)
    # The upload handler reads these off the server instance (self.server).
    httpd.rapha_cfg = cfg
    httpd.rapha_port = cfg.portal_port
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
