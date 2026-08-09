from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.schemas.documents import RetrievalResult


TRACE_STATUS_PROCESSING = "PROCESSING"
TRACE_STATUS_SUCCESS = "SUCCESS"
TRACE_STATUS_ERROR = "ERROR"


@dataclass
class RAGTraceContext:
    request_id: str
    user_id: int | None
    question: str
    retrieval_mode: str
    model_name: str
    started_at: float = field(default_factory=perf_counter)
    retrieval_time_ms: float | None = None
    reranker_time_ms: float | None = None
    generation_time_ms: float | None = None
    total_time_ms: float | None = None
    retrieved_count: int = 0
    retrieved_sources: list[dict[str, Any]] = field(default_factory=list)
    status: str = TRACE_STATUS_PROCESSING
    error_message: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def add_timing(self, field_name: str, elapsed_ms: float) -> None:
        current_value = getattr(self, field_name)
        if current_value is None:
            setattr(self, field_name, _round_ms(elapsed_ms))
            return

        setattr(self, field_name, _round_ms(current_value + elapsed_ms))

    def record_retrieved_sources(
        self,
        retrieval_results: list[RetrievalResult],
    ) -> None:
        self.retrieved_count = len(retrieval_results)
        self.retrieved_sources = [
            {
                "content_type": result.metadata.content_type,
                "file_type": result.metadata.file_type,
                "filename": result.filename,
                "source_path": result.metadata.source_path,
                "page_number": result.page_number,
                "chunk_index": result.metadata.chunk_index,
                "repo_name": result.metadata.repo_name,
                "repo_url": result.metadata.repo_url,
                "branch": result.metadata.branch,
                "commit_sha": result.metadata.commit_sha,
                "language": result.metadata.language,
                "symbol_name": result.metadata.symbol_name,
                "symbol_kind": result.metadata.symbol_kind,
                "start_line": result.metadata.start_line,
                "end_line": result.metadata.end_line,
                "repository_file_path": result.metadata.repository_file_path,
                "score": result.score,
                "vector_score": result.vector_score,
                "bm25_score": result.bm25_score,
                "fusion_score": result.fusion_score,
                "reranker_score": result.reranker_score,
            }
            for result in retrieval_results
        ]

    def finish_success(self) -> None:
        self.status = TRACE_STATUS_SUCCESS
        self.error_message = None
        self.total_time_ms = _round_ms(_elapsed_ms(self.started_at))

    def finish_error(self, error_message: str) -> None:
        self.status = TRACE_STATUS_ERROR
        self.error_message = error_message
        self.total_time_ms = _round_ms(_elapsed_ms(self.started_at))


_current_trace_context: ContextVar[RAGTraceContext | None] = ContextVar(
    "rag_trace_context",
    default=None,
)


def generate_request_id() -> str:
    return str(uuid4())


def get_current_trace_context() -> RAGTraceContext | None:
    return _current_trace_context.get()


def set_current_trace_context(
    trace_context: RAGTraceContext,
) -> Token[RAGTraceContext | None]:
    return _current_trace_context.set(trace_context)


def reset_current_trace_context(token: Token[RAGTraceContext | None]) -> None:
    _current_trace_context.reset(token)


@contextmanager
def trace_timer(field_name: str):
    started_at = perf_counter()
    try:
        yield
    finally:
        trace_context = get_current_trace_context()
        if trace_context is not None:
            trace_context.add_timing(
                field_name=field_name,
                elapsed_ms=_elapsed_ms(started_at),
            )


def _elapsed_ms(started_at: float) -> float:
    return (perf_counter() - started_at) * 1000


def _round_ms(value: float) -> float:
    return round(value, 3)
