from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.knowledge_explorer import router, search_knowledge
from app.schemas.knowledge_explorer import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.retrieval_service import RetrievalServiceError


class FakeKnowledgeExplorerService:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.call: dict | None = None

    def search(self, request, user_id):
        if self.fail:
            raise RetrievalServiceError(
                "Qdrant query failed: SELECT * FROM internal_vectors"
            )

        self.call = {
            "request": request,
            "user_id": user_id,
        }
        return KnowledgeSearchResponse(
            query=request.query,
            mode=request.mode,
            top_k=request.top_k,
            retrieval_mode="hybrid",
            results=[],
        )


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=7,
        email="searcher@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_knowledge_search_api_calls_service_with_current_user() -> None:
    service = FakeKnowledgeExplorerService()

    response = search_knowledge(
        request=KnowledgeSearchRequest(query="remote work", mode="all", top_k=5),
        current_user=_build_user(),
        explorer_service=service,
    )

    assert response.query == "remote work"
    assert response.results == []
    assert service.call is not None
    assert service.call["user_id"] == 7
    assert service.call["request"].top_k == 5


def test_knowledge_search_api_hides_internal_retrieval_errors() -> None:
    with pytest.raises(HTTPException) as exc_info:
        search_knowledge(
            request=KnowledgeSearchRequest(query="remote work"),
            current_user=_build_user(),
            explorer_service=FakeKnowledgeExplorerService(fail=True),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Knowledge search query could not be processed."
    assert "SELECT" not in exc_info.value.detail
    assert "internal_vectors" not in exc_info.value.detail


def test_knowledge_search_route_requires_jwt_dependency() -> None:
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
