from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.api.chat import REQUEST_ID_HEADER, chat
from app.schemas.chat import ChatRequest
from app.schemas.documents import ChunkMetadata, GeneratedAnswer, RetrievalResult
from app.services.auth_service import AuthenticatedUser
from app.services.chat_service import RAGChatService
from app.services.generation_service import RAGGenerationService
from app.services.prompt_builder import RAGPromptBuilder
from app.services.rag_trace_service import RAGTracePersistenceError
from app.services.reranker_service import CrossEncoderRerankerService, RerankerConfig
from app.services.retrieval_service import RetrievalConfig, RetrievalService
from app.services.trace_context import (
    RAGTraceContext,
    get_current_trace_context,
    reset_current_trace_context,
    set_current_trace_context,
)


class FakeEmbeddingService:
    def embed_texts(self, texts):
        return [[1.0, 0.0] for _text in texts]


class FakeVectorStore:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results

    def search_similar(self, query_vector, top_k, allowed_point_ids=None):
        return self.results[:top_k]


class FakeRetrievalService:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.config = RetrievalConfig(mode="hybrid")
        self.allowed_point_ids: list[str] | None = None

    def retrieve(self, query, top_k, allowed_point_ids=None):
        self.allowed_point_ids = allowed_point_ids
        return self.results[:top_k]


class FakeGenerationService:
    class FakeOllamaService:
        model = "fake-llm"

    ollama_service = FakeOllamaService()

    def generate_answer(self, question, retrieval_results):
        return GeneratedAnswer(answer="Remote work answer.", sources=[])


class FakeOllamaGenerationService:
    model = "fake-llm"

    def generate(self, prompt: str) -> str:
        return "Generated answer."


class FakeCrossEncoder:
    def predict(self, pairs, batch_size, show_progress_bar):
        return [0.7 for _pair in pairs]


class FakePermissionService:
    def list_accessible_qdrant_point_ids(self, user_id: int) -> list[str]:
        return ["point-1"]


class FakeTraceService:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.saved_traces: list[RAGTraceContext] = []

    def save_trace(self, trace_context: RAGTraceContext):
        if self.fail:
            raise RAGTracePersistenceError("trace database unavailable")

        self.saved_traces.append(deepcopy(trace_context))


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_http_request(request_id: str | None = None) -> Request:
    headers = []
    if request_id is not None:
        headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": headers,
        }
    )


def _build_result() -> RetrievalResult:
    return RetrievalResult(
        text="Remote work policy text.",
        filename="company_policy.md",
        page_number=None,
        score=0.91,
        vector_score=0.82,
        bm25_score=1.6,
        fusion_score=0.44,
        reranker_score=0.91,
        metadata=ChunkMetadata(
            filename="company_policy.md",
            source_path="company_policy.md",
            file_type="markdown",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=24,
        ),
    )


def test_chat_api_accepts_and_returns_request_id_and_saves_success_trace() -> None:
    trace_service = FakeTraceService()
    response = Response()
    retrieval_service = FakeRetrievalService(results=[_build_result()])
    chat_service = RAGChatService(
        retrieval_service=retrieval_service,
        generation_service=FakeGenerationService(),
    )

    result = chat(
        chat_request=ChatRequest(question="What is the remote work policy?"),
        http_request=_build_http_request("req-123"),
        response=response,
        current_user=_build_user(),
        chat_service=chat_service,
        permission_service=FakePermissionService(),
        trace_service=trace_service,
    )

    assert result.answer == "Remote work answer."
    assert response.headers[REQUEST_ID_HEADER] == "req-123"
    assert retrieval_service.allowed_point_ids == ["point-1"]
    assert get_current_trace_context() is None

    saved_trace = trace_service.saved_traces[0]
    assert saved_trace.request_id == "req-123"
    assert saved_trace.user_id == 1
    assert saved_trace.question == "What is the remote work policy?"
    assert saved_trace.retrieval_mode == "hybrid"
    assert saved_trace.model_name == "fake-llm"
    assert saved_trace.status == "SUCCESS"
    assert saved_trace.total_time_ms is not None
    assert saved_trace.retrieved_count == 1
    assert saved_trace.retrieved_sources[0]["filename"] == "company_policy.md"
    assert saved_trace.retrieved_sources[0]["vector_score"] == 0.82
    assert saved_trace.retrieved_sources[0]["bm25_score"] == 1.6
    assert saved_trace.retrieved_sources[0]["fusion_score"] == 0.44
    assert saved_trace.retrieved_sources[0]["reranker_score"] == 0.91


