"""Readers — the only layer that touches SQLite/JSON. Return domain objects.

Stages never open files, run SQL, or parse JSON directly (spec §4.2).
"""
