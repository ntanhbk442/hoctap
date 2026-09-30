"""`content_catalog_*` tables. Only `hoctap.content.catalog.service` writes them (AD-2).

- `content_catalog_books`: the fixed book list (`upsert_books()`).
- `content_catalog_units` / `content_catalog_lessons`: the book structure, keyed by the
  structural keys of the ProblemDoc (`publish_problems()`).
- `content_catalog_problems`: the published ProblemDocs (`publish_problems()`). A Problem
  is never deleted: one that vanished from a re-extracted Lesson gets `retired_at`.
- `content_catalog_concept_guides`: the generated Concept Guide per `concept_id` (Story 5.1,
  `upsert_concept_guide()`); Anh's edits are `content_review_guide_overrides`.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

content_catalog_books = Table(
    "content_catalog_books",
    metadata,
    Column("book_id", Text, primary_key=True),  # permanent, e.g. toan1-2020-q1
    Column("edition", Text, nullable=False),  # "2020" | "2024-25"
    Column("grade", Integer, nullable=False),
    Column("volume", Integer, nullable=False),
    Column("title_vi", Text, nullable=False),
    Column("source_path", Text, nullable=False),  # relative to source_dir, NFC, "/"-separated
    Column("page_count", Integer, nullable=False),
    Column("file_size", Integer, nullable=False),
    Column("fingerprint", Text, nullable=False),  # sha256 hex of the first 1 MB
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("grade BETWEEN 1 AND 5", name="ck_content_catalog_books_grade"),
    CheckConstraint("edition IN ('2020', '2024-25')", name="ck_content_catalog_books_edition"),
    CheckConstraint("page_count > 0", name="ck_content_catalog_books_page_count"),
    CheckConstraint("file_size > 0", name="ck_content_catalog_books_file_size"),
    UniqueConstraint("source_path", name="uq_content_catalog_books_source_path"),
)

content_catalog_units = Table(
    "content_catalog_units",
    metadata,
    Column("book_id", Text, ForeignKey("content_catalog_books.book_id"), nullable=False),
    Column("unit_key", Text, nullable=False),  # e.g. tuan03; u00 before the first heading
    Column("label", Text, nullable=False),  # as printed, e.g. "TUẦN 3"; may be empty
    Column("title", Text, nullable=False),  # may be empty
    Column("position", Integer, nullable=False),  # first page * 100 + order on that page
    PrimaryKeyConstraint("book_id", "unit_key", name="pk_content_catalog_units"),
)

content_catalog_lessons = Table(
    "content_catalog_lessons",
    metadata,
    Column("book_id", Text, ForeignKey("content_catalog_books.book_id"), nullable=False),
    Column("unit_key", Text, nullable=False),
    Column("lesson_key", Text, nullable=False),  # e.g. tiet2, phieu; l00 by default
    Column("label", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("is_quiz_sheet", Integer, nullable=False, server_default="0"),
    PrimaryKeyConstraint("book_id", "unit_key", "lesson_key", name="pk_content_catalog_lessons"),
    CheckConstraint("is_quiz_sheet IN (0, 1)", name="ck_content_catalog_lessons_quiz"),
)

content_catalog_problems = Table(
    "content_catalog_problems",
    metadata,
    Column("problem_id", Text, primary_key=True),  # {book_id}.{unit_key}.{lesson_key}.{label}
    Column("book_id", Text, ForeignKey("content_catalog_books.book_id"), nullable=False),
    Column("unit_key", Text, nullable=False),
    Column("lesson_key", Text, nullable=False),
    Column("position", Integer, nullable=False),  # page * 1000 + draft order on the page
    Column("doc_json", Text, nullable=False),  # the extracted ProblemDoc, canonical JSON
    Column("content_hash", Text, nullable=False),  # sha256 hex of doc_json
    Column("needs_review", Integer, nullable=False),  # copied from verify
    Column("verify_status", Text, nullable=False),  # agree | disagree | unverified
    Column("duplicate", Integer, nullable=False, server_default="0"),
    Column("source_page_first", Integer, nullable=False),
    Column("retired_at", Text, nullable=True),  # set when it vanished from its Lesson
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("needs_review IN (0, 1)", name="ck_content_catalog_problems_needs_review"),
    CheckConstraint("duplicate IN (0, 1)", name="ck_content_catalog_problems_duplicate"),
    CheckConstraint(
        "verify_status IN ('agree', 'disagree', 'unverified')",
        name="ck_content_catalog_problems_verify_status",
    ),
    Index("ix_content_catalog_problems_lesson", "book_id", "unit_key", "lesson_key"),
)

content_catalog_concept_guides = Table(
    "content_catalog_concept_guides",
    metadata,
    Column("concept_id", Text, primary_key=True),  # a curated Concept; never changes
    Column("body_json", Text, nullable=False),  # canonical ConceptGuideDoc JSON
    Column("source", Text, nullable=False),  # book | problems
    Column("input_hash", Text, nullable=False),  # the generation input; same input, no call
    Column("model", Text, nullable=False),
    Column("generated_at", Text, nullable=False),
    CheckConstraint(
        "source IN ('book', 'problems')", name="ck_content_catalog_concept_guides_source"
    ),
)
