from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.documents import get_document, list_documents, reindex_document
from app.schemas.document_management import (
    DocumentDetail,
    DocumentSummary,
    ReindexDocumentResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.metadata_service import MetadataPersistenceError
from app.services.permission_service import DocumentAccessDeniedError


class FakeDocumentManagementService:
    def __init__(self, reindex_error: Exception | None = None) -> None:
        self.document_ids: list[int] | None = None
        self.reindex_error = reindex_error

    def list_documents(self, document_ids=None):
        self.document_ids = document_ids
        return []

    def get_document(self, document_id):
        timestamp = datetime.now(timezone.utc)
        summary = DocumentSummary(
            id=document_id,
            filename="security.md",
            file_type="markdown",
            storage_path="security.md",
            file_hash="a" * 64,
            status="INDEXED",
            created_at=timestamp,
            updated_at=timestamp,
            chunk_count=0,
        )
        return DocumentDetail(**summary.model_dump(), chunks=[])

    def reindex_document(self, document_id):
        if self.reindex_error is not None:
            raise self.reindex_error

        return ReindexDocumentResponse(
            document_id=document_id,
            status="INDEXED",
            chunks=1,
            stored_vectors=1,
            replaced_vectors=0,
            cleanup_warning=None,
        )


class FakePermissionService:
    def __init__(self, denied: bool = False) -> None:
        self.denied = denied

    def list_accessible_document_ids(self, user_id: int) -> list[int]:
        return [10, 11]

    def ensure_user_can_access_document(self, user_id: int, document_id: int) -> None:
        if self.denied:
            raise DocumentAccessDeniedError(
                f"User {user_id} cannot access document {document_id}."
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


def test_list_documents_filters_by_accessible_document_ids() -> None:
    document_service = FakeDocumentManagementService()

    response = list_documents(
        current_user=_build_user(),
        document_management_service=document_service,
        permission_service=FakePermissionService(),
    )

    assert response == []
    assert document_service.document_ids == [10, 11]


def test_get_document_blocks_inaccessible_document() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_document(
            document_id=10,
            current_user=_build_user(),
            document_management_service=FakeDocumentManagementService(),
            permission_service=FakePermissionService(denied=True),
        )

    assert exc_info.value.status_code == 403


def test_reindex_document_hides_internal_metadata_errors() -> None:
    raw_error = (
        'psycopg.errors.UniqueViolation: duplicate key value violates unique '
        'constraint "uq_document_chunks_position"; SQL: INSERT INTO '
        "document_chunks ... params: {'document_id': 3}"
    )

    with pytest.raises(HTTPException) as exc_info:
        reindex_document(
            document_id=3,
            current_user=_build_user(),
            document_management_service=FakeDocumentManagementService(
                reindex_error=MetadataPersistenceError(raw_error)
            ),
            permission_service=FakePermissionService(),
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to update document metadata."
    assert "psycopg" not in exc_info.value.detail
    assert "INSERT" not in exc_info.value.detail
    assert "document_chunks" not in exc_info.value.detail
