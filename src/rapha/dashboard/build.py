"""Render the portal from the store — the one place that assembles and writes it.

Both `rapha report` and the server's upload endpoint need to (re)build the portal,
so the sequence lives here once: build the briefing, copy the referenced progress
photos into ``dist`` (which is inside ``%RAPHA_HOME%``, outside OneDrive, served on
localhost only), and write the HTML.

⚠️ Credential-free by construction. It imports only `briefing` and `portal`, which
read SQLite and files and never import `rapha.garmin`'s token holders — so the
server can call this without ever crossing the ADR-001 boundary.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def render(cfg) -> tuple[Path, dict]:
    """Build the briefing, stage its photos into dist, write the portal.

    Returns ``(portal_path, briefing)`` — the server ignores the briefing, the CLI
    reports a couple of its fields.
    """
    from . import briefing as briefing_mod
    from . import portal

    b = briefing_mod.build(cfg)

    src_root = cfg.photos_dir
    dst_root = cfg.dist_dir / "photos"
    if src_root.is_dir():
        for pset in b["progress"].get("photo_sets", []):
            src = src_root / pset["date"] / (pset.get("subdir") or "")
            dst = dst_root / pset["date"]
            dst.mkdir(parents=True, exist_ok=True)
            for img in pset["images"]:
                if (src / img).is_file():
                    shutil.copy2(src / img, dst / img)

    return portal.write(cfg.dist_dir, b), b
