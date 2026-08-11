import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import (
    get_chat_service,
    get_permission_service,
    get_rag_trace_service,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.auth_service import AuthenticatedUser
from app.services.chat_service import RAGChatService
from app.services.embedding_service import EmbeddingServiceError
from app.services.generation_service import (
    GenerationServiceError,
    InternalGenerationUnavailableError,
)
from app.services.permission_service import PermissionPersistenceError, PermissionService
from app.services.rag_trace_service import RAGTraceService
from app.services.retrieval_service import RetrievalServiceError
from app.services.trace_context import (
    RAGTraceContext,
    generate_request_id,
    reset_current_trace_context,
    set_current_trace_context,
)
from app.services.vector_store import VectorStoreError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])
REQUEST_ID_HEADER = "X-Request-ID"


@router.post("/chat", response_model=ChatResponse)
def chat(
    chat_request: ChatRequest,
    http_request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
    chat_service: RAGChatService = Depends(get_chat_service),
    permission_service: PermissionService = Depends(get_permission_service),
    trace_service: RAGTraceService = Depends(get_rag_trace_service),
) -> ChatResponse:
    request_id = _resolve_request_id(http_request)
    response.headers[REQUEST_ID_HEADER] = request_id
    trace_context = _build_trace_context(
        request_id=request_id,
        user_id=current_user.id,
        question=chat_request.question,
        chat_service=chat_service,
    )
    trace_token = set_current_trace_context(trace_context)

    try:
        if not chat_request.question.strip():
            detail = "Question cannot be empty."
            trace_context.finish_error(detail)
            raise _http_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
                request_id=request_id,
            )

        allowed_point_ids = permission_service.list_accessible_qdrant_point_ids(
            current_user.id
        )
        chat_response = chat_service.answer_question(
            question=chat_request.question,
            top_k=chat_request.top_k,
            allowed_point_ids=allowed_point_ids,
        )
        trace_context.finish_success()
        return chat_response
    except PermissionPersistenceError as exc:
        detail = "Permission lookup failed."
        trace_context.finish_error(str(exc))
        logger.warning(
            "chat_permission_lookup_failed request_id=%s",
            request_id,
            exc_info=True,
        )
        raise _http_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
            request_id=request_id,
        ) from exc
    except (EmbeddingServiceError, RetrievalServiceError, VectorStoreError) as exc:
        detail = "Knowledge retrieval failed."
        trace_context.finish_error(str(exc))
        logger.warning(
            "chat_retrieval_failed request_id=%s",
            request_id,
            exc_info=True,
        )
        raise _http_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
            request_id=request_id,
        ) from exc
    except InternalGenerationUnavailableError as exc:
        detail = "Internal answer generation is not configured."
        trace_context.finish_error(str(exc))
        logger.info("chat_generation_unavailable request_id=%s", request_id)
        raise _http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            request_id=request_id,
        ) from exc
    except GenerationServiceError as exc:
        detail = "Internal answer generation failed."
        trace_context.finish_error(str(exc))
        logger.warning(
            "chat_generation_failed request_id=%s",
            request_id,
            exc_info=True,
        )
        raise _http_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
            request_id=request_id,
        ) from exc
    except HTTPException as exc:
        if trace_context.total_time_ms is None:
            trace_context.finish_error(str(exc.detail))
        raise
    except Exception as exc:
        trace_context.finish_error(str(exc))
        raise
    finally:
        if trace_context.total_time_ms is None:
            trace_context.finish_success()

        _save_trace_best_effort(
            trace_service=trace_service,
            trace_context=trace_context,
        )
        reset_current_trace_context(trace_token)


def _resolve_request_id(http_request: Request) -> str:
    request_id = http_request.headers.get(REQUEST_ID_HEADER)
    if request_id is None:
        return generate_request_id()

    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        return generate_request_id()

    return normalized_request_id[:255]


def _build_trace_context(
    request_id: str,
    user_id: int,
    question: str,
    chat_service: RAGChatService,
) -> RAGTraceContext:
    retrieval_service = getattr(chat_service, "retrieval_service", None)
    generation_service = getattr(chat_service, "generation_service", None)
    retrieval_mode = getattr(
        getattr(retrieval_service, "config", None),
        "mode",
        "unknown",
    )
    model_name = getattr(
        getattr(generation_service, "ollama_service", None),
        "model",
        "none" if generation_service is None else "unknown",
    )
    return RAGTraceContext(
        request_id=request_id,
        user_id=user_id,
        question=question,
        retrieval_mode=str(retrieval_mode),
        model_name=str(model_name),
    )


def _http_error(
    status_code: int,
    detail: str,
    request_id: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={REQUEST_ID_HEADER: request_id},
    )


def _save_trace_best_effort(
    trace_service: RAGTraceService,
    trace_context: RAGTraceContext,
) -> None:
    try:
        trace_service.save_trace(trace_context)
    except Exception:
        logger.warning(
            "Failed to persist RAG trace for request_id=%s",
            trace_context.request_id,
            exc_info=True,
        )
