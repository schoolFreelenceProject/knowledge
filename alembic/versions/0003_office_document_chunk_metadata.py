"""add office document chunk metadata

Revision ID: 0003_office_chunk_metadata
Revises: 0002_code_source_types
Create Date: 2026-08-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_office_chunk_metadata"
down_revision: str | Sequence[str] | None = "0002_code_source_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("section_heading", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("heading_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("block_kind", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("workbook", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("cell_range", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("row_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("row_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("slide_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("slide_title", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "slide_title")
    op.drop_column("document_chunks", "slide_number")
    op.drop_column("document_chunks", "row_end")
    op.drop_column("document_chunks", "row_start")
    op.drop_column("document_chunks", "cell_range")
    op.drop_column("document_chunks", "sheet_name")
    op.drop_column("document_chunks", "workbook")
    op.drop_column("document_chunks", "block_kind")
    op.drop_column("document_chunks", "heading_path")
    op.drop_column("document_chunks", "section_heading")
