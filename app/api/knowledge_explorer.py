import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_knowledge_explorer_service
from app.schemas.knowledge_explorer import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.code_metadata_service import CodeMetadataPersistenceError
from app.services.embedding_service import EmbeddingServiceError
from app.services.knowledge_explorer_service import (
    KnowledgeExplorerError,
    KnowledgeExplorerService,
)
from app.services.metadata_service import MetadataPersistenceError
from app.services.permission_service import PermissionPersistenceError
from app.services.retrieval_service import RetrievalServiceError
from app.services.vector_store import VectorStoreError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge-explorer"])


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    explorer_service: KnowledgeExplorerService = Depends(
        get_knowledge_explorer_service
    ),
) -> KnowledgeSearchResponse:
    try:
        return explorer_service.search(
            request=request,
            user_id=current_user.id,
        )
    except RetrievalServiceError as exc:
        _raise_logged_http_exception(
            status.HTTP_400_BAD_REQUEST,
            "Knowledge search query could not be processed.",
            exc,
        )
    except PermissionPersistenceError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to verify knowledge access.",
            exc,
        )
    except (EmbeddingServiceError, VectorStoreError) as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Knowledge search could not be completed.",
            exc,
        )
    except (MetadataPersistenceError, CodeMetadataPersistenceError) as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Unable to load knowledge source details.",
            exc,
        )
    except KnowledgeExplorerError as exc:
        _raise_logged_http_exception(
            status.HTTP_502_BAD_GATEWAY,
            "Knowledge source details could not be inspected.",
            exc,
        )


def _raise_logged_http_exception(
    status_code: int,
    detail: str,
    exc: Exception,
) -> NoReturn:
    logger.exception(detail)
    raise HTTPException(status_code=status_code, detail=detail) from exc
