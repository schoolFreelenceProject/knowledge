from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.auth_dependencies import get_current_user
from app.api.feedback import list_feedback, router, submit_trace_feedback
from app.schemas.feedback import FeedbackRequest
from app.services.auth_service import AuthenticatedUser
from app.services.rag_feedback_service import (
    RAGFeedbackList,
    RAGFeedbackTargetNotFoundError,
    StoredRAGFeedback,
)


class FakeFeedbackService:
    def __init__(self) -> None:
        self.submit_call: dict | None = None
        self.list_call: dict | None = None

    def submit_feedback(self, request_id, user_id, rating, comment=None):
        if request_id == "missing":
            raise RAGFeedbackTargetNotFoundError(
                f"RAG trace not found for request_id: {request_id}"
            )

        self.submit_call = {
            "request_id": request_id,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
        }
        return _build_feedback(request_id=request_id, rating=rating, comment=comment)

    def list_feedback(
        self,
        limit,
        offset,
        user_id=None,
        rating=None,
        request_id=None,
        created_from=None,
        created_to=None,
    ):
        self.list_call = {
            "limit": limit,
            "offset": offset,
            "user_id": user_id,
            "rating": rating,
            "request_id": request_id,
            "created_from": created_from,
            "created_to": created_to,
        }
        return RAGFeedbackList(
            items=[_build_feedback(request_id=request_id or "req-1")],
            total=1,
            limit=limit,
            offset=offset,
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


def _build_feedback(
    request_id: str,
    rating: int = 5,
    comment: str | None = "Accurate answer.",
) -> StoredRAGFeedback:
    return StoredRAGFeedback(
        id=10,
        trace_id=20,
        request_id=request_id,
        user_id=1,
        rating=rating,
        comment=comment,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )


def test_submit_trace_feedback_creates_feedback_for_current_user() -> None:
    feedback_service = FakeFeedbackService()

    response = submit_trace_feedback(
        feedback_request=FeedbackRequest(
            rating=5,
            comment="Accurate answer.",
        ),
        request_id="req-1",
        current_user=_build_user(),
        feedback_service=feedback_service,
    )

    assert response.request_id == "req-1"
    assert response.user_id == 1
    assert response.rating == 5
    assert feedback_service.submit_call == {
        "request_id": "req-1",
        "user_id": 1,
        "rating": 5,
        "comment": "Accurate answer.",
    }


def test_submit_trace_feedback_returns_404_for_missing_trace() -> None:
    with pytest.raises(HTTPException) as exc_info:
        submit_trace_feedback(
            feedback_request=FeedbackRequest(rating=4),
            request_id="missing",
            current_user=_build_user(),
            feedback_service=FakeFeedbackService(),
        )

    assert exc_info.value.status_code == 404


def test_feedback_request_validates_rating_range() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(rating=0)


def test_list_feedback_validates_and_passes_filters_to_service() -> None:
    feedback_service = FakeFeedbackService()
    created_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    created_to = datetime(2026, 8, 9, tzinfo=timezone.utc)

    response = list_feedback(
        limit=25,
        offset=50,
        user_id=1,
        rating=5,
        request_id="req-1",
        created_from=created_from,
        created_to=created_to,
        current_user=_build_user(),
        feedback_service=feedback_service,
    )

    assert response.total == 1
    assert response.items[0].request_id == "req-1"
    assert response.items[0].rating == 5
    assert feedback_service.list_call == {
        "limit": 25,
        "offset": 50,
        "user_id": 1,
        "rating": 5,
        "request_id": "req-1",
        "created_from": created_from,
        "created_to": created_to,
    }


def test_list_feedback_rejects_invalid_date_range() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_feedback(
            limit=50,
            offset=0,
            user_id=None,
            rating=None,
            request_id=None,
            created_from=datetime(2026, 8, 9, tzinfo=timezone.utc),
            created_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
            current_user=_build_user(),
            feedback_service=FakeFeedbackService(),
        )

    assert exc_info.value.status_code == 400


def test_feedback_routes_require_jwt_dependency() -> None:
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
