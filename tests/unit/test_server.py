"""The portal's security properties, pinned.

These are the ones that are invisible when they work and catastrophic when they
silently stop working, so they get tests rather than comments.
"""

import re
import sys
from pathlib import Path

from rapha import server


class TestItHoldsNoCredential:
    def test_the_server_module_does_not_import_garmin(self):
        """ADR-001's structural property: a listening process has no credential.

        If someone ever "simplifies" this by having the portal refresh its own
        data, that stops being true, and this test is what says so.
        """
        source = Path(server.__file__).read_text(encoding="utf-8")
        import_lines = [
            line
            for line in source.splitlines()
            if re.match(r"\s*(?:from|import)\s", line)
        ]

        # Match imports, not prose. The module's docstring names rapha.garmin in
        # order to say it must never import it, and an over-eager grep fails on
        # its own documentation.
        offenders = [line for line in import_lines if "garmin" in line.lower()]
        assert not offenders, f"the portal must hold no credential: {offenders}"


class TestHostValidation:
    def test_only_localhost_names_are_accepted(self):
        assert "127.0.0.1" in server.ALLOWED_HOSTS
        assert "localhost" in server.ALLOWED_HOSTS

    def test_an_attacker_domain_is_not(self):
        # DNS rebinding: attacker.com resolves to 127.0.0.1, then their page in
        # your browser talks to this server. The Host header is what gives it away.
        assert "attacker.com" not in server.ALLOWED_HOSTS
        assert "0.0.0.0" not in server.ALLOWED_HOSTS


class TestLoggingSurvivesHavingNoStderr:
    """Under pythonw there is no console and sys.stderr is None.

    An unguarded write then raises *inside the request handler*: the port keeps
    listening while every response dies mid-flight, so it looks healthy right up
    until you load the page. MrW hit exactly this.
    """

    def test_log_does_not_raise_when_stderr_is_none(self, monkeypatch):
        monkeypatch.setattr(sys, "stderr", None)
        server._log("this must not raise")

    def test_log_does_not_raise_when_stderr_is_closed(self, monkeypatch):
        class Closed:
            def write(self, _):
                raise ValueError("I/O operation on closed file")

            def flush(self):
                pass

        monkeypatch.setattr(sys, "stderr", Closed())
        server._log("nor this")

    def test_it_still_writes_when_stderr_works(self, capsys):
        server._log("hello")
        assert "hello" in capsys.readouterr().err
