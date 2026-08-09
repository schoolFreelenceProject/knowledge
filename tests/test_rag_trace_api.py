from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.traces import get_trace, list_traces, router
from app.services.auth_service import AuthenticatedUser
from app.services.rag_trace_service import (
    RAGTraceList,
    RAGTraceNotFoundError,
    StoredRAGTrace,
)


class FakeTraceService:
    def __init__(self) -> None:
        self.list_call: dict | None = None

    def list_traces(
        self,
        limit,
        offset,
        user_id=None,
        status=None,
        retrieval_mode=None,
        created_from=None,
        created_to=None,
    ):
        self.list_call = {
            "limit": limit,
            "offset": offset,
            "user_id": user_id,
            "status": status,
            "retrieval_mode": retrieval_mode,
            "created_from": created_from,
            "created_to": created_to,
        }
        return RAGTraceList(
            items=[_build_trace("req-1")],
            total=1,
            limit=limit,
            offset=offset,
        )

    def get_trace_by_request_id(self, request_id: str):
        if request_id == "missing":
            raise RAGTraceNotFoundError(
                f"RAG trace not found for request_id: {request_id}"
            )

        return _build_trace(request_id)


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_trace(request_id: str) -> StoredRAGTrace:
    return StoredRAGTrace(
        id=10,
        request_id=request_id,
        user_id=1,
        question="What is the remote work policy?",
        retrieval_mode="hybrid",
        retrieval_time_ms=12.3,
        reranker_time_ms=4.5,
        generation_time_ms=30.4,
        total_time_ms=50.2,
        model_name="llama3.1:8b",
        retrieved_count=1,
        status="SUCCESS",
        error_message=None,
        prompt_tokens=None,
        completion_tokens=None,
        retrieved_sources=[
            {
                "filename": "company_policy.md",
                "source_path": "company_policy.md",
                "page_number": None,
                "chunk_index": 1,
                "score": 0.91,
                "vector_score": 0.82,
                "bm25_score": 1.6,
                "fusion_score": 0.44,
                "reranker_score": 0.91,
            }
        ],
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )


def test_list_traces_validates_and_passes_filters_to_service() -> None:
    trace_service = FakeTraceService()
    created_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    created_to = datetime(2026, 8, 9, tzinfo=timezone.utc)

    response = list_traces(
        limit=25,
        offset=50,
        user_id=1,
        status_filter="SUCCESS",
        retrieval_mode="hybrid",
        created_from=created_from,
        created_to=created_to,
        current_user=_build_user(),
        trace_service=trace_service,
    )

    assert response.total == 1
    assert response.limit == 25
    assert response.offset == 50
    assert response.items[0].request_id == "req-1"
    assert response.items[0].retrieved_sources[0].filename == "company_policy.md"
    assert trace_service.list_call == {
        "limit": 25,
        "offset": 50,
        "user_id": 1,
        "status": "SUCCESS",
        "retrieval_mode": "hybrid",
        "created_from": created_from,
        "created_to": created_to,
    }


def test_list_traces_rejects_invalid_date_range() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_traces(
            limit=50,
            offset=0,
            user_id=None,
            status_filter=None,
            retrieval_mode=None,
            created_from=datetime(2026, 8, 9, tzinfo=timezone.utc),
            created_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
            current_user=_build_user(),
            trace_service=FakeTraceService(),
        )

    assert exc_info.value.status_code == 400


def test_get_trace_returns_record_by_request_id() -> None:
    response = get_trace(
        request_id="req-abc",
        current_user=_build_user(),
        trace_service=FakeTraceService(),
    )

    assert response.request_id == "req-abc"
    assert response.status == "SUCCESS"
    assert response.retrieved_sources[0].reranker_score == 0.91


def test_get_trace_returns_404_for_missing_request_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_trace(
            request_id="missing",
            current_user=_build_user(),
            trace_service=FakeTraceService(),
        )

    assert exc_info.value.status_code == 404


def test_trace_routes_require_jwt_dependency() -> None:
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
