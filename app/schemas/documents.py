from typing import Literal

from pydantic import BaseModel, Field


ContentType = Literal["document", "code"]
DocumentFileType = Literal["pdf", "markdown", "code"]


class DocumentMetadata(BaseModel):
    filename: str = Field(..., description="Original file name.")
    source_path: str = Field(..., description="Path relative to the documents directory.")
    file_type: DocumentFileType
    content_type: ContentType = Field(
        default="document",
        description="High-level content type for unified document/code retrieval.",
    )
    page_number: int | None = Field(
        default=None,
        description="One-based PDF page number. Markdown files do not have pages.",
    )
    repo_name: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    language: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    repository_file_path: str | None = None


class ExtractedDocument(BaseModel):
    text: str
    metadata: DocumentMetadata


class ChunkMetadata(DocumentMetadata):
    chunk_index: int = Field(..., description="One-based chunk index per source block.")
    start_char: int = Field(..., description="Start character offset in extracted text.")
    end_char: int = Field(..., description="Exclusive end character offset in extracted text.")


class DocumentChunk(BaseModel):
    text: str
    metadata: ChunkMetadata


class EmbeddedChunk(BaseModel):
    vector: list[float] = Field(..., description="Dense embedding vector for the chunk text.")
    text: str
    metadata: ChunkMetadata


class RetrievalResult(BaseModel):
    text: str
    filename: str
    page_number: int | None
    score: float
    content_type: ContentType = "document"
    vector_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None
    metadata: ChunkMetadata


class AnswerSource(BaseModel):
    filename: str
    page_number: int | None
    score: float


class GeneratedAnswer(BaseModel):
    answer: str
    sources: list[AnswerSource]
