"""`rapha serve` — the local portal.

⚠️ **This module holds no credential and must never import `rapha.garmin`**
(ADR-001). `rapha login` and `rapha sync` are the only code that authenticate to
anything. A process listening on a port therefore has no credential in it, which
makes that a structural property rather than a promise.

Security properties, all deliberate:

- Binds ``127.0.0.1`` only. Never ``0.0.0.0``.
- Validates the ``Host`` header. DNS rebinding is the real attack against
  localhost services: a malicious page in your browser can otherwise reach them.
- Emits no CORS headers, so a cross-origin page cannot read a response even if it
  manages to send a request.
- Serves ``GET`` only. There are no mutating endpoints — not "none for now", none.
"""

from __future__ import annotations

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
