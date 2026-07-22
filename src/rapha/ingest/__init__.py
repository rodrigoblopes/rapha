"""Ingest adapters. Each converts a source into canonical records for the store.

The rules engine never sees which adapter produced a record — that seam is what
lets a manual export stand in for the API without anything downstream noticing.
"""
