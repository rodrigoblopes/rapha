"""Configuration, read from %RAPHA_HOME%\\.env.

No python-dotenv: the format is KEY=VALUE and parsing it is a dozen lines, which is
cheaper than another dependency (CLAUDE.md, tech stack).

Real environment variables win over the file, so a one-off override never means
editing config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / ".rapha"


class ConfigError(RuntimeError):
    """Configuration that cannot be safely used."""


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _looks_synced(path: Path) -> bool:
    """Is this path inside a cloud-sync root?

    ADR-002 exists because the repo is inside OneDrive. If RAPHA_HOME were also
    inside it, every token, every metric and every body photo would sync to
    Microsoft's cloud — and a rule that is only written down is a rule that gets
    broken during a hurried reinstall. So it is checked, not just documented.
    """
    parts = [p.lower() for p in path.resolve().parts]
    return any(
        marker in part
        for part in parts
        for marker in ("onedrive", "dropbox", "google drive", "icloud")
    )


@dataclass(frozen=True, slots=True)
class Config:
    home: Path
    garmin_email: str | None
    token_store: Path
    protocol_dir: Path
    course_dir: Path | None
    athlete_height_mm: int | None
    athlete_birth_year: int | None
    athlete_sex: str
    deficit_bps: int
    protein_g_per_kg_x10: int
    tdee_window_days: int
    portal_port: int

    @property
    def db_path(self) -> Path:
        return self.home / "rapha.db"

    @property
    def dist_dir(self) -> Path:
        return self.home / "dist"

    @property
    def photos_dir(self) -> Path:
        return self.home / "data" / "photos"


def _int_or_none(raw: str | None) -> int | None:
    return int(raw) if raw not in (None, "") else None


def load(home: Path | None = None, *, allow_synced_home: bool = False) -> Config:
    home = Path(home or os.environ.get("RAPHA_HOME") or DEFAULT_HOME)

    if _looks_synced(home) and not allow_synced_home:
        raise ConfigError(
            f"RAPHA_HOME is inside a cloud-sync folder: {home}\n"
            "That would sync your Garmin tokens, your health data and your body "
            "photos to a third party. Point RAPHA_HOME somewhere outside it "
            f"(the default {DEFAULT_HOME} is fine). See DECISIONS.md ADR-002."
        )

    file_values = _parse_env_file(home / ".env")

    def get(key: str, default: str | None = None) -> str | None:
        return os.environ.get(key) or file_values.get(key) or default

    token_store = get("GARMIN_TOKEN_STORE")
    protocol_dir = get("PROTOCOL_DIR")
    course_dir = get("COURSE_DIR")

    return Config(
        home=home,
        garmin_email=get("GARMIN_EMAIL"),
        token_store=Path(token_store) if token_store else home / "garmin_tokens",
        protocol_dir=Path(protocol_dir) if protocol_dir else home / "protocol",
        course_dir=Path(course_dir) if course_dir else None,
        athlete_height_mm=_int_or_none(get("ATHLETE_HEIGHT_MM")),
        athlete_birth_year=_int_or_none(get("ATHLETE_BIRTH_YEAR")),
        athlete_sex=(get("ATHLETE_SEX") or "M").upper(),
        deficit_bps=int(get("DEFICIT_BPS", "1750")),
        protein_g_per_kg_x10=int(get("PROTEIN_G_PER_KG_X10", "19")),
        tdee_window_days=int(get("TDEE_WINDOW_DAYS", "21")),
        portal_port=int(get("PORTAL_PORT", "8766")),
    )
