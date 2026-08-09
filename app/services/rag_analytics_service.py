from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import RAGFeedbackRecord, RAGTraceRecord


class RAGAnalyticsPersistenceError(RuntimeError):
    """Raised when RAG analytics data cannot be read."""


@dataclass(frozen=True)
class AnalyticsFilterState:
    user_id: int | None
    status: str | None
    retrieval_mode: str | None
    created_from: datetime | None
    created_to: datetime | None


@dataclass(frozen=True)
class RatingDistribution:
    rating: int
    count: int
    rate: float | None


@dataclass(frozen=True)
class RetrievalModeDistribution:
    retrieval_mode: str
    count: int
    rate: float | None
    average_latency_ms: float | None


@dataclass(frozen=True)
class TopFailedDocumentStat:
    filename: str
    failure_count: int
    average_retrieval_score: float | None
    source_path: str | None


@dataclass(frozen=True)
class AnalyticsSummary:
    total_questions: int
    average_latency_ms: float | None
    feedback_count: int
    average_user_rating: float | None
    bad_answer_rate: float | None
    good_answer_rate: float | None
    filters: AnalyticsFilterState


@dataclass(frozen=True)
class FeedbackAnalytics:
    feedback_count: int
    average_user_rating: float | None
    bad_answer_rate: float | None
    good_answer_rate: float | None
    rating_distribution: list[RatingDistribution]
    filters: AnalyticsFilterState


@dataclass(frozen=True)
class RetrievalAnalytics:
    total_questions: int
    retrieval_mode_distribution: list[RetrievalModeDistribution]
    top_failed_documents: list[TopFailedDocumentStat]
    filters: AnalyticsFilterState


@dataclass
class _FailedDocumentAccumulator:
    filename: str
    source_path: str | None
    failure_count: int = 0
    score_total: float = 0.0
    score_count: int = 0

    def record_failure(self, average_score: float | None) -> None:
        self.failure_count += 1
        if average_score is not None:
            self.score_total += average_score
            self.score_count += 1

    @property
    def average_retrieval_score(self) -> float | None:
        if self.score_count == 0:
            return None

        return self.score_total / self.score_count


