from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MCPContentType = Literal["all", "document", "code"]


class MCPCodeMetadata(BaseModel):
    repo: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    language: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    start_line: int | None = None
    end_line: int | None = None


class MCPDocumentMetadata(BaseModel):
    page_number: int | None = None
    chunk_index: int
    start_char: int
    end_char: int


class MCPSearchResult(BaseModel):
    text: str
    source_type: Literal["document", "code"]
    filename: str
    source_path: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None
    document_metadata: MCPDocumentMetadata
    code_metadata: MCPCodeMetadata | None = None


class MCPSearchKnowledgeResponse(BaseModel):
    request_id: str
    results: list[MCPSearchResult]


class MCPAskKnowledgeSource(BaseModel):
    filename: str
    page_number: int | None
    score: float


class MCPAskKnowledgeResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[MCPAskKnowledgeSource]


class MCPDocumentChunkDetail(BaseModel):
    id: int
    qdrant_point_id: str
    chunk_index: int
    page_number: int | None
    start_char: int
    end_char: int
    created_at: datetime


class MCPDocumentDetail(BaseModel):
    request_id: str
    id: int
    filename: str
    file_type: str
    storage_path: str
    file_hash: str
    status: str
    created_at: datetime
    updated_at: datetime
    chunk_count: int = Field(..., ge=0)
    chunks: list[MCPDocumentChunkDetail]


class MCPSearchCodeResponse(BaseModel):
    request_id: str
    results: list[MCPSearchResult]
