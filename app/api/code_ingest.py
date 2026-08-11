import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_code_ingestion_service
from app.schemas.code import CodeIngestRequest, CodeIngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.code_ingestion_service import (
    CodeFolderUploadFile,
    CodeIngestionService,
    CodeIngestionServiceError,
    CodeRepositoryIngestionConflictError,
)
from app.services.code_metadata_service import CodeMetadataPersistenceError
from app.services.code_parser import CodeParserError
from app.services.code_repository_loader import CodeRepositoryLoaderError
from app.services.embedding_service import EmbeddingServiceError
from app.services.permission_service import PermissionServiceError
from app.services.vector_store import VectorStoreError


logger = logging.getLogger(__name__)
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
            detail="This repository revision is already indexed.",
        ) from exc
    except (CodeIngestionServiceError, CodeRepositoryLoaderError, CodeParserError) as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Code repository could not be processed.",
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
            "Unable to store repository vectors.",
            exc,
        )
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to save repository metadata.",
            exc,
        )


@router.post(
    "/ingest/folder",
    response_model=CodeIngestResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_code_folder(
    folder_name: str = Form(...),
    relative_paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    code_ingestion_service: CodeIngestionService = Depends(
        get_code_ingestion_service
    ),
) -> CodeIngestResponse:
    try:
        if len(files) != len(relative_paths):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code folder upload files and relative paths do not match.",
            )

        folder_files = [
            CodeFolderUploadFile(
                relative_path=relative_path,
                content=await upload.read(),
            )
            for upload, relative_path in zip(files, relative_paths, strict=True)
        ]
        response = code_ingestion_service.ingest_uploaded_folder(
            folder_name=folder_name,
            files=folder_files,
            uploader_user_id=current_user.id,
        )
        audit_log(
            "code.folder_ingest",
            user_id=current_user.id,
            repository_id=response.repository_id,
            repo_name=response.repo_name,
            files=response.files,
            chunks=response.chunks,
            skipped_files=response.skipped_files,
        )
        return response
    except HTTPException:
        raise
    except (CodeIngestionServiceError, CodeRepositoryLoaderError, CodeParserError) as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Code folder could not be processed.",
            exc,
        )
    except EmbeddingServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to generate code folder embeddings.",
            exc,
        )
    except VectorStoreError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to store code folder vectors.",
            exc,
        )
    except CodeMetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to save code folder metadata.",
            exc,
        )
    except PermissionServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to grant code folder access.",
            exc,
        )
    finally:
        for upload in files:
            await upload.close()


def _raise_logged_http_exception(
    status_code: int,
    detail: str,
    exc: Exception,
) -> NoReturn:
    logger.exception(detail)
    raise HTTPException(status_code=status_code, detail=detail) from exc
