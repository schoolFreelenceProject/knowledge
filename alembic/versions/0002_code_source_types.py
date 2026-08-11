"""support git and local code sources

Revision ID: 0002_code_source_types
Revises: 0001_baseline_current_schema
Create Date: 2026-08-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_code_source_types"
down_revision: str | Sequence[str] | None = "0001_baseline_current_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "code_repositories",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="GIT_REPOSITORY",
        ),
    )
    op.add_column(
        "code_repositories",
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
    )
    op.alter_column(
        "code_repositories",
        "repo_url",
        existing_type=sa.String(length=2048),
        nullable=True,
    )
    op.alter_column(
        "code_repositories",
        "branch",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "code_repositories",
        "commit_sha",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.create_unique_constraint(
        "uq_code_repositories_local_source_fingerprint",
        "code_repositories",
        ["source_type", "repo_name", "source_fingerprint"],
    )
    op.alter_column(
        "code_repositories",
        "source_type",
        existing_type=sa.String(length=32),
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_code_repositories_local_source_fingerprint",
        "code_repositories",
        type_="unique",
    )
    op.alter_column(
        "code_repositories",
        "commit_sha",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "code_repositories",
        "branch",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "code_repositories",
        "repo_url",
        existing_type=sa.String(length=2048),
        nullable=False,
    )
    op.drop_column("code_repositories", "source_fingerprint")
    op.drop_column("code_repositories", "source_type")
