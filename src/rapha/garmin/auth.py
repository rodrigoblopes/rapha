"""Garmin authentication. The only place a credential exists.

There is no legitimate personal Garmin API (ADR-001), so this runs on the unofficial
`garminconnect` client, which uses the same mobile SSO flow as Garmin's official
Android app.

**A password is never written to disk, and never held longer than one call.** It is
supplied once to `mint_tokens`, exchanged for OAuth tokens, and dropped. Everything
afterwards — every sync, every push — runs from the token store and refreshes itself.
`connect()` cannot fall back to a password even if one were available, because it
never receives one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from garminconnect import Garmin

from ..config import Config


class NotAuthenticated(RuntimeError):
    """No usable token store. `rapha login` has not been run, or tokens expired."""


def _has_tokens(token_store: Path) -> bool:
    return token_store.is_dir() and any(token_store.iterdir())


def mint_tokens(
    cfg: Config,
    password: str,
    *,
    mfa_prompt: Callable[[], str] | None = None,
) -> str:
    """Exchange email + password for OAuth tokens. Returns the display name.

    The password parameter is the only place one appears in Rapha, and it is not
    stored, logged, or returned.
    """
    if not cfg.garmin_email:
        raise NotAuthenticated(
            "GARMIN_EMAIL is not set. Add it to %RAPHA_HOME%\\.env "
            "(there is no password variable, and there will not be one)."
        )

    cfg.token_store.mkdir(parents=True, exist_ok=True)

    client = Garmin(
        email=cfg.garmin_email,
        password=password,
        prompt_mfa=mfa_prompt or _refuse_mfa,
    )
    client.login(tokenstore=str(cfg.token_store))
    return client.display_name or cfg.garmin_email


def connect(cfg: Config) -> Garmin:
    """A logged-in client, from tokens only.

    Deliberately takes no password argument. If the tokens are gone, the answer is
    to run `rapha login` — not for a background sync to reach for a credential.
    """
    if not _has_tokens(cfg.token_store):
        raise NotAuthenticated(
            f"No Garmin tokens in {cfg.token_store}. Run `rapha login` first."
        )

    client = Garmin()
    client.login(tokenstore=str(cfg.token_store))
    return client


def _refuse_mfa() -> str:
    raise NotAuthenticated(
        "Garmin asked for an MFA code, but this run has no way to ask you.\n"
        "Run `rapha login` from an interactive terminal."
    )


def file_mfa_prompt(path: Path, timeout_s: int = 900, poll_s: float = 2.0):
    """An MFA prompt that waits for a code to appear in a file.

    Garmin only asks for MFA *after* the password is accepted, and an authenticator
    code is valid for about thirty seconds. Prompting on a terminal means the login
    must already be running when you read the code — awkward when the login is
    driven by something that cannot type. Waiting on a file inverts that: start the
    login, and drop the code in whenever it is ready.

    The file is deleted as soon as it is read. A stale code left on disk would be
    silently reused on the next login and fail for a reason nobody would guess.
    """

    def prompt() -> str:
        import time

        deadline = time.monotonic() + timeout_s
        print(f"waiting for an MFA code in {path} ...", flush=True)
        while time.monotonic() < deadline:
            if path.is_file():
                code = path.read_text(encoding="utf-8").strip()
                if code:
                    path.unlink(missing_ok=True)
                    print("got it, resuming login", flush=True)
                    return code
            time.sleep(poll_s)
        raise NotAuthenticated(
            f"No MFA code appeared in {path} within {timeout_s}s."
        )

    return prompt
