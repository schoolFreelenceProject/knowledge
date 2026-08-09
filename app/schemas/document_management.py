from datetime import datetime

from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    id: int
    filename: str
    file_type: str
    storage_path: str
    file_hash: str
    status: str
    created_at: datetime
    updated_at: datetime
    chunk_count: int = Field(..., ge=0)


class DocumentChunkDetail(BaseModel):
    id: int
    qdrant_point_id: str
    chunk_index: int
    page_number: int | None
    start_char: int
    end_char: int
    created_at: datetime


class DocumentDetail(DocumentSummary):
    chunks: list[DocumentChunkDetail]


class DeleteDocumentResponse(BaseModel):
    document_id: int
    deleted_vectors: int = Field(..., ge=0)
    deleted_metadata: bool
    deleted_file: bool
    cleanup_warning: str | None = None


class ReindexDocumentResponse(BaseModel):
    document_id: int
    status: str
    chunks: int = Field(..., ge=0)
    stored_vectors: int = Field(..., ge=0)
    replaced_vectors: int = Field(..., ge=0)
    cleanup_warning: str | None = None
