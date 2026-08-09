from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import RAGFeedbackRecord, RAGTraceRecord
from app.schemas.evaluation import EvaluationCase, EvaluationDataset, FeedbackMetrics


class FeedbackEvaluationServiceError(RuntimeError):
    """Raised when feedback-aware evaluation data cannot be read."""


class FeedbackEvaluationService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def calculate_feedback_metrics(
        self,
        user_id: int | None = None,
        retrieval_mode: str | None = None,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> FeedbackMetrics:
        try:
            self.init_database()
            with self.session_factory() as session:
                filters = _build_feedback_trace_filters(
                    user_id=user_id,
                    retrieval_mode=retrieval_mode,
                    status=status,
                    created_from=created_from,
                    created_to=created_to,
                )
                row = session.execute(
                    select(
                        func.count(RAGFeedbackRecord.id),
                        func.avg(RAGFeedbackRecord.rating),
                        func.sum(
                            case(
                                (RAGFeedbackRecord.rating <= 2, 1),
                                else_=0,
                            )
                        ),
                        func.sum(
                            case(
                                (RAGFeedbackRecord.rating >= 4, 1),
                                else_=0,
                            )
                        ),
                    )
                    .select_from(RAGFeedbackRecord)
                    .join(RAGTraceRecord)
                    .where(*filters)
                ).one()
        except SQLAlchemyError as exc:
            raise FeedbackEvaluationServiceError(
                f"Failed to calculate feedback metrics: {exc}"
            ) from exc

        feedback_count = int(row[0] or 0)
        bad_answer_count = int(row[2] or 0)
        good_answer_count = int(row[3] or 0)
        return FeedbackMetrics(
            feedback_count=feedback_count,
            average_user_rating=(
                float(row[1]) if row[1] is not None else None
            ),
            bad_answer_rate=_rate(bad_answer_count, feedback_count),
            good_answer_rate=_rate(good_answer_count, feedback_count),
        )

    def export_failed_query_dataset(
        self,
        max_rating: int = 2,
        limit: int = 100,
        offset: int = 0,
        user_id: int | None = None,
        retrieval_mode: str | None = None,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> EvaluationDataset:
        if max_rating < 1 or max_rating > 5:
            raise FeedbackEvaluationServiceError(
                "max_rating must be between 1 and 5."
            )

        try:
            self.init_database()
            with self.session_factory() as session:
                filters = _build_feedback_trace_filters(
                    user_id=user_id,
                    retrieval_mode=retrieval_mode,
                    status=status,
                    created_from=created_from,
                    created_to=created_to,
                )
                filters.append(RAGFeedbackRecord.rating <= max_rating)
                rows = session.execute(
                    select(RAGFeedbackRecord, RAGTraceRecord)
                    .join(RAGTraceRecord)
                    .where(*filters)
                    .order_by(
                        RAGFeedbackRecord.created_at.desc(),
                        RAGFeedbackRecord.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                ).all()
        except SQLAlchemyError as exc:
            raise FeedbackEvaluationServiceError(
                f"Failed to export failed query dataset: {exc}"
            ) from exc

        return EvaluationDataset(
            version=1,
            name="Feedback failed queries",
            metadata={
                "source": "rag_feedback",
                "max_rating": max_rating,
                "limit": limit,
                "offset": offset,
                "user_id": user_id,
                "retrieval_mode": retrieval_mode,
                "status": status,
                "created_from": created_from,
                "created_to": created_to,
                "generated_at": datetime.now(timezone.utc),
            },
            cases=[
                _build_failed_query_case(
                    feedback=feedback,
                    trace=trace,
                )
                for feedback, trace in rows
            ],
        )


def _build_feedback_trace_filters(
    user_id: int | None,
    retrieval_mode: str | None,
    status: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> list:
    filters = []
    if user_id is not None:
        filters.append(RAGFeedbackRecord.user_id == user_id)

    if retrieval_mode is not None:
        filters.append(RAGTraceRecord.retrieval_mode == retrieval_mode)

    if status is not None:
        filters.append(RAGTraceRecord.status == status)

    if created_from is not None:
        filters.append(RAGFeedbackRecord.created_at >= created_from)

    if created_to is not None:
        filters.append(RAGFeedbackRecord.created_at <= created_to)

    return filters


def _build_failed_query_case(
    feedback: RAGFeedbackRecord,
    trace: RAGTraceRecord,
) -> EvaluationCase:
    return EvaluationCase(
        id=f"feedback-{feedback.id}-trace-{trace.id}",
        question=trace.question,
        expected_sources=[],
        expected_answer_contains=[],
        metadata={
            "source": "rag_feedback",
            "feedback_id": feedback.id,
            "trace_id": trace.id,
            "request_id": trace.request_id,
            "user_id": feedback.user_id,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "retrieval_mode": trace.retrieval_mode,
            "model_name": trace.model_name,
            "trace_status": trace.status,
            "retrieved_count": trace.retrieved_count,
            "retrieved_sources": trace.retrieved_sources or [],
            "trace_created_at": trace.created_at,
            "feedback_created_at": feedback.created_at,
        },
    )


def _rate(count: int, total: int) -> float | None:
    if total == 0:
        return None

    return count / total
