import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_ingestion_service
from app.core.config import get_settings
from app.schemas.ingest import FolderIngestResponse, IngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.document_loader import DocumentLoaderError
from app.services.embedding_service import EmbeddingServiceError
from app.services.ingestion_service import (
    EmptyUploadError,
    FolderUploadItem,
    IngestionService,
    IngestionServiceError,
    UploadedDocumentConflictError,
    UploadedDocumentStorageError,
)
from app.services.metadata_service import MetadataPersistenceError
from app.services.permission_service import PermissionServiceError
from app.services.vector_store import VectorStoreError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ingestion"])
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> IngestResponse:
    settings = get_settings()
    try:
        content = await _read_upload_content_with_limit(
            file,
            max_file_bytes=settings.max_upload_file_size,
        )
        response = ingestion_service.ingest_uploaded_document(
            filename=file.filename or "",
            content=content,
            uploader_user_id=current_user.id,
        )
        audit_log(
            "document.ingest",
            user_id=current_user.id,
            document_id=response.document_id,
            filename=response.filename,
            chunks=response.chunks,
        )
        return response
    except EmptyUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UploadedDocumentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UploadedDocumentStorageError as exc:
        _raise_logged_http_exception(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Uploaded document could not be saved.",
            exc,
        )
    except (IngestionServiceError, DocumentLoaderError, ValueError) as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Uploaded document could not be processed.",
            exc,
        )
    except EmbeddingServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to generate document embeddings.",
            exc,
        )
    except VectorStoreError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to store document vectors.",
            exc,
        )
    except MetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to save document metadata.",
            exc,
        )
    finally:
        await file.close()


@router.post(
    "/ingest/folder",
    response_model=FolderIngestResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_document_folder(
    folder_name: str = Form(...),
    relative_paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> FolderIngestResponse:
    settings = get_settings()
    try:
        if len(files) != len(relative_paths):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder upload files and relative paths do not match.",
            )

        if len(files) > settings.max_bulk_file_count:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Folder upload has too many files. "
                    f"Maximum allowed file count is {settings.max_bulk_file_count}."
                ),
            )

        total_file_bytes = 0
        folder_files: list[FolderUploadItem] = []
        for upload, relative_path in zip(files, relative_paths, strict=True):
            content = await _read_upload_content_with_limit(
                upload,
                max_file_bytes=settings.max_upload_file_size,
            )
            total_file_bytes += len(content)
            if total_file_bytes > settings.max_bulk_upload_size:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        "Folder upload is too large. "
                        "Maximum allowed total size is "
                        f"{settings.max_bulk_upload_size} bytes."
                    ),
                )
            folder_files.append(
                FolderUploadItem(relative_path=relative_path, content=content)
            )

        response = ingestion_service.ingest_folder_documents(
            folder_name=folder_name,
            files=folder_files,
            uploader_user_id=current_user.id,
        )
        audit_log(
            "document.folder_ingest",
            user_id=current_user.id,
            folder_name=response.folder_name,
            files_discovered=response.files_discovered,
            indexed=response.indexed,
            skipped=response.skipped,
            failed=response.failed,
        )
        return response
    except HTTPException:
        raise
    except (IngestionServiceError, ValueError) as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Folder upload could not be processed.",
            exc,
        )
    except MetadataPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to save folder document metadata.",
            exc,
        )
    except PermissionServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to grant folder document access.",
            exc,
        )
    finally:
        for upload in files:
            await upload.close()


async def _read_upload_content_with_limit(
    upload: UploadFile,
    max_file_bytes: int,
) -> bytes:
    content = bytearray()
    while True:
        chunk = await upload.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break

        content.extend(chunk)
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Uploaded file is too large. "
                    f"Maximum allowed file size is {max_file_bytes} bytes."
                ),
            )

    return bytes(content)


def _raise_logged_http_exception(
    status_code: int,
    detail: str,
    exc: Exception,
) -> NoReturn:
    logger.exception(detail)
    raise HTTPException(status_code=status_code, detail=detail) from exc
