from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import (
    get_document_management_service,
    get_permission_service,
)
from app.schemas.document_management import (
    DeleteDocumentResponse,
    DocumentDetail,
    DocumentSummary,
    ReindexDocumentResponse,
)
from app.schemas.permissions import (
    DocumentPermissionResponse,
    GrantDocumentPermissionRequest,
    RevokeDocumentPermissionResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.document_loader import DocumentLoaderError
from app.services.document_management_service import (
    DocumentManagementError,
    DocumentManagementService,
    DocumentStorageError,
)
from app.services.embedding_service import EmbeddingServiceError
from app.services.metadata_service import (
    DocumentMetadataNotFoundError,
    MetadataPersistenceError,
)
from app.services.permission_service import (
    DocumentAccessDeniedError,
    PermissionPersistenceError,
    PermissionService,
    PermissionTargetNotFoundError,
)
from app.services.vector_store import VectorStoreError


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_management_service: DocumentManagementService = Depends(
        get_document_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[DocumentSummary]:
    try:
        document_ids = permission_service.list_accessible_document_ids(
            current_user.id
        )
        return document_management_service.list_documents(document_ids=document_ids)
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc
    except MetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Metadata read failed: {exc}",
        ) from exc


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_management_service: DocumentManagementService = Depends(
        get_document_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DocumentDetail:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        return document_management_service.get_document(document_id)
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc
    except DocumentMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Metadata read failed: {exc}",
        ) from exc


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_management_service: DocumentManagementService = Depends(
        get_document_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DeleteDocumentResponse:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        response = document_management_service.delete_document(document_id)
        audit_log(
            "document.delete",
            user_id=current_user.id,
            document_id=document_id,
            deleted_vectors=response.deleted_vectors,
            deleted_file=response.deleted_file,
        )
        return response
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc
    except DocumentMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Qdrant cleanup failed: {exc}",
        ) from exc
    except MetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Metadata delete failed: {exc}",
        ) from exc
    except DocumentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/{document_id}/reindex", response_model=ReindexDocumentResponse)
def reindex_document(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_management_service: DocumentManagementService = Depends(
        get_document_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> ReindexDocumentResponse:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        response = document_management_service.reindex_document(document_id)
        audit_log(
            "document.reindex",
            user_id=current_user.id,
            document_id=document_id,
            chunks=response.chunks,
            stored_vectors=response.stored_vectors,
        )
        return response
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc
    except DocumentMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (DocumentManagementError, DocumentLoaderError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EmbeddingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding failed: {exc}",
        ) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Qdrant reindex failed: {exc}",
        ) from exc
    except MetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Metadata update failed: {exc}",
        ) from exc


@router.get(
    "/{document_id}/permissions",
    response_model=list[DocumentPermissionResponse],
)
def list_document_permissions(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[DocumentPermissionResponse]:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        return [
            DocumentPermissionResponse(**permission.__dict__)
            for permission in permission_service.list_document_permissions(
                document_id=document_id,
            )
        ]
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc


@router.post(
    "/{document_id}/permissions",
    response_model=DocumentPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_document_permission(
    document_id: int,
    request: GrantDocumentPermissionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DocumentPermissionResponse:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        permission = permission_service.grant_document_access(
            document_id=document_id,
            user_id=request.user_id,
        )
        audit_log(
            "document.permission.grant",
            user_id=current_user.id,
            document_id=document_id,
            target_user_id=request.user_id,
        )
        return DocumentPermissionResponse(**permission.__dict__)
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


@router.delete(
    "/{document_id}/permissions/{user_id}",
    response_model=RevokeDocumentPermissionResponse,
)
def revoke_document_permission(
    document_id: int,
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> RevokeDocumentPermissionResponse:
    try:
        _ensure_document_access(
            permission_service=permission_service,
            current_user=current_user,
            document_id=document_id,
        )
        revoked = permission_service.revoke_document_access(
            document_id=document_id,
            user_id=user_id,
        )
        audit_log(
            "document.permission.revoke",
            user_id=current_user.id,
            document_id=document_id,
            target_user_id=user_id,
            revoked=revoked,
        )
        return RevokeDocumentPermissionResponse(
            document_id=document_id,
            user_id=user_id,
            revoked=revoked,
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


def _ensure_document_access(
    permission_service: PermissionService,
    current_user: AuthenticatedUser,
    document_id: int,
) -> None:
    permission_service.ensure_user_can_access_document(
        user_id=current_user.id,
        document_id=document_id,
    )
