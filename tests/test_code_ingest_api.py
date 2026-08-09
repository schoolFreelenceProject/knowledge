from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.code_ingest import ingest_code_repository, router
from app.schemas.code import CodeIngestRequest, CodeIngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.code_ingestion_service import CodeRepositoryIngestionConflictError


class FakeCodeIngestionService:
    def __init__(self) -> None:
        self.call: dict | None = None

    def ingest_repository(
        self,
        repo_url,
        branch,
        include_globs,
        exclude_globs,
        uploader_user_id,
    ):
        if repo_url == "duplicate":
            raise CodeRepositoryIngestionConflictError(
                "Code repository revision is already indexed."
            )

        self.call = {
            "repo_url": repo_url,
            "branch": branch,
            "include_globs": include_globs,
            "exclude_globs": exclude_globs,
            "uploader_user_id": uploader_user_id,
        }
        return CodeIngestResponse(
            repository_id=10,
            repo_name="repo",
            repo_url=repo_url,
            branch=branch,
            commit_sha="a" * 40,
            storage_path="repo/main/aaaaaaaa",
            status="INDEXED",
            files=1,
            chunks=2,
            embeddings=2,
            collection_name="company_documents",
            stored_vectors=2,
            saved_chunks=2,
            vector_size=384,
        )


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=7,
        email="developer@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_code_ingest_api_calls_service_with_current_user() -> None:
    service = FakeCodeIngestionService()

    response = ingest_code_repository(
        request=CodeIngestRequest(
            repo_url="file:///repo",
            branch="main",
            include_globs=["**/*.py"],
            exclude_globs=["**/dist/**"],
        ),
        current_user=_build_user(),
        code_ingestion_service=service,
    )

    assert response.repository_id == 10
    assert service.call == {
        "repo_url": "file:///repo",
        "branch": "main",
        "include_globs": ["**/*.py"],
        "exclude_globs": ["**/dist/**"],
        "uploader_user_id": 7,
    }


def test_code_ingest_api_returns_409_for_duplicate_revision() -> None:
    with pytest.raises(HTTPException) as exc_info:
        ingest_code_repository(
            request=CodeIngestRequest(repo_url="duplicate", branch="main"),
            current_user=_build_user(),
            code_ingestion_service=FakeCodeIngestionService(),
        )

    assert exc_info.value.status_code == 409


def test_code_ingest_routes_require_jwt_dependency() -> None:
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
