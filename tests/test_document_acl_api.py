from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.documents import get_document, list_documents
from app.schemas.document_management import DocumentDetail, DocumentSummary
from app.services.auth_service import AuthenticatedUser
from app.services.permission_service import DocumentAccessDeniedError


class FakeDocumentManagementService:
    def __init__(self) -> None:
        self.document_ids: list[int] | None = None

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
