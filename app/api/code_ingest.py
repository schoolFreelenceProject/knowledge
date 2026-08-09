from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_code_ingestion_service
from app.schemas.code import CodeIngestRequest, CodeIngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.code_ingestion_service import (
    CodeIngestionService,
    CodeIngestionServiceError,
    CodeRepositoryIngestionConflictError,
)
from app.services.code_metadata_service import CodeMetadataPersistenceError
from app.services.code_parser import CodeParserError
from app.services.code_repository_loader import CodeRepositoryLoaderError
from app.services.embedding_service import EmbeddingServiceError
from app.services.vector_store import VectorStoreError


router = APIRouter(prefix="/api/code", tags=["code-ingestion"])


@router.post(
    "/ingest",
    response_model=CodeIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_code_repository(
    request: CodeIngestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_ingestion_service: CodeIngestionService = Depends(
        get_code_ingestion_service
    ),
) -> CodeIngestResponse:
    try:
        response = code_ingestion_service.ingest_repository(
            repo_url=request.repo_url,
            branch=request.branch,
            include_globs=request.include_globs,
            exclude_globs=request.exclude_globs,
            uploader_user_id=current_user.id,
        )
        audit_log(
            "code.ingest",
            user_id=current_user.id,
            repository_id=response.repository_id,
            repo_name=response.repo_name,
            branch=response.branch,
            chunks=response.chunks,
        )
        return response
    except CodeRepositoryIngestionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (CodeIngestionServiceError, CodeRepositoryLoaderError, CodeParserError) as exc:
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
            detail=f"Vector storage failed: {exc}",
        ) from exc
    except CodeMetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Code metadata persistence failed: {exc}",
        ) from exc
