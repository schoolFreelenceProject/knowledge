import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import (
    get_code_repository_management_service,
    get_permission_service,
)
from app.schemas.code import (
    CodeRepositoryDetail,
    CodeRepositorySummary,
    DeleteCodeRepositoryResponse,
    ReindexCodeRepositoryResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.code_metadata_service import (
    CodeMetadataPersistenceError,
    CodeRepositoryMetadataNotFoundError,
)
from app.services.code_parser import CodeParserError
from app.services.code_repository_management_service import (
    CodeRepositoryManagementError,
    CodeRepositoryManagementService,
    CodeRepositoryStorageError,
)
from app.services.code_repository_loader import CodeRepositoryLoaderError
from app.services.embedding_service import EmbeddingServiceError
from app.services.permission_service import (
    CodeRepositoryAccessDeniedError,
    PermissionPersistenceError,
    PermissionService,
    PermissionTargetNotFoundError,
)
from app.services.vector_store import VectorStoreError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code/repositories", tags=["code-repositories"])


@router.get("", response_model=list[CodeRepositorySummary])
def list_code_repositories(
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_repository_management_service: CodeRepositoryManagementService = Depends(
        get_code_repository_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> list[CodeRepositorySummary]:
    try:
        repository_ids = permission_service.list_accessible_code_repository_ids(
            current_user.id
        )
        return code_repository_management_service.list_repositories(
            repository_ids=repository_ids,
        )
    except PermissionPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to verify repository access.",
            exc,
        )
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to load code repositories.",
            exc,
        )


@router.get("/{repository_id}", response_model=CodeRepositoryDetail)
def get_code_repository(
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_repository_management_service: CodeRepositoryManagementService = Depends(
        get_code_repository_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> CodeRepositoryDetail:
    try:
        _ensure_repository_access(
            permission_service=permission_service,
            current_user=current_user,
            repository_id=repository_id,
        )
        return code_repository_management_service.get_repository(repository_id)
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except CodeRepositoryAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this code repository.",
        ) from exc
    except PermissionPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to verify repository access.",
            exc,
        )
    except CodeRepositoryMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to load code repository.",
            exc,
        )


@router.delete("/{repository_id}", response_model=DeleteCodeRepositoryResponse)
def delete_code_repository(
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_repository_management_service: CodeRepositoryManagementService = Depends(
        get_code_repository_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> DeleteCodeRepositoryResponse:
    try:
        _ensure_repository_access(
            permission_service=permission_service,
            current_user=current_user,
            repository_id=repository_id,
        )
        response = code_repository_management_service.delete_repository(repository_id)
        audit_log(
            "code.repository.delete",
            user_id=current_user.id,
            repository_id=repository_id,
            deleted_vectors=response.deleted_vectors,
            deleted_files=response.deleted_files,
        )
        return response
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except CodeRepositoryAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this code repository.",
        ) from exc
    except PermissionPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to verify repository access.",
            exc,
        )
    except CodeRepositoryMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except VectorStoreError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to delete repository vectors.",
            exc,
        )
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to delete repository metadata.",
            exc,
        )
    except CodeRepositoryStorageError as exc:
        _raise_logged_http_exception(
            status.HTTP_409_CONFLICT,
            "Unable to delete stored repository files.",
            exc,
        )


@router.post("/{repository_id}/reindex", response_model=ReindexCodeRepositoryResponse)
def reindex_code_repository(
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_repository_management_service: CodeRepositoryManagementService = Depends(
        get_code_repository_management_service
    ),
    permission_service: PermissionService = Depends(get_permission_service),
) -> ReindexCodeRepositoryResponse:
    try:
        _ensure_repository_access(
            permission_service=permission_service,
            current_user=current_user,
            repository_id=repository_id,
        )
        response = code_repository_management_service.reindex_repository(repository_id)
        audit_log(
            "code.repository.reindex",
            user_id=current_user.id,
            repository_id=repository_id,
            files=response.files,
            chunks=response.chunks,
            stored_vectors=response.stored_vectors,
        )
        return response
    except PermissionTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except CodeRepositoryAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this code repository.",
        ) from exc
    except PermissionPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to verify repository access.",
            exc,
        )
    except CodeRepositoryMetadataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code repository not found.",
        ) from exc
    except CodeRepositoryStorageError as exc:
        _raise_logged_http_exception(
            status.HTTP_409_CONFLICT,
            "Stored repository files are unavailable.",
            exc,
        )
    except (
        CodeRepositoryManagementError,
        CodeRepositoryLoaderError,
        CodeParserError,
        ValueError,
    ) as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Code repository could not be reindexed.",
            exc,
        )
    except EmbeddingServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to generate repository embeddings.",
            exc,
        )
    except VectorStoreError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to update repository vectors.",
            exc,
        )
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to update repository metadata.",
            exc,
        )


def _ensure_repository_access(
    permission_service: PermissionService,
    current_user: AuthenticatedUser,
    repository_id: int,
) -> None:
    permission_service.ensure_user_can_access_code_repository(
        user_id=current_user.id,
        repository_id=repository_id,
    )


def _raise_logged_http_exception(
    status_code: int,
    detail: str,
    exc: Exception,
) -> NoReturn:
    logger.exception(detail)
    raise HTTPException(status_code=status_code, detail=detail) from exc
