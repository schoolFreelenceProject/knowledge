from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_ingestion_service
from app.schemas.ingest import IngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.audit_log import audit_log
from app.services.document_loader import DocumentLoaderError
from app.services.embedding_service import EmbeddingServiceError
from app.services.ingestion_service import (
    EmptyUploadError,
    IngestionService,
    IngestionServiceError,
    UploadedDocumentConflictError,
    UploadedDocumentStorageError,
)
from app.services.metadata_service import MetadataPersistenceError
from app.services.vector_store import VectorStoreError


router = APIRouter(prefix="/api", tags=["ingestion"])


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
    try:
        content = await file.read()
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except (IngestionServiceError, DocumentLoaderError, ValueError) as exc:
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
    except MetadataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Metadata persistence failed: {exc}",
        ) from exc
    finally:
        await file.close()
