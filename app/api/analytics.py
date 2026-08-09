from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_rag_analytics_service
from app.schemas.analytics import (
    AnalyticsFeedbackResponse,
    AnalyticsFilters,
    AnalyticsRetrievalResponse,
    AnalyticsSummaryResponse,
    RatingDistributionItem,
    RetrievalModeDistributionItem,
    TopFailedDocument,
)
from app.services.auth_service import AuthenticatedUser
from app.services.rag_analytics_service import (
    AnalyticsFilterState,
    AnalyticsSummary,
    FeedbackAnalytics,
    RAGAnalyticsPersistenceError,
    RAGAnalyticsService,
    RetrievalAnalytics,
)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    user_id: int | None = Query(default=None, ge=1),
    status_filter: Literal["PROCESSING", "SUCCESS", "ERROR"] | None = Query(
        default=None,
        alias="status",
    ),
    retrieval_mode: Literal["vector", "bm25", "hybrid"] | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    analytics_service: RAGAnalyticsService = Depends(get_rag_analytics_service),
) -> AnalyticsSummaryResponse:
    _ = current_user
    _validate_date_range(created_from=created_from, created_to=created_to)
    try:
        return _to_summary_response(
            analytics_service.get_summary(
                user_id=user_id,
                status=status_filter,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
            )
        )
    except RAGAnalyticsPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Analytics lookup failed: {exc}",
        ) from exc


@router.get("/feedback", response_model=AnalyticsFeedbackResponse)
def get_feedback_analytics(
    user_id: int | None = Query(default=None, ge=1),
    status_filter: Literal["PROCESSING", "SUCCESS", "ERROR"] | None = Query(
        default=None,
        alias="status",
    ),
    retrieval_mode: Literal["vector", "bm25", "hybrid"] | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    analytics_service: RAGAnalyticsService = Depends(get_rag_analytics_service),
) -> AnalyticsFeedbackResponse:
    _ = current_user
    _validate_date_range(created_from=created_from, created_to=created_to)
    try:
        return _to_feedback_response(
            analytics_service.get_feedback_analytics(
                user_id=user_id,
                status=status_filter,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
            )
        )
    except RAGAnalyticsPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Analytics lookup failed: {exc}",
        ) from exc


@router.get("/retrieval", response_model=AnalyticsRetrievalResponse)
def get_retrieval_analytics(
    user_id: int | None = Query(default=None, ge=1),
    status_filter: Literal["PROCESSING", "SUCCESS", "ERROR"] | None = Query(
        default=None,
        alias="status",
    ),
    retrieval_mode: Literal["vector", "bm25", "hybrid"] | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    top_failed_limit: int = Query(default=10, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    analytics_service: RAGAnalyticsService = Depends(get_rag_analytics_service),
) -> AnalyticsRetrievalResponse:
    _ = current_user
    _validate_date_range(created_from=created_from, created_to=created_to)
    try:
        return _to_retrieval_response(
            analytics_service.get_retrieval_analytics(
                user_id=user_id,
                status=status_filter,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
                top_failed_limit=top_failed_limit,
            )
        )
    except RAGAnalyticsPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Analytics lookup failed: {exc}",
        ) from exc


def _validate_date_range(
    created_from: datetime | None,
    created_to: datetime | None,
) -> None:
    if (
        created_from is not None
        and created_to is not None
        and created_from > created_to
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_from must be before or equal to created_to.",
        )


def _to_summary_response(summary: AnalyticsSummary) -> AnalyticsSummaryResponse:
    return AnalyticsSummaryResponse(
        total_questions=summary.total_questions,
        average_latency_ms=summary.average_latency_ms,
        feedback_count=summary.feedback_count,
        average_user_rating=summary.average_user_rating,
        bad_answer_rate=summary.bad_answer_rate,
        good_answer_rate=summary.good_answer_rate,
        filters=_to_filter_schema(summary.filters),
    )


def _to_feedback_response(feedback: FeedbackAnalytics) -> AnalyticsFeedbackResponse:
    return AnalyticsFeedbackResponse(
        feedback_count=feedback.feedback_count,
        average_user_rating=feedback.average_user_rating,
        bad_answer_rate=feedback.bad_answer_rate,
        good_answer_rate=feedback.good_answer_rate,
        rating_distribution=[
            RatingDistributionItem(**item.__dict__)
            for item in feedback.rating_distribution
        ],
        filters=_to_filter_schema(feedback.filters),
    )


def _to_retrieval_response(
    retrieval: RetrievalAnalytics,
) -> AnalyticsRetrievalResponse:
    return AnalyticsRetrievalResponse(
        total_questions=retrieval.total_questions,
        retrieval_mode_distribution=[
            RetrievalModeDistributionItem(**item.__dict__)
            for item in retrieval.retrieval_mode_distribution
        ],
        top_failed_documents=[
            TopFailedDocument(**item.__dict__)
            for item in retrieval.top_failed_documents
        ],
        filters=_to_filter_schema(retrieval.filters),
    )


def _to_filter_schema(filters: AnalyticsFilterState) -> AnalyticsFilters:
    return AnalyticsFilters(**filters.__dict__)
