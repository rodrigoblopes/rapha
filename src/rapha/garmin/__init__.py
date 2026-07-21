"""Garmin Connect access.

⚠️ This package is the ONLY place in Rapha that holds a credential, and the portal
must never import it (CLAUDE.md, ADR-001).

The split is deliberate:

    auth.py   mints and refreshes OAuth tokens. Never stores a password.
    read.py   pulls metrics and activities.
    write.py  creates, schedules and deletes WORKOUTS. Nothing else, ever.
"""
