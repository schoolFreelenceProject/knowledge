"""baseline current knowledge base schema

Revision ID: 0001_baseline_current_schema
Revises:
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_baseline_current_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path", name="uq_documents_storage_path"),
    )

    op.create_table(
        "code_repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repo_url", sa.String(length=2048), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repo_url",
            "branch",
            "commit_sha",
            name="uq_code_repositories_source_revision",
        ),
        sa.UniqueConstraint(
            "storage_path",
            name="uq_code_repositories_storage_path",
        ),
    )

    op.create_table(
        "rag_traces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=32), nullable=False),
        sa.Column("retrieval_time_ms", sa.Float(), nullable=True),
        sa.Column("reranker_time_ms", sa.Float(), nullable=True),
        sa.Column("generation_time_ms", sa.Float(), nullable=True),
        sa.Column("total_time_ms", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("retrieved_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("retrieved_sources", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_traces_request_id", "rag_traces", ["request_id"])
    op.create_index("ix_rag_traces_user_id", "rag_traces", ["user_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_position",
        ),
        sa.UniqueConstraint(
            "qdrant_point_id",
            name="uq_document_chunks_qdrant_point_id",
        ),
    )

    op.create_table(
        "document_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_permissions_document_user",
        ),
    )

    op.create_table(
        "code_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["code_repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_id",
            "file_path",
            name="uq_code_files_repository_path",
        ),
    )

    op.create_table(
        "code_repository_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["code_repositories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_id",
            "user_id",
            name="uq_code_repository_permissions_repository_user",
        ),
    )

    op.create_table(
        "rag_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trace_id"],
            ["rag_traces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_feedback_rating", "rag_feedback", ["rating"])
    op.create_index("ix_rag_feedback_trace_id", "rag_feedback", ["trace_id"])
    op.create_index("ix_rag_feedback_user_id", "rag_feedback", ["user_id"])

    op.create_table(
        "code_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("code_file_id", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("symbol_name", sa.String(length=512), nullable=True),
        sa.Column("symbol_kind", sa.String(length=64), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["code_file_id"],
            ["code_files.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["code_repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_id",
            "code_file_id",
            "chunk_index",
            name="uq_code_chunks_position",
        ),
        sa.UniqueConstraint(
            "qdrant_point_id",
            name="uq_code_chunks_qdrant_point_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("code_chunks")
    op.drop_index("ix_rag_feedback_user_id", table_name="rag_feedback")
    op.drop_index("ix_rag_feedback_trace_id", table_name="rag_feedback")
    op.drop_index("ix_rag_feedback_rating", table_name="rag_feedback")
    op.drop_table("rag_feedback")
    op.drop_table("code_repository_permissions")
    op.drop_table("code_files")
    op.drop_table("document_permissions")
    op.drop_table("document_chunks")
    op.drop_index("ix_rag_traces_user_id", table_name="rag_traces")
    op.drop_index("ix_rag_traces_request_id", table_name="rag_traces")
    op.drop_table("rag_traces")
    op.drop_table("code_repositories")
    op.drop_table("documents")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
