"""`parent_*` tables. Only `hoctap.parent` writes them."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, Text

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
    CheckConstraint("grade BETWEEN 1 AND 5", name="ck_parent_profiles_grade"),
)
