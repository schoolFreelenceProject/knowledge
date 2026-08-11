from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_permission_service
from app.schemas.permissions import (
    CodeRepositoryPermissionResponse,
    DocumentPermissionResponse,
    GrantCodeRepositoryPermissionRequest,
    GrantCodeRepositoryToUserRequest,
    GrantDocumentPermissionRequest,
    GrantDocumentToUserRequest,
    RevokeCodeRepositoryPermissionResponse,
    RevokeDocumentPermissionResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.permission_service import (
    PermissionPersistenceError,
    PermissionService,
    PermissionTargetNotFoundError,
)


router = APIRouter(prefix="/api/admin/permissions", tags=["admin-permissions"])


@router.get(
    "/users/{user_id}/documents",
    response_model=list[DocumentPermissionResponse],
)
def list_user_document_permissions(
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[DocumentPermissionResponse]:
    _ = current_user
    try:
        return _to_document_permission_responses(
            permission_service.list_document_permissions_for_user(user_id=user_id)
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc


@router.post(
    "/users/{user_id}/documents",
    response_model=DocumentPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_user_document_permission(
    user_id: int,
    request: GrantDocumentToUserRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DocumentPermissionResponse:
    try:
        permission = permission_service.grant_document_access(
            document_id=request.document_id,
            user_id=user_id,
        )
        audit_log(
            "admin.permission.document.grant",
            user_id=current_user.id,
            document_id=request.document_id,
            target_user_id=user_id,
        )
        return DocumentPermissionResponse(**permission.__dict__)
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


@router.delete(
    "/users/{user_id}/documents/{document_id}",
    response_model=RevokeDocumentPermissionResponse,
)
def revoke_user_document_permission(
    user_id: int,
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> RevokeDocumentPermissionResponse:
    try:
        revoked = permission_service.revoke_document_access(
            document_id=document_id,
            user_id=user_id,
        )
        audit_log(
            "admin.permission.document.revoke",
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
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


@router.get(
    "/documents/{document_id}/users",
    response_model=list[DocumentPermissionResponse],
)
def list_document_user_permissions(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[DocumentPermissionResponse]:
    _ = current_user
    try:
        return _to_document_permission_responses(
            permission_service.list_document_permissions(document_id=document_id)
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc


@router.post(
    "/documents/{document_id}/users",
    response_model=DocumentPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_document_user_permission(
    document_id: int,
    request: GrantDocumentPermissionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DocumentPermissionResponse:
    return grant_user_document_permission(
        user_id=request.user_id,
        request=GrantDocumentToUserRequest(document_id=document_id),
        current_user=current_user,
        permission_service=permission_service,
    )


@router.delete(
    "/documents/{document_id}/users/{user_id}",
    response_model=RevokeDocumentPermissionResponse,
)
def revoke_document_user_permission(
    document_id: int,
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> RevokeDocumentPermissionResponse:
    return revoke_user_document_permission(
        user_id=user_id,
        document_id=document_id,
        current_user=current_user,
        permission_service=permission_service,
    )


@router.get(
    "/users/{user_id}/code-repositories",
    response_model=list[CodeRepositoryPermissionResponse],
)
def list_user_code_repository_permissions(
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[CodeRepositoryPermissionResponse]:
    _ = current_user
    try:
        return _to_code_repository_permission_responses(
            permission_service.list_code_repository_permissions_for_user(
                user_id=user_id,
            )
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc


@router.post(
    "/users/{user_id}/code-repositories",
    response_model=CodeRepositoryPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_user_code_repository_permission(
    user_id: int,
    request: GrantCodeRepositoryToUserRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> CodeRepositoryPermissionResponse:
    try:
        permission = permission_service.grant_code_repository_access(
            repository_id=request.repository_id,
            user_id=user_id,
        )
        audit_log(
            "admin.permission.code_repository.grant",
            user_id=current_user.id,
            repository_id=request.repository_id,
            target_user_id=user_id,
        )
        return CodeRepositoryPermissionResponse(**permission.__dict__)
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


@router.delete(
    "/users/{user_id}/code-repositories/{repository_id}",
    response_model=RevokeCodeRepositoryPermissionResponse,
)
def revoke_user_code_repository_permission(
    user_id: int,
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> RevokeCodeRepositoryPermissionResponse:
    try:
        revoked = permission_service.revoke_code_repository_access(
            repository_id=repository_id,
            user_id=user_id,
        )
        audit_log(
            "admin.permission.code_repository.revoke",
            user_id=current_user.id,
            repository_id=repository_id,
            target_user_id=user_id,
            revoked=revoked,
        )
        return RevokeCodeRepositoryPermissionResponse(
            repository_id=repository_id,
            user_id=user_id,
            revoked=revoked,
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission update failed: {exc}",
        ) from exc


@router.get(
    "/code-repositories/{repository_id}/users",
    response_model=list[CodeRepositoryPermissionResponse],
)
def list_code_repository_user_permissions(
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[CodeRepositoryPermissionResponse]:
    _ = current_user
    try:
        return _to_code_repository_permission_responses(
            permission_service.list_code_repository_permissions(
                repository_id=repository_id,
            )
        )
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Permission lookup failed: {exc}",
        ) from exc


@router.post(
    "/code-repositories/{repository_id}/users",
    response_model=CodeRepositoryPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_code_repository_user_permission(
    repository_id: int,
    request: GrantCodeRepositoryPermissionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> CodeRepositoryPermissionResponse:
    return grant_user_code_repository_permission(
        user_id=request.user_id,
        request=GrantCodeRepositoryToUserRequest(repository_id=repository_id),
        current_user=current_user,
        permission_service=permission_service,
    )


@router.delete(
    "/code-repositories/{repository_id}/users/{user_id}",
    response_model=RevokeCodeRepositoryPermissionResponse,
)
def revoke_code_repository_user_permission(
    repository_id: int,
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> RevokeCodeRepositoryPermissionResponse:
    return revoke_user_code_repository_permission(
        user_id=user_id,
        repository_id=repository_id,
        current_user=current_user,
        permission_service=permission_service,
    )


def _to_document_permission_responses(permissions) -> list[DocumentPermissionResponse]:
    return [
        DocumentPermissionResponse(**permission.__dict__)
        for permission in permissions
    ]


def _to_code_repository_permission_responses(
    permissions,
) -> list[CodeRepositoryPermissionResponse]:
    return [
        CodeRepositoryPermissionResponse(**permission.__dict__)
        for permission in permissions
    ]
