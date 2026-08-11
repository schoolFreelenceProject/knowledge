from typing import Literal

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: int
    filename: str
    file_type: str
    storage_path: str
    file_hash: str
    status: str
    extracted_blocks: int = Field(..., ge=0)
    chunks: int = Field(..., ge=0)
    embeddings: int = Field(..., ge=0)
    collection_name: str
    stored_vectors: int = Field(..., ge=0)
    saved_chunks: int = Field(..., ge=0)
    vector_size: int | None
    already_indexed: bool = False
    message: str | None = None


FolderIngestFileStatus = Literal["indexed", "skipped", "failed"]


class FolderIngestFileResult(BaseModel):
    relative_path: str
    status: FolderIngestFileStatus
    document_id: int | None = None
    filename: str | None = None
    file_type: str | None = None
    chunks: int = Field(default=0, ge=0)
    stored_vectors: int = Field(default=0, ge=0)
    reason: str | None = None
    message: str | None = None


class FolderIngestResponse(BaseModel):
    folder_name: str
    files_discovered: int = Field(..., ge=0)
    indexed: int = Field(..., ge=0)
    skipped: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    results: list[FolderIngestFileResult]
