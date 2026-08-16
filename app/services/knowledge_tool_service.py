import logging

from app.schemas.mcp import (
    MCPAskKnowledgeResponse,
    MCPAskKnowledgeSource,
    MCPCodeMetadata,
    MCPContentType,
    MCPDocumentChunkDetail,
    MCPDocumentDetail,
    MCPDocumentMetadata,
    MCPSearchCodeResponse,
    MCPSearchKnowledgeResponse,
    MCPSearchResult,
)
from app.services.chat_service import RAGChatService
from app.services.document_management_service import DocumentManagementService
from app.services.generation_service import (
    INTERNAL_GENERATION_UNAVAILABLE_MESSAGE,
    InternalGenerationUnavailableError,
)
from app.services.permission_service import PermissionService
from app.services.rag_trace_service import RAGTraceService
from app.services.retrieval_service import RetrievalService
from app.services.trace_context import (
    RAGTraceContext,
    generate_request_id,
    reset_current_trace_context,
    set_current_trace_context,
)


logger = logging.getLogger(__name__)
MAX_TOOL_TOP_K = 20


class KnowledgeToolServiceError(RuntimeError):
    """Raised when a read-only MCP knowledge tool cannot complete."""


class KnowledgeToolService:
    def __init__(
        self,
        chat_service: RAGChatService,
        retrieval_service: RetrievalService,
        permission_service: PermissionService,
        document_management_service: DocumentManagementService,
        trace_service: RAGTraceService,
    ) -> None:
        self.chat_service = chat_service
        self.retrieval_service = retrieval_service
        self.permission_service = permission_service
        self.document_management_service = document_management_service
        self.trace_service = trace_service

    def search_knowledge(
        self,
        user_id: int,
        query: str,
        top_k: int,
        request_id: str | None = None,
        content_type: MCPContentType = "all",
    ) -> MCPSearchKnowledgeResponse:
        request_id = _normalize_request_id(request_id)
        allowed_point_ids = self.permission_service.list_accessible_qdrant_point_ids(
            user_id
        )
        results = self.retrieval_service.retrieve(
            query=query,
            top_k=_validate_top_k(top_k),
            allowed_point_ids=allowed_point_ids,
            content_types=_content_type_filter(content_type),
        )
        response = MCPSearchKnowledgeResponse(
            request_id=request_id,
            results=[_to_search_result(result) for result in results],
        )
        _log_tool_success(
            tool_name="search_knowledge",
            request_id=request_id,
            user_id=user_id,
            result_count=len(response.results),
        )
        return response

    def ask_knowledge(
        self,
        user_id: int,
        question: str,
        top_k: int,
        request_id: str | None = None,
    ) -> MCPAskKnowledgeResponse:
        request_id = _normalize_request_id(request_id)
        trace_context = _build_trace_context(
            request_id=request_id,
            user_id=user_id,
            question=question,
            chat_service=self.chat_service,
        )
        trace_token = set_current_trace_context(trace_context)

        try:
            allowed_point_ids = (
                self.permission_service.list_accessible_qdrant_point_ids(user_id)
            )
            chat_response = self.chat_service.answer_question(
                question=question,
                top_k=_validate_top_k(top_k),
                allowed_point_ids=allowed_point_ids,
            )
            trace_context.finish_success()
            response = MCPAskKnowledgeResponse(
                request_id=request_id,
                answer=chat_response.answer,
                sources=[
                    MCPAskKnowledgeSource(
                        filename=source.filename,
                        page_number=source.page_number,
                        score=source.score,
                    )
                    for source in chat_response.sources
                ],
            )
            _log_tool_success(
                tool_name="ask_knowledge",
                request_id=request_id,
                user_id=user_id,
                result_count=len(response.sources),
            )
            return response
        except InternalGenerationUnavailableError as exc:
            trace_context.finish_error(str(exc))
            logger.info(
                "mcp_tool_generation_unavailable tool=ask_knowledge "
                "request_id=%s user_id=%s",
                request_id,
                user_id,
            )
            return MCPAskKnowledgeResponse(
                request_id=request_id,
                answer=(
                    f"{INTERNAL_GENERATION_UNAVAILABLE_MESSAGE} "
                    "Use search_knowledge or search_code for retrieved sources."
                ),
                sources=[],
            )
        except Exception as exc:
            trace_context.finish_error(str(exc))
            logger.warning(
                "mcp_tool_failed tool=ask_knowledge request_id=%s user_id=%s",
                request_id,
                user_id,
                exc_info=True,
            )
            raise
        finally:
            if trace_context.total_time_ms is None:
                trace_context.finish_success()
            _save_trace_best_effort(
                trace_service=self.trace_service,
                trace_context=trace_context,
            )
            reset_current_trace_context(trace_token)

    def get_document(
        self,
        user_id: int,
        document_id: int,
        request_id: str | None = None,
    ) -> MCPDocumentDetail:
        request_id = _normalize_request_id(request_id)
        self.permission_service.ensure_user_can_access_document(
            user_id=user_id,
            document_id=document_id,
        )
        document = self.document_management_service.get_document(document_id)
        response = MCPDocumentDetail(
            request_id=request_id,
            id=document.id,
            filename=document.filename,
            file_type=document.file_type,
            storage_path=document.storage_path,
            file_hash=document.file_hash,
            status=document.status,
            created_at=document.created_at,
            updated_at=document.updated_at,
            chunk_count=document.chunk_count,
            chunks=[
                MCPDocumentChunkDetail(
                    id=chunk.id,
                    qdrant_point_id=chunk.qdrant_point_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section_heading=chunk.section_heading,
                    heading_path=chunk.heading_path,
                    block_kind=chunk.block_kind,
                    workbook=chunk.workbook,
                    sheet_name=chunk.sheet_name,
                    cell_range=chunk.cell_range,
                    row_start=chunk.row_start,
                    row_end=chunk.row_end,
                    slide_number=chunk.slide_number,
                    slide_title=chunk.slide_title,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    created_at=chunk.created_at,
                )
                for chunk in document.chunks
            ],
        )
        _log_tool_success(
            tool_name="get_document",
            request_id=request_id,
            user_id=user_id,
            result_count=1,
        )
        return response

    def search_code(
        self,
        user_id: int,
        query: str,
        top_k: int,
        request_id: str | None = None,
        language: str | None = None,
    ) -> MCPSearchCodeResponse:
        request_id = _normalize_request_id(request_id)
        allowed_point_ids = self.permission_service.list_accessible_qdrant_point_ids(
            user_id
        )
        results = self.retrieval_service.retrieve(
            query=query,
            top_k=_validate_top_k(top_k),
            allowed_point_ids=allowed_point_ids,
            content_types=["code"],
            languages=_language_filter(language),
        )
        response = MCPSearchCodeResponse(
            request_id=request_id,
            results=[_to_search_result(result) for result in results],
        )
        _log_tool_success(
            tool_name="search_code",
            request_id=request_id,
            user_id=user_id,
            result_count=len(response.results),
        )
        return response