def test_chat_api_generates_request_id_when_missing() -> None:
    trace_service = FakeTraceService()
    response = Response()
    chat_service = RAGChatService(
        retrieval_service=FakeRetrievalService(results=[]),
        generation_service=FakeGenerationService(),
    )

    chat(
        chat_request=ChatRequest(question="What is the leave policy?"),
        http_request=_build_http_request(),
        response=response,
        current_user=_build_user(),
        chat_service=chat_service,
        permission_service=FakePermissionService(),
        trace_service=trace_service,
    )

    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id
    assert trace_service.saved_traces[0].request_id == request_id


def test_chat_api_trace_failure_does_not_break_response() -> None:
    response = Response()
    chat_service = RAGChatService(
        retrieval_service=FakeRetrievalService(results=[]),
        generation_service=FakeGenerationService(),
    )

    result = chat(
        chat_request=ChatRequest(question="What is the leave policy?"),
        http_request=_build_http_request("req-best-effort"),
        response=response,
        current_user=_build_user(),
        chat_service=chat_service,
        permission_service=FakePermissionService(),
        trace_service=FakeTraceService(fail=True),
    )

    assert result.answer == "Remote work answer."
    assert response.headers[REQUEST_ID_HEADER] == "req-best-effort"


def test_chat_api_saves_error_trace_for_empty_question() -> None:
    trace_service = FakeTraceService()
    response = Response()
    chat_service = RAGChatService(
        retrieval_service=FakeRetrievalService(results=[]),
        generation_service=FakeGenerationService(),
    )

    with pytest.raises(HTTPException) as exc:
        chat(
            chat_request=ChatRequest(question=" "),
            http_request=_build_http_request("req-empty"),
            response=response,
            current_user=_build_user(),
            chat_service=chat_service,
            permission_service=FakePermissionService(),
            trace_service=trace_service,
        )

    assert exc.value.status_code == 400
    assert exc.value.headers[REQUEST_ID_HEADER] == "req-empty"
    saved_trace = trace_service.saved_traces[0]
    assert saved_trace.status == "ERROR"
    assert saved_trace.error_message == "Question cannot be empty."
    assert saved_trace.total_time_ms is not None


def test_trace_context_records_service_timings() -> None:
    trace_context = RAGTraceContext(
        request_id="req-timing",
        user_id=1,
        question="What is the remote work policy?",
        retrieval_mode="vector",
        model_name="fake-llm",
    )
    trace_token = set_current_trace_context(trace_context)
    try:
        retrieval_service = RetrievalService(
            embedding_service=FakeEmbeddingService(),
            vector_store=FakeVectorStore(results=[_build_result()]),
            config=RetrievalConfig(mode="vector", reranker_enabled=False),
        )
        retrieval_results = retrieval_service.retrieve(
            query="What is the remote work policy?",
            top_k=1,
        )
        assert trace_context.retrieval_time_ms is not None
        assert trace_context.retrieval_time_ms >= 0
        assert trace_context.reranker_time_ms is None

        reranker_service = CrossEncoderRerankerService(
            config=RerankerConfig(model_name="fake-model", batch_size=2)
        )
        reranker_service._model = FakeCrossEncoder()
        reranker_service.rerank(
            query="What is the remote work policy?",
            candidates=retrieval_results,
            top_k=1,
        )
        assert trace_context.reranker_time_ms is not None
        assert trace_context.reranker_time_ms >= 0

        generation_service = RAGGenerationService(
            ollama_service=FakeOllamaGenerationService(),
            prompt_builder=RAGPromptBuilder(),
        )
        generation_service.generate_answer(
            question="What is the remote work policy?",
            retrieval_results=retrieval_results,
        )
        assert trace_context.generation_time_ms is not None
        assert trace_context.generation_time_ms >= 0
    finally:
        reset_current_trace_context(trace_token)

    assert get_current_trace_context() is None
