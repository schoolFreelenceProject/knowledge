from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExpectedSource(BaseModel):
    filename: str = Field(..., min_length=1)
    page_number: int | None = None
    source_path: str | None = None
    content_type: str | None = None
    symbol_name: str | None = None

    model_config = ConfigDict(extra="allow")


class EvaluationCase(BaseModel):
    id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    expected_sources: list[ExpectedSource] = Field(default_factory=list)
    expected_answer_contains: list[str] = Field(default_factory=list)
    top_k: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class EvaluationDataset(BaseModel):
    version: int = 1
    name: str | None = None
    cases: list[EvaluationCase]
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class RetrievedDocument(BaseModel):
    rank: int
    content_type: str = "document"
    filename: str
    source_path: str
    file_type: str | None = None
    page_number: int | None
    chunk_index: int
    language: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None


class RetrievalScore(BaseModel):
    hit: bool
    expected_source_rank: int | None = None
    best_expected_source_score: float | None = None


class AnswerScore(BaseModel):
    expected_keywords_found: int
    expected_keywords_total: int
    coverage: float | None
    found_keywords: list[str]
    missing_keywords: list[str]


class FeedbackMetrics(BaseModel):
    feedback_count: int = Field(..., ge=0)
    average_user_rating: float | None = None
    bad_answer_rate: float | None = None
    good_answer_rate: float | None = None

    model_config = ConfigDict(extra="allow")


class EvaluationCaseResult(BaseModel):
    id: str
    question: str
    expected_sources: list[ExpectedSource]
    retrieved_documents: list[RetrievedDocument]
    retrieval_score: RetrievalScore
    answer_output: str
    answer_score: AnswerScore


class EvaluationSummary(BaseModel):
    total_cases: int
    retrieval_hit_rate: float
    average_expected_source_rank: float | None
    average_best_source_score: float | None
    answer_keyword_coverage_rate: float | None
    feedback_count: int | None = None
    average_user_rating: float | None = None
    bad_answer_rate: float | None = None
    good_answer_rate: float | None = None


class EvaluationReport(BaseModel):
    generated_at: datetime
    summary: EvaluationSummary
    cases: list[EvaluationCaseResult]
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")
