from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db.models import RAGFeedbackRecord, RAGTraceRecord


class RAGFeedbackServiceError(RuntimeError):
    """Raised when RAG feedback handling fails."""


class RAGFeedbackPersistenceError(RAGFeedbackServiceError):
    """Raised when RAG feedback cannot be read or written."""


class RAGFeedbackTargetNotFoundError(RAGFeedbackServiceError):
    """Raised when feedback references a missing trace."""


@dataclass(frozen=True)
class StoredRAGFeedback:
    id: int
    trace_id: int
    request_id: str
    user_id: int
    rating: int
    comment: str | None
    created_at: datetime


@dataclass(frozen=True)
class RAGFeedbackList:
    items: list[StoredRAGFeedback]
    total: int
    limit: int
    offset: int


class RAGFeedbackService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def submit_feedback(
        self,
        request_id: str,
        user_id: int,
        rating: int,
        comment: str | None = None,
    ) -> StoredRAGFeedback:
        if rating < 1 or rating > 5:
            raise RAGFeedbackServiceError("rating must be between 1 and 5.")

        try:
            self.init_database()
            with self.session_factory() as session:
                trace = _get_newest_trace_by_request_id(
                    session=session,
                    request_id=request_id,
                )
                feedback = RAGFeedbackRecord(
                    trace_id=trace.id,
                    user_id=user_id,
                    rating=rating,
                    comment=_normalize_comment(comment),
                )
                session.add(feedback)
                session.flush()
                stored_feedback = _to_stored_feedback(
                    feedback=feedback,
                    request_id=trace.request_id,
                )
                session.commit()
                return stored_feedback
        except RAGFeedbackTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RAGFeedbackPersistenceError(
                f"Failed to save RAG feedback: {exc}"
            ) from exc

    def list_feedback(
        self,
        limit: int,
        offset: int,
        user_id: int | None = None,
        rating: int | None = None,
        request_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> RAGFeedbackList:
        try:
            self.init_database()
            with self.session_factory() as session:
                filters = _build_feedback_filters(
                    user_id=user_id,
                    rating=rating,
                    request_id=request_id,
                    created_from=created_from,
                    created_to=created_to,
                )
                total = session.scalar(
                    select(func.count())
                    .select_from(RAGFeedbackRecord)
                    .join(RAGTraceRecord)
                    .where(*filters)
                )
                records = session.scalars(
                    select(RAGFeedbackRecord)
                    .join(RAGTraceRecord)
                    .options(selectinload(RAGFeedbackRecord.trace))
                    .where(*filters)
                    .order_by(
                        RAGFeedbackRecord.created_at.desc(),
                        RAGFeedbackRecord.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                ).all()
                return RAGFeedbackList(
                    items=[
                        _to_stored_feedback_from_record(record)
                        for record in records
                    ],
                    total=int(total or 0),
                    limit=limit,
                    offset=offset,
                )
        except SQLAlchemyError as exc:
            raise RAGFeedbackPersistenceError(
                f"Failed to list RAG feedback: {exc}"
            ) from exc


def _get_newest_trace_by_request_id(
    session: Session,
    request_id: str,
) -> RAGTraceRecord:
    trace = session.scalars(
        select(RAGTraceRecord)
        .where(RAGTraceRecord.request_id == request_id)
        .order_by(
            RAGTraceRecord.created_at.desc(),
            RAGTraceRecord.id.desc(),
        )
        .limit(1)
    ).one_or_none()
    if trace is None:
        raise RAGFeedbackTargetNotFoundError(
            f"RAG trace not found for request_id: {request_id}"
        )

    return trace


def _build_feedback_filters(
    user_id: int | None,
    rating: int | None,
    request_id: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    filters = []
    if user_id is not None:
        filters.append(RAGFeedbackRecord.user_id == user_id)

    if rating is not None:
        filters.append(RAGFeedbackRecord.rating == rating)

    if request_id is not None:
        filters.append(RAGTraceRecord.request_id == request_id)

    if created_from is not None:
        filters.append(RAGFeedbackRecord.created_at >= created_from)

    if created_to is not None:
        filters.append(RAGFeedbackRecord.created_at <= created_to)

    return filters


def _normalize_comment(comment: str | None) -> str | None:
    if comment is None:
        return None

    normalized_comment = comment.strip()
    if not normalized_comment:
        return None

    return normalized_comment


def _to_stored_feedback_from_record(
    record: RAGFeedbackRecord,
) -> StoredRAGFeedback:
    return _to_stored_feedback(
        feedback=record,
        request_id=record.trace.request_id,
    )


def _to_stored_feedback(
    feedback: RAGFeedbackRecord,
    request_id: str,
) -> StoredRAGFeedback:
    return StoredRAGFeedback(
        id=feedback.id,
        trace_id=feedback.trace_id,
        request_id=request_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )
