from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import RAGTraceRecord
from app.services.trace_context import RAGTraceContext


class RAGTracePersistenceError(RuntimeError):
    """Raised when RAG trace persistence fails."""


class RAGTraceNotFoundError(RAGTracePersistenceError):
    """Raised when a requested RAG trace row does not exist."""


@dataclass(frozen=True)
class StoredRAGTrace:
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
    retrieved_sources: list[dict[str, Any]]
    created_at: datetime


@dataclass(frozen=True)
class RAGTraceList:
    items: list[StoredRAGTrace]
    total: int
    limit: int
    offset: int


class RAGTraceService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def save_trace(self, trace_context: RAGTraceContext) -> StoredRAGTrace:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = RAGTraceRecord(
                    request_id=trace_context.request_id,
                    user_id=trace_context.user_id,
                    question=trace_context.question,
                    retrieval_mode=trace_context.retrieval_mode,
                    retrieval_time_ms=trace_context.retrieval_time_ms,
                    reranker_time_ms=trace_context.reranker_time_ms,
                    generation_time_ms=trace_context.generation_time_ms,
                    total_time_ms=trace_context.total_time_ms,
                    model_name=trace_context.model_name,
                    retrieved_count=trace_context.retrieved_count,
                    status=trace_context.status,
                    error_message=trace_context.error_message,
                    prompt_tokens=trace_context.prompt_tokens,
                    completion_tokens=trace_context.completion_tokens,
                    retrieved_sources=trace_context.retrieved_sources,
                )
                session.add(record)
                session.commit()
                return _to_stored_rag_trace(record)
        except SQLAlchemyError as exc:
            raise RAGTracePersistenceError(
                f"Failed to save RAG trace: {exc}"
            ) from exc

    def list_traces(
        self,
        limit: int,
        offset: int,
        user_id: int | None = None,
        status: str | None = None,
        retrieval_mode: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> RAGTraceList:
        try:
            self.init_database()
            with self.session_factory() as session:
                filters = _build_trace_filters(
                    user_id=user_id,
                    status=status,
                    retrieval_mode=retrieval_mode,
                    created_from=created_from,
                    created_to=created_to,
                )
                total = session.scalar(
                    select(func.count())
                    .select_from(RAGTraceRecord)
                    .where(*filters)
                )
                records = session.scalars(
                    select(RAGTraceRecord)
                    .where(*filters)
                    .order_by(
                        RAGTraceRecord.created_at.desc(),
                        RAGTraceRecord.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                ).all()
                return RAGTraceList(
                    items=[_to_stored_rag_trace(record) for record in records],
                    total=int(total or 0),
                    limit=limit,
                    offset=offset,
                )
        except SQLAlchemyError as exc:
            raise RAGTracePersistenceError(
                f"Failed to list RAG traces: {exc}"
            ) from exc

    def get_trace_by_request_id(self, request_id: str) -> StoredRAGTrace:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = session.scalars(
                    select(RAGTraceRecord)
                    .where(RAGTraceRecord.request_id == request_id)
                    .order_by(
                        RAGTraceRecord.created_at.desc(),
                        RAGTraceRecord.id.desc(),
                    )
                    .limit(1)
                ).one_or_none()
                if record is None:
                    raise RAGTraceNotFoundError(
                        f"RAG trace not found for request_id: {request_id}"
                    )

                return _to_stored_rag_trace(record)
        except RAGTraceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RAGTracePersistenceError(
                f"Failed to read RAG trace: {exc}"
            ) from exc


def _build_trace_filters(
    user_id: int | None,
    status: str | None,
    retrieval_mode: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    filters = []
    if user_id is not None:
        filters.append(RAGTraceRecord.user_id == user_id)

    if status is not None:
        filters.append(RAGTraceRecord.status == status)

    if retrieval_mode is not None:
        filters.append(RAGTraceRecord.retrieval_mode == retrieval_mode)

    if created_from is not None:
        filters.append(RAGTraceRecord.created_at >= created_from)

    if created_to is not None:
        filters.append(RAGTraceRecord.created_at <= created_to)

    return filters


def _to_stored_rag_trace(record: RAGTraceRecord) -> StoredRAGTrace:
    return StoredRAGTrace(
        id=record.id,
        request_id=record.request_id,
        user_id=record.user_id,
        question=record.question,
        retrieval_mode=record.retrieval_mode,
        retrieval_time_ms=record.retrieval_time_ms,
        reranker_time_ms=record.reranker_time_ms,
        generation_time_ms=record.generation_time_ms,
        total_time_ms=record.total_time_ms,
        model_name=record.model_name,
        retrieved_count=record.retrieved_count,
        status=record.status,
        error_message=record.error_message,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        retrieved_sources=record.retrieved_sources or [],
        created_at=record.created_at,
    )