class RAGAnalyticsService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def get_summary(
        self,
        user_id: int | None = None,
        status: str | None = None,
        retrieval_mode: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AnalyticsSummary:
        filters = AnalyticsFilterState(
            user_id=user_id,
            status=status,
            retrieval_mode=retrieval_mode,
            created_from=created_from,
            created_to=created_to,
        )
        try:
            self.init_database()
            with self.session_factory() as session:
                trace_filters = _build_trace_filters(filters)
                trace_row = session.execute(
                    select(
                        func.count(RAGTraceRecord.id),
                        func.avg(RAGTraceRecord.total_time_ms),
                    )
                    .select_from(RAGTraceRecord)
                    .where(*trace_filters)
                ).one()
                feedback_counts = _fetch_feedback_rating_counts(
                    session=session,
                    filters=filters,
                )
        except SQLAlchemyError as exc:
            raise RAGAnalyticsPersistenceError(
                f"Failed to read RAG analytics summary: {exc}"
            ) from exc

        feedback_metrics = _calculate_feedback_metrics(feedback_counts)
        return AnalyticsSummary(
            total_questions=int(trace_row[0] or 0),
            average_latency_ms=(
                float(trace_row[1]) if trace_row[1] is not None else None
            ),
            feedback_count=feedback_metrics.feedback_count,
            average_user_rating=feedback_metrics.average_user_rating,
            bad_answer_rate=feedback_metrics.bad_answer_rate,
            good_answer_rate=feedback_metrics.good_answer_rate,
            filters=filters,
        )

    def get_feedback_analytics(
        self,
        user_id: int | None = None,
        status: str | None = None,
        retrieval_mode: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> FeedbackAnalytics:
        filters = AnalyticsFilterState(
            user_id=user_id,
            status=status,
            retrieval_mode=retrieval_mode,
            created_from=created_from,
            created_to=created_to,
        )
        try:
            self.init_database()
            with self.session_factory() as session:
                feedback_counts = _fetch_feedback_rating_counts(
                    session=session,
                    filters=filters,
                )
        except SQLAlchemyError as exc:
            raise RAGAnalyticsPersistenceError(
                f"Failed to read RAG feedback analytics: {exc}"
            ) from exc

        feedback_metrics = _calculate_feedback_metrics(feedback_counts)
        return FeedbackAnalytics(
            feedback_count=feedback_metrics.feedback_count,
            average_user_rating=feedback_metrics.average_user_rating,
            bad_answer_rate=feedback_metrics.bad_answer_rate,
            good_answer_rate=feedback_metrics.good_answer_rate,
            rating_distribution=feedback_metrics.rating_distribution,
            filters=filters,
        )

    def get_retrieval_analytics(
        self,
        user_id: int | None = None,
        status: str | None = None,
        retrieval_mode: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        top_failed_limit: int = 10,
    ) -> RetrievalAnalytics:
        filters = AnalyticsFilterState(
            user_id=user_id,
            status=status,
            retrieval_mode=retrieval_mode,
            created_from=created_from,
            created_to=created_to,
        )
        try:
            self.init_database()
            with self.session_factory() as session:
                trace_filters = _build_trace_filters(filters)
                total_questions = session.scalar(
                    select(func.count(RAGTraceRecord.id))
                    .select_from(RAGTraceRecord)
                    .where(*trace_filters)
                )
                mode_distribution = _fetch_retrieval_mode_distribution(
                    session=session,
                    filters=filters,
                    total_questions=int(total_questions or 0),
                )
                top_failed_documents = _fetch_top_failed_documents(
                    session=session,
                    filters=filters,
                    limit=top_failed_limit,
                )
        except SQLAlchemyError as exc:
            raise RAGAnalyticsPersistenceError(
                f"Failed to read RAG retrieval analytics: {exc}"
            ) from exc

        return RetrievalAnalytics(
            total_questions=int(total_questions or 0),
            retrieval_mode_distribution=mode_distribution,
            top_failed_documents=top_failed_documents,
            filters=filters,
        )


@dataclass(frozen=True)
class _FeedbackMetrics:
    feedback_count: int
    average_user_rating: float | None
    bad_answer_rate: float | None
    good_answer_rate: float | None
    rating_distribution: list[RatingDistribution]


def _fetch_feedback_rating_counts(
    session: Session,
    filters: AnalyticsFilterState,
) -> dict[int, int]:
    rows = session.execute(
        select(
            RAGFeedbackRecord.rating,
            func.count(RAGFeedbackRecord.id),
        )
        .select_from(RAGFeedbackRecord)
        .join(RAGTraceRecord)
        .where(*_build_feedback_trace_filters(filters))
        .group_by(RAGFeedbackRecord.rating)
        .order_by(RAGFeedbackRecord.rating.asc())
    ).all()

    return {int(rating): int(count or 0) for rating, count in rows}


def _fetch_retrieval_mode_distribution(
    session: Session,
    filters: AnalyticsFilterState,
    total_questions: int,
) -> list[RetrievalModeDistribution]:
    rows = session.execute(
        select(
            RAGTraceRecord.retrieval_mode,
            func.count(RAGTraceRecord.id),
            func.avg(RAGTraceRecord.total_time_ms),
        )
        .select_from(RAGTraceRecord)
        .where(*_build_trace_filters(filters))
        .group_by(RAGTraceRecord.retrieval_mode)
        .order_by(func.count(RAGTraceRecord.id).desc(), RAGTraceRecord.retrieval_mode)
    ).all()

    return [
        RetrievalModeDistribution(
            retrieval_mode=retrieval_mode,
            count=int(count or 0),
            rate=_rate(int(count or 0), total_questions),
            average_latency_ms=(
                float(average_latency) if average_latency is not None else None
            ),
        )
        for retrieval_mode, count, average_latency in rows
    ]


def _fetch_top_failed_documents(
    session: Session,
    filters: AnalyticsFilterState,
    limit: int,
) -> list[TopFailedDocumentStat]:
    rows = session.execute(
        select(
            RAGFeedbackRecord.id,
            RAGTraceRecord.retrieved_sources,
        )
        .select_from(RAGFeedbackRecord)
        .join(RAGTraceRecord)
        .where(
            *_build_feedback_trace_filters(filters),
            RAGFeedbackRecord.rating <= 2,
        )
        .order_by(RAGFeedbackRecord.created_at.desc(), RAGFeedbackRecord.id.desc())
    ).all()

    accumulators: dict[str, _FailedDocumentAccumulator] = {}
    for _feedback_id, retrieved_sources in rows:
        for filename, source_path, average_score in _extract_failed_documents(
            retrieved_sources or []
        ):
            accumulator = accumulators.get(filename)
            if accumulator is None:
                accumulator = _FailedDocumentAccumulator(
                    filename=filename,
                    source_path=source_path,
                )
                accumulators[filename] = accumulator
            if accumulator.source_path is None and source_path is not None:
                accumulator.source_path = source_path
            accumulator.record_failure(average_score)

    sorted_accumulators = sorted(
        accumulators.values(),
        key=lambda item: (-item.failure_count, item.filename),
    )
    return [
        TopFailedDocumentStat(
            filename=item.filename,
            failure_count=item.failure_count,
            average_retrieval_score=item.average_retrieval_score,
            source_path=item.source_path,
        )
        for item in sorted_accumulators[:limit]
    ]


def _extract_failed_documents(
    retrieved_sources: list[dict[str, Any]],
) -> list[tuple[str, str | None, float | None]]:
    per_document_scores: dict[str, list[float]] = {}
    per_document_source_path: dict[str, str | None] = {}

    for source in retrieved_sources:
        if not isinstance(source, dict):
            continue

        source_path = _clean_string(source.get("source_path"))
        filename = _clean_string(source.get("filename")) or _filename_from_path(
            source_path
        )
        if filename is None:
            continue

        per_document_source_path.setdefault(filename, source_path)
        score = _coerce_float(source.get("score"))
        if score is not None:
            per_document_scores.setdefault(filename, []).append(score)
        else:
            per_document_scores.setdefault(filename, [])

    documents: list[tuple[str, str | None, float | None]] = []
    for filename, scores in per_document_scores.items():
        documents.append(
            (
                filename,
                per_document_source_path.get(filename),
                (sum(scores) / len(scores)) if scores else None,
            )
        )

    return documents


def _build_trace_filters(filters: AnalyticsFilterState):
    clauses = []
    if filters.user_id is not None:
        clauses.append(RAGTraceRecord.user_id == filters.user_id)

    if filters.status is not None:
        clauses.append(RAGTraceRecord.status == filters.status)

    if filters.retrieval_mode is not None:
        clauses.append(RAGTraceRecord.retrieval_mode == filters.retrieval_mode)

    if filters.created_from is not None:
        clauses.append(RAGTraceRecord.created_at >= filters.created_from)

    if filters.created_to is not None:
        clauses.append(RAGTraceRecord.created_at <= filters.created_to)

    return clauses


def _build_feedback_trace_filters(filters: AnalyticsFilterState):
    clauses = []
    if filters.user_id is not None:
        clauses.append(RAGFeedbackRecord.user_id == filters.user_id)

    if filters.status is not None:
        clauses.append(RAGTraceRecord.status == filters.status)

    if filters.retrieval_mode is not None:
        clauses.append(RAGTraceRecord.retrieval_mode == filters.retrieval_mode)

    if filters.created_from is not None:
        clauses.append(RAGFeedbackRecord.created_at >= filters.created_from)

    if filters.created_to is not None:
        clauses.append(RAGFeedbackRecord.created_at <= filters.created_to)

    return clauses


def _calculate_feedback_metrics(
    rating_counts: dict[int, int],
) -> _FeedbackMetrics:
    feedback_count = sum(rating_counts.values())
    rating_total = sum(rating * count for rating, count in rating_counts.items())
    bad_answer_count = sum(
        count for rating, count in rating_counts.items() if rating <= 2
    )
    good_answer_count = sum(
        count for rating, count in rating_counts.items() if rating >= 4
    )
    return _FeedbackMetrics(
        feedback_count=feedback_count,
        average_user_rating=(
            rating_total / feedback_count if feedback_count else None
        ),
        bad_answer_rate=_rate(bad_answer_count, feedback_count),
        good_answer_rate=_rate(good_answer_count, feedback_count),
        rating_distribution=[
            RatingDistribution(
                rating=rating,
                count=rating_counts.get(rating, 0),
                rate=_rate(rating_counts.get(rating, 0), feedback_count),
            )
            for rating in range(1, 6)
        ],
    )


def _rate(count: int, total: int) -> float | None:
    if total == 0:
        return None

    return count / total


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    stripped_value = value.strip()
    if not stripped_value:
        return None

    return stripped_value


def _filename_from_path(source_path: str | None) -> str | None:
    if source_path is None:
        return None

    return source_path.replace("\\", "/").rsplit("/", 1)[-1] or None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, int | float):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None

    return None
