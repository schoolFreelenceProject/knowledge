from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CodeSourceTypeValue = Literal["GIT_REPOSITORY", "LOCAL_FOLDER"]


DEFAULT_CODE_INCLUDE_GLOBS = [
    "**/*.py",
    "**/*.js",
    "**/*.jsx",
    "**/*.ts",
    "**/*.tsx",
    "**/*.java",
    "**/*.go",
    "**/*.rs",
    "**/*.c",
    "**/*.h",
    "**/*.cpp",
    "**/*.hpp",
    "**/*.php",
    "**/*.md",
    "**/*.markdown",
]
DEFAULT_CODE_EXCLUDE_GLOBS = [
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
    "**/vendor/**",
    "**/dist/**",
    "**/build/**",
    "**/generated/**",
    "**/out/**",
    "**/target/**",
    "**/tmp/**",
    "**/temp/**",
    "**/__pycache__/**",
    "**/.cache/**",
    "**/coverage/**",
    "**/storage/**",
    "**/bootstrap/cache/**",
]


class CodeIngestRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)
    branch: str = Field(default="main", min_length=1)
    include_globs: list[str] = Field(default_factory=lambda: DEFAULT_CODE_INCLUDE_GLOBS.copy())
    exclude_globs: list[str] = Field(default_factory=lambda: DEFAULT_CODE_EXCLUDE_GLOBS.copy())

    model_config = {"extra": "allow"}


class CodeIngestResponse(BaseModel):
    repository_id: int
    repo_name: str
    source_type: CodeSourceTypeValue = "GIT_REPOSITORY"
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    source_fingerprint: str | None = None
    storage_path: str
    status: str
    files: int = Field(..., ge=0)
    chunks: int = Field(..., ge=0)
    embeddings: int = Field(..., ge=0)
    collection_name: str
    stored_vectors: int = Field(..., ge=0)
    saved_chunks: int = Field(..., ge=0)
    vector_size: int | None
    skipped_files: int = Field(default=0, ge=0)
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    already_indexed: bool = False
    recovered: bool = False
    message: str | None = None

    model_config = {"extra": "allow"}


class CodeRepositorySummary(BaseModel):
    id: int
    repo_name: str
    source_type: CodeSourceTypeValue = "GIT_REPOSITORY"
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    source_fingerprint: str | None = None
    storage_path: str
    status: str
    created_at: datetime
    updated_at: datetime
    file_count: int = Field(..., ge=0)
    chunk_count: int = Field(..., ge=0)


class CodeFileDetail(BaseModel):
    id: int
    file_path: str
    language: str
    file_hash: str
    size_bytes: int = Field(..., ge=0)
    created_at: datetime
    chunk_count: int = Field(..., ge=0)


class CodeChunkDetail(BaseModel):
    id: int
    code_file_id: int
    qdrant_point_id: str
    chunk_index: int
    symbol_name: str | None = None
    symbol_kind: str | None = None
    start_line: int
    end_line: int
    start_char: int
    end_char: int
    created_at: datetime


class CodeRepositoryDetail(CodeRepositorySummary):
    files: list[CodeFileDetail]
    chunks: list[CodeChunkDetail]


class DeleteCodeRepositoryResponse(BaseModel):
    repository_id: int
    deleted_vectors: int = Field(..., ge=0)
    deleted_metadata: bool
    deleted_files: bool
    cleanup_warning: str | None = None


class ReindexCodeRepositoryResponse(BaseModel):
    repository_id: int
    status: str
    files: int = Field(..., ge=0)
    chunks: int = Field(..., ge=0)
    stored_vectors: int = Field(..., ge=0)
    replaced_vectors: int = Field(..., ge=0)
    skipped_files: int = Field(default=0, ge=0)
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    cleanup_warning: str | None = None
