"""Book catalogue (`content_catalog_books`).

Revision ID: 0003_catalog_books
Revises: 0002_parent
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_catalog_books"
down_revision: str | Sequence[str] | None = "0002_parent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_catalog_books",
        sa.Column("book_id", sa.Text, primary_key=True),
        sa.Column("edition", sa.Text, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("volume", sa.Integer, nullable=False),
        sa.Column("title_vi", sa.Text, nullable=False),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("grade BETWEEN 1 AND 5", name="ck_content_catalog_books_grade"),
        sa.CheckConstraint(
            "edition IN ('2020', '2024-25')", name="ck_content_catalog_books_edition"
        ),
        sa.CheckConstraint("page_count > 0", name="ck_content_catalog_books_page_count"),
        sa.CheckConstraint("file_size > 0", name="ck_content_catalog_books_file_size"),
        sa.UniqueConstraint("source_path", name="uq_content_catalog_books_source_path"),
    )


def downgrade() -> None:
    op.drop_table("content_catalog_books")
