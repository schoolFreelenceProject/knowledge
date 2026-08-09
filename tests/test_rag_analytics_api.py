from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.analytics import (
    get_analytics_summary,
    get_feedback_analytics,
    get_retrieval_analytics,
    router,
)
from app.api.auth_dependencies import get_current_user
from app.services.auth_service import AuthenticatedUser
from app.services.rag_analytics_service import (
    AnalyticsFilterState,
    AnalyticsSummary,
    FeedbackAnalytics,
    RAGAnalyticsPersistenceError,
    RatingDistribution,
    RetrievalAnalytics,
    RetrievalModeDistribution,
    TopFailedDocumentStat,
)


class FakeAnalyticsService:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.summary_call: dict | None = None
        self.feedback_call: dict | None = None
        self.retrieval_call: dict | None = None

    def get_summary(
        self,
        user_id=None,
        status=None,
        retrieval_mode=None,
        created_from=None,
        created_to=None,
    ):
        if self.should_fail:
            raise RAGAnalyticsPersistenceError("database unavailable")

        self.summary_call = {
            "user_id": user_id,
            "status": status,
            "retrieval_mode": retrieval_mode,
            "created_from": created_from,
            "created_to": created_to,
        }
        return AnalyticsSummary(
            total_questions=3,
            average_latency_ms=120.5,
            feedback_count=2,
            average_user_rating=4.0,
            bad_answer_rate=0.0,
            good_answer_rate=1.0,
            filters=_build_filters(
                user_id=user_id,
                status=status,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
            ),
        )

    def get_feedback_analytics(
        self,
        user_id=None,
        status=None,
        retrieval_mode=None,
        created_from=None,
        created_to=None,
    ):
        self.feedback_call = {
            "user_id": user_id,
            "status": status,
            "retrieval_mode": retrieval_mode,
            "created_from": created_from,
            "created_to": created_to,
        }
        return FeedbackAnalytics(
            feedback_count=2,
            average_user_rating=3.0,
            bad_answer_rate=0.5,
            good_answer_rate=0.5,
            rating_distribution=[
                RatingDistribution(rating=1, count=1, rate=0.5),
                RatingDistribution(rating=2, count=0, rate=0.0),
                RatingDistribution(rating=3, count=0, rate=0.0),
                RatingDistribution(rating=4, count=0, rate=0.0),
                RatingDistribution(rating=5, count=1, rate=0.5),
            ],
            filters=_build_filters(
                user_id=user_id,
                status=status,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
            ),
        )

    def get_retrieval_analytics(
        self,
        user_id=None,
        status=None,
        retrieval_mode=None,
        created_from=None,
        created_to=None,
        top_failed_limit=10,
    ):
        self.retrieval_call = {
            "user_id": user_id,
            "status": status,
            "retrieval_mode": retrieval_mode,
            "created_from": created_from,
            "created_to": created_to,
            "top_failed_limit": top_failed_limit,
        }
        return RetrievalAnalytics(
            total_questions=3,
            retrieval_mode_distribution=[
                RetrievalModeDistribution(
                    retrieval_mode="hybrid",
                    count=2,
                    rate=2 / 3,
                    average_latency_ms=100.0,
                )
            ],
            top_failed_documents=[
                TopFailedDocumentStat(
                    filename="company_policy.md",
                    failure_count=2,
                    average_retrieval_score=0.72,
                    source_path="company_policy.md",
                )
            ],
            filters=_build_filters(
                user_id=user_id,
                status=status,
                retrieval_mode=retrieval_mode,
                created_from=created_from,
                created_to=created_to,
            ),
        )


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_filters(
    user_id=None,
    status=None,
    retrieval_mode=None,
    created_from=None,
    created_to=None,
) -> AnalyticsFilterState:
    return AnalyticsFilterState(
        user_id=user_id,
        status=status,
        retrieval_mode=retrieval_mode,
        created_from=created_from,
        created_to=created_to,
    )


def test_summary_endpoint_validates_and_passes_filters_to_service() -> None:
    analytics_service = FakeAnalyticsService()
    created_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    created_to = datetime(2026, 8, 9, tzinfo=timezone.utc)

    response = get_analytics_summary(
        user_id=1,
        status_filter="SUCCESS",
        retrieval_mode="hybrid",
        created_from=created_from,
        created_to=created_to,
        current_user=_build_user(),
        analytics_service=analytics_service,
    )

    assert response.total_questions == 3
    assert response.average_latency_ms == 120.5
    assert response.feedback_count == 2
    assert response.filters.retrieval_mode == "hybrid"
    assert analytics_service.summary_call == {
        "user_id": 1,
        "status": "SUCCESS",
        "retrieval_mode": "hybrid",
        "created_from": created_from,
        "created_to": created_to,
    }


def test_feedback_endpoint_returns_rating_distribution() -> None:
    analytics_service = FakeAnalyticsService()

    response = get_feedback_analytics(
        user_id=None,
        status_filter=None,
        retrieval_mode=None,
        created_from=None,
        created_to=None,
        current_user=_build_user(),
        analytics_service=analytics_service,
    )

    assert response.feedback_count == 2
    assert response.bad_answer_rate == 0.5
    assert response.rating_distribution[0].rating == 1
    assert response.rating_distribution[0].count == 1


def test_retrieval_endpoint_returns_distribution_and_failed_documents() -> None:
    analytics_service = FakeAnalyticsService()

    response = get_retrieval_analytics(
        user_id=1,
        status_filter="SUCCESS",
        retrieval_mode="hybrid",
        created_from=None,
        created_to=None,
        top_failed_limit=5,
        current_user=_build_user(),
        analytics_service=analytics_service,
    )

    assert response.total_questions == 3
    assert response.retrieval_mode_distribution[0].retrieval_mode == "hybrid"
    assert response.top_failed_documents[0].filename == "company_policy.md"
    assert response.top_failed_documents[0].failure_count == 2
    assert response.top_failed_documents[0].average_retrieval_score == 0.72
    assert analytics_service.retrieval_call["top_failed_limit"] == 5


def test_analytics_endpoints_reject_invalid_date_range() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_analytics_summary(
            user_id=None,
            status_filter=None,
            retrieval_mode=None,
            created_from=datetime(2026, 8, 9, tzinfo=timezone.utc),
            created_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
            current_user=_build_user(),
            analytics_service=FakeAnalyticsService(),
        )

    assert exc_info.value.status_code == 400


def test_analytics_endpoint_maps_persistence_errors_to_502() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_analytics_summary(
            user_id=None,
            status_filter=None,
            retrieval_mode=None,
            created_from=None,
            created_to=None,
            current_user=_build_user(),
            analytics_service=FakeAnalyticsService(should_fail=True),
        )

    assert exc_info.value.status_code == 502


def test_analytics_routes_require_jwt_dependency() -> None:
    protected_routes = [
        route for route in router.routes
        if getattr(route, "dependant", None) is not None
    ]

    assert protected_routes
    for route in protected_routes:
        dependency_calls = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert get_current_user in dependency_calls
