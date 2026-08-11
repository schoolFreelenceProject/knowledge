from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, Enum):
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class CodeSourceType(str, Enum):
    GIT_REPOSITORY = "GIT_REPOSITORY"
    LOCAL_FOLDER = "LOCAL_FOLDER"


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    document_permissions: Mapped[list[DocumentPermissionRecord]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    code_repository_permissions: Mapped[
        list[CodeRepositoryPermissionRecord]
    ] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    rag_feedback: Mapped[list[RAGFeedbackRecord]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_path", name="uq_documents_storage_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentStatus.PROCESSING.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    chunks: Mapped[list[DocumentChunkRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    permissions: Mapped[list[DocumentPermissionRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunkRecord(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("qdrant_point_id", name="uq_document_chunks_qdrant_point_id"),
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    document: Mapped[DocumentRecord] = relationship(back_populates="chunks")


class DocumentPermissionRecord(Base):
    __tablename__ = "document_permissions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_permissions_document_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    document: Mapped[DocumentRecord] = relationship(back_populates="permissions")
    user: Mapped[UserRecord] = relationship(back_populates="document_permissions")


class CodeRepositoryRecord(Base):
    __tablename__ = "code_repositories"
    __table_args__ = (
        UniqueConstraint(
            "repo_url",
            "branch",
            "commit_sha",
            name="uq_code_repositories_source_revision",
        ),
        UniqueConstraint(
            "source_type",
            "repo_name",
            "source_fingerprint",
            name="uq_code_repositories_local_source_fingerprint",
        ),
        UniqueConstraint("storage_path", name="uq_code_repositories_storage_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(
        String(32),
        default=CodeSourceType.GIT_REPOSITORY.value,
        nullable=False,
    )
    repo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentStatus.PROCESSING.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    files: Mapped[list[CodeFileRecord]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list[CodeChunkRecord]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    permissions: Mapped[list[CodeRepositoryPermissionRecord]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class CodeFileRecord(Base):
    __tablename__ = "code_files"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "file_path",
            name="uq_code_files_repository_path",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    repository: Mapped[CodeRepositoryRecord] = relationship(back_populates="files")
    chunks: Mapped[list[CodeChunkRecord]] = relationship(
        back_populates="code_file",
        cascade="all, delete-orphan",
    )


class CodeChunkRecord(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        UniqueConstraint("qdrant_point_id", name="uq_code_chunks_qdrant_point_id"),
        UniqueConstraint(
            "repository_id",
            "code_file_id",
            "chunk_index",
            name="uq_code_chunks_position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_file_id: Mapped[int] = mapped_column(
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    symbol_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    repository: Mapped[CodeRepositoryRecord] = relationship(back_populates="chunks")
    code_file: Mapped[CodeFileRecord] = relationship(back_populates="chunks")


class CodeRepositoryPermissionRecord(Base):
    __tablename__ = "code_repository_permissions"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "user_id",
            name="uq_code_repository_permissions_repository_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    repository: Mapped[CodeRepositoryRecord] = relationship(
        back_populates="permissions"
    )
    user: Mapped[UserRecord] = relationship(
        back_populates="code_repository_permissions"
    )


class RAGTraceRecord(Base):
    __tablename__ = "rag_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reranker_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    retrieved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_sources: Mapped[list[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    feedback: Mapped[list[RAGFeedbackRecord]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
    )


class RAGFeedbackRecord(Base):
    __tablename__ = "rag_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[int] = mapped_column(
        ForeignKey("rag_traces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    trace: Mapped[RAGTraceRecord] = relationship(back_populates="feedback")
    user: Mapped[UserRecord] = relationship(back_populates="rag_feedback")
