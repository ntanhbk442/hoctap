"""`parent_*` tables. Only `hoctap.parent` writes them."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, Integer, MetaData, Table, Text, true

metadata = MetaData()

# A single row (id = 1) holding the family PIN hash and the brute-force counter.
parent_settings = Table(
    "parent_settings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("pin_hash", Text, nullable=False),
    Column("failed_attempts", Integer, nullable=False, server_default="0"),
    Column("locked_until", Text, nullable=True),
    # Signed into the parent cookie; logout increments it so old cookies stop working.
    Column("session_version", Integer, nullable=False, server_default="0"),
    # Story 7.2: a random token, regenerated after every restore; tablets stamp their
    # outbox events with it and the server refuses events stamped with an older one.
    Column("db_epoch", Text, nullable=False, server_default="0"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("id = 1", name="ck_parent_settings_single_row"),
)

parent_profiles = Table(
    "parent_profiles",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("name", Text, nullable=False),
    Column("avatar", Text, nullable=False),
    Column("grade", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    # Story 2.9: gates auto-playing a Problem's instruction on open. Default on for every
    # existing and new Profile -- no Parent-Area toggle ships with this story (see
    # spec-2-9's Boundaries & Constraints / deferred-work.md).
    Column("auto_play", Boolean, nullable=False, server_default=true()),
    CheckConstraint("grade BETWEEN 1 AND 5", name="ck_parent_profiles_grade"),
)