def _validate_top_k(top_k: int) -> int:
    if top_k < 1 or top_k > MAX_TOOL_TOP_K:
        raise KnowledgeToolServiceError(
            f"top_k must be between 1 and {MAX_TOOL_TOP_K}."
        )

    return top_k


def _normalize_request_id(request_id: str | None) -> str:
    if request_id is None:
        return generate_request_id()

    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        return generate_request_id()

    return normalized_request_id[:255]


def _content_type_filter(content_type: MCPContentType) -> list[str] | None:
    if content_type == "all":
        return None

    return [content_type]


def _language_filter(language: str | None) -> list[str] | None:
    if language is None:
        return None

    normalized_language = language.strip().casefold()
    if not normalized_language:
        return None

    return [normalized_language]


def _to_search_result(result) -> MCPSearchResult:
    metadata = result.metadata
    code_metadata = None
    if metadata.content_type == "code":
        code_metadata = MCPCodeMetadata(
            repo=metadata.repo_name,
            repo_url=metadata.repo_url,
            branch=metadata.branch,
            commit_sha=metadata.commit_sha,
            file_path=metadata.repository_file_path,
            language=metadata.language,
            symbol_name=metadata.symbol_name,
            symbol_kind=metadata.symbol_kind,
            start_line=metadata.start_line,
            end_line=metadata.end_line,
        )

    return MCPSearchResult(
        text=result.text,
        source_type=metadata.content_type,
        filename=result.filename,
        source_path=metadata.source_path,
        score=result.score,
        vector_score=result.vector_score,
        bm25_score=result.bm25_score,
        fusion_score=result.fusion_score,
        reranker_score=result.reranker_score,
        document_metadata=MCPDocumentMetadata(
            page_number=metadata.page_number,
            section_heading=metadata.section_heading,
            heading_path=metadata.heading_path,
            block_kind=metadata.block_kind,
            workbook=metadata.workbook,
            sheet_name=metadata.sheet_name,
            cell_range=metadata.cell_range,
            row_start=metadata.row_start,
            row_end=metadata.row_end,
            slide_number=metadata.slide_number,
            slide_title=metadata.slide_title,
            chunk_index=metadata.chunk_index,
            start_char=metadata.start_char,
            end_char=metadata.end_char,
        ),
        code_metadata=code_metadata,
    )


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


def _save_trace_best_effort(
    trace_service: RAGTraceService,
    trace_context: RAGTraceContext,
) -> None:
    try:
        trace_service.save_trace(trace_context)
    except Exception:
        logger.warning(
            "Failed to persist MCP RAG trace for request_id=%s",
            trace_context.request_id,
            exc_info=True,
        )


def _log_tool_success(
    tool_name: str,
    request_id: str,
    user_id: int,
    result_count: int,
) -> None:
    logger.info(
        "mcp_tool_completed tool=%s request_id=%s user_id=%s result_count=%s",
        tool_name,
        request_id,
        user_id,
        result_count,
    )
