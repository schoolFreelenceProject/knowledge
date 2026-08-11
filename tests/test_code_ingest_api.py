import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.code_ingest import ingest_code_folder, ingest_code_repository, router
from app.schemas.code import CodeIngestRequest, CodeIngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.code_ingestion_service import CodeRepositoryIngestionConflictError
from app.services.code_metadata_service import CodeMetadataPersistenceError


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
        if repo_url == "metadata-failure":
            raise CodeMetadataPersistenceError(
                "psycopg.errors.UniqueViolation: INSERT INTO code_chunks VALUES (...)"
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

    def ingest_uploaded_folder(self, folder_name, files, uploader_user_id):
        if folder_name == "metadata-failure":
            raise CodeMetadataPersistenceError(
                "psycopg.errors.UniqueViolation: INSERT INTO code_chunks VALUES (...)"
            )

        self.call = {
            "folder_name": folder_name,
            "files": files,
            "uploader_user_id": uploader_user_id,
        }
        return CodeIngestResponse(
            repository_id=11,
            repo_name=folder_name,
            source_type="LOCAL_FOLDER",
            repo_url=None,
            branch=None,
            commit_sha=None,
            source_fingerprint="b" * 64,
            storage_path="local/CodeFolder/bbbbbbbb",
            status="INDEXED",
            files=1,
            chunks=1,
            embeddings=1,
            collection_name="company_documents",
            stored_vectors=1,
            saved_chunks=1,
            vector_size=384,
            skipped_files=1,
            skip_reasons={"unsupported_extension": 1},
        )


class FakeFolderUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content
        self.closed = False

    async def read(self) -> bytes:
        return self.content

    async def close(self) -> None:
        self.closed = True


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
    assert exc_info.value.detail == "This repository revision is already indexed."


def test_code_ingest_api_hides_internal_persistence_errors() -> None:
    with pytest.raises(HTTPException) as exc_info:
        ingest_code_repository(
            request=CodeIngestRequest(repo_url="metadata-failure", branch="main"),
            current_user=_build_user(),
            code_ingestion_service=FakeCodeIngestionService(),
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to save repository metadata."
    assert "psycopg" not in exc_info.value.detail
    assert "INSERT" not in exc_info.value.detail
    assert "code_chunks" not in exc_info.value.detail


def test_code_folder_ingest_api_calls_service_and_closes_uploads() -> None:
    service = FakeCodeIngestionService()
    uploads = [
        FakeFolderUploadFile("app.py", b"def app():\n    return 'ok'\n"),
        FakeFolderUploadFile("logo.png", b"binary"),
    ]

    response = asyncio.run(
        ingest_code_folder(
            folder_name="CodeFolder",
            relative_paths=["src/app.py", "assets/logo.png"],
            files=uploads,
            current_user=_build_user(),
            code_ingestion_service=service,
        )
    )

    assert [upload.closed for upload in uploads] == [True, True]
    assert response.repository_id == 11
    assert response.source_type == "LOCAL_FOLDER"
    assert response.repo_url is None
    assert service.call is not None
    assert service.call["folder_name"] == "CodeFolder"
    assert service.call["uploader_user_id"] == 7
    assert [item.relative_path for item in service.call["files"]] == [
        "src/app.py",
        "assets/logo.png",
    ]


def test_code_folder_ingest_api_rejects_mismatched_files_and_paths() -> None:
    uploads = [FakeFolderUploadFile("app.py", b"def app(): pass\n")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_code_folder(
                folder_name="CodeFolder",
                relative_paths=["src/app.py", "src/extra.py"],
                files=uploads,
                current_user=_build_user(),
                code_ingestion_service=FakeCodeIngestionService(),
            )
        )

    assert uploads[0].closed is True
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Code folder upload files and relative paths do not match."
    )


def test_code_folder_ingest_api_hides_internal_persistence_errors() -> None:
    uploads = [FakeFolderUploadFile("app.py", b"def app(): pass\n")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_code_folder(
                folder_name="metadata-failure",
                relative_paths=["src/app.py"],
                files=uploads,
                current_user=_build_user(),
                code_ingestion_service=FakeCodeIngestionService(),
            )
        )

    assert uploads[0].closed is True
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to save code folder metadata."
    assert "psycopg" not in exc_info.value.detail
    assert "INSERT" not in exc_info.value.detail
    assert "code_chunks" not in exc_info.value.detail


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
