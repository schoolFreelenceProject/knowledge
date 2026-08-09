from datetime import datetime
from pydantic import BaseModel, Field


class TraceSource(BaseModel):
    filename: str | None = None
    source_path: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None

    model_config = {"extra": "allow"}


class TraceRecord(BaseModel):
    id: int
    request_id: str
    user_id: int | None
    question: str
    retrieval_mode: str
    retrieval_time_ms: float | None
    reranker_time_ms: float | None
    generation_time_ms: float | None
    total_time_ms: float | None
    model_name: str
    retrieved_count: int
    status: str
    error_message: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    retrieved_sources: list[TraceSource] = Field(default_factory=list)
    created_at: datetime

    model_config = {"extra": "allow"}


class TraceListResponse(BaseModel):
    items: list[TraceRecord]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

    model_config = {"extra": "allow"}
