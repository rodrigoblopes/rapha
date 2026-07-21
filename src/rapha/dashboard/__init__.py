"""The portal. Renders to %RAPHA_HOME%/dist and is served on 127.0.0.1.

⚠️ Holds no credential and must never import `rapha.garmin` (ADR-001). It reads
SQLite and the extracted protocol; nothing here authenticates to anything.
"""
