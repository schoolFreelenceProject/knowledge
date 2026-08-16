from typing import Literal

from pydantic import BaseModel, Field


KnowledgeSearchMode = Literal["all", "documents", "code"]
KnowledgeContentType = Literal["document", "code"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: KnowledgeSearchMode = "all"
    content_types: list[KnowledgeContentType] | None = None
    document_ids: list[int] = Field(default_factory=list)
    repository_ids: list[int] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)


class KnowledgeSourceInspection(BaseModel):
    text: str
    context_start_line: int | None = None
    context_end_line: int | None = None
    highlight_start_line: int | None = None
    highlight_end_line: int | None = None


class KnowledgeSearchResult(BaseModel):
    point_id: str
    content_type: KnowledgeContentType
    title: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None
    preview: str
    inspection: KnowledgeSourceInspection

    document_id: int | None = None
    filename: str | None = None
    source_path: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    heading_path: str | None = None
    block_kind: str | None = None
    workbook: str | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    slide_number: int | None = None
    slide_title: str | None = None
    chunk_index: int

    repository_id: int | None = None
    repo_name: str | None = None
    source_type: str | None = None
    file_path: str | None = None
    language: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    start_line: int | None = None
    end_line: int | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    mode: KnowledgeSearchMode
    top_k: int
    retrieval_mode: str
    results: list[KnowledgeSearchResult]
