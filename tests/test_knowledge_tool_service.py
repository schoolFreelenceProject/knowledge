from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.schemas.chat import ChatResponse
from app.schemas.document_management import (
    DocumentChunkDetail,
    DocumentDetail,
)
from app.schemas.documents import ChunkMetadata, RetrievalResult
from app.services.knowledge_tool_service import KnowledgeToolService
from app.services.generation_service import InternalGenerationUnavailableError
from app.services.permission_service import DocumentAccessDeniedError
from app.services.retrieval_service import RetrievalConfig
from app.services.trace_context import RAGTraceContext


class FakePermissionService:
    def __init__(
        self,
        order: list[str] | None = None,
        denied_document_ids: set[int] | None = None,
    ) -> None:
        self.order = order
        self.denied_document_ids = denied_document_ids or set()
        self.document_access_checks: list[tuple[int, int]] = []

    def list_accessible_qdrant_point_ids(self, user_id: int) -> list[str]:
        return [f"point-for-user-{user_id}"]

    def ensure_user_can_access_document(self, user_id: int, document_id: int) -> None:
        if self.order is not None:
            self.order.append("permission")
        self.document_access_checks.append((user_id, document_id))
        if document_id in self.denied_document_ids:
            raise DocumentAccessDeniedError(
                f"User {user_id} cannot access document {document_id}."
            )


class FakeRetrievalService:
    config = RetrievalConfig(mode="hybrid")

    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def retrieve(
        self,
        query,
        top_k,
        allowed_point_ids=None,
        content_types=None,
        languages=None,
    ):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "allowed_point_ids": allowed_point_ids,
                "content_types": content_types,
                "languages": languages,
            }
        )
        return self.results[:top_k]


class FakeGenerationService:
    class FakeOllamaService:
        model = "fake-llm"

    ollama_service = FakeOllamaService()


class FakeChatService:
    def __init__(self) -> None:
        self.retrieval_service = FakeRetrievalService(results=[])
        self.generation_service = FakeGenerationService()
        self.calls: list[dict] = []

    def answer_question(self, question, top_k, allowed_point_ids=None):
        self.calls.append(
            {
                "question": question,
                "top_k": top_k,
                "allowed_point_ids": allowed_point_ids,
            }
        )
        return ChatResponse(answer="Answer", sources=[])


class FakeUnavailableChatService:
    def __init__(self) -> None:
        self.retrieval_service = FakeRetrievalService(results=[])
        self.generation_service = None

    def answer_question(self, question, top_k, allowed_point_ids=None):
        raise InternalGenerationUnavailableError()


class FakeDocumentManagementService:
    def __init__(self, order: list[str] | None = None) -> None:
        self.order = order

    def get_document(self, document_id: int) -> DocumentDetail:
        if self.order is not None:
            self.order.append("document")
        timestamp = datetime.now(timezone.utc)
        return DocumentDetail(
            id=document_id,
            filename="policy.md",
            file_type="markdown",
            storage_path="policy.md",
            file_hash="a" * 64,
            status="INDEXED",
            created_at=timestamp,
            updated_at=timestamp,
            chunk_count=1,
            chunks=[
                DocumentChunkDetail(
                    id=3,
                    qdrant_point_id="point-1",
                    chunk_index=1,
                    page_number=None,
                    start_char=0,
                    end_char=10,
                    created_at=timestamp,
                )
            ],
        )


class FakeTraceService:
    def __init__(self) -> None:
        self.saved_traces: list[RAGTraceContext] = []

    def save_trace(self, trace_context: RAGTraceContext):
        self.saved_traces.append(deepcopy(trace_context))


def _build_document_result() -> RetrievalResult:
    return RetrievalResult(
        text="Remote work policy text.",
        filename="company_policy.md",
        page_number=None,
        score=0.91,
        vector_score=0.82,
        metadata=ChunkMetadata(
            filename="company_policy.md",
            source_path="company_policy.md",
            file_type="markdown",
            page_number=None,
            section_heading="Remote Work Policy",
            heading_path="Remote Work Policy",
            chunk_index=1,
            start_char=0,
            end_char=24,
        ),
    )


def _build_code_result() -> RetrievalResult:
    return RetrievalResult(
        text="def hello():\n    return 'hi'\n",
        filename="app.py",
        page_number=None,
        score=0.88,
        metadata=ChunkMetadata(
            filename="app.py",
            source_path="repo@abc/app.py",
            file_type="code",
            content_type="code",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=28,
            repo_name="repo",
            repo_url="https://github.com/company/repo.git",
            branch="main",
            commit_sha="abc",
            language="python",
            symbol_name="hello",
            symbol_kind="function",
            start_line=1,
            end_line=2,
            repository_file_path="app.py",
        ),
    )


def _build_service(
    retrieval_results: list[RetrievalResult] | None = None,
    order: list[str] | None = None,
    denied_document_ids: set[int] | None = None,
    chat_service=None,
):
    trace_service = FakeTraceService()
    return (
        KnowledgeToolService(
            chat_service=chat_service or FakeChatService(),
            retrieval_service=FakeRetrievalService(retrieval_results or []),
            permission_service=FakePermissionService(
                order=order,
                denied_document_ids=denied_document_ids,
            ),
            document_management_service=FakeDocumentManagementService(order=order),
            trace_service=trace_service,
        ),
        trace_service,
    )


def test_search_knowledge_uses_acl_points_and_content_type_filter() -> None:
    service, _trace_service = _build_service([_build_document_result()])

    response = service.search_knowledge(
        user_id=7,
        query="remote work",
        top_k=5,
        content_type="document",
        request_id="req-search",
    )

    assert response.request_id == "req-search"
    assert response.results[0].source_type == "document"
    assert response.results[0].document_metadata.section_heading == (
        "Remote Work Policy"
    )
    assert service.retrieval_service.calls == [
        {
            "query": "remote work",
            "top_k": 5,
            "allowed_point_ids": ["point-for-user-7"],
            "content_types": ["document"],
            "languages": None,
        }
    ]


def test_search_knowledge_returns_empty_results_for_empty_retrieval() -> None:
    service, _trace_service = _build_service()

    response = service.search_knowledge(
        user_id=7,
        query="no matching documents",
        top_k=5,
        request_id="req-empty",
    )

    assert response.request_id == "req-empty"
    assert response.results == []
    assert service.retrieval_service.calls[0]["allowed_point_ids"] == [
        "point-for-user-7"
    ]


def test_search_code_uses_code_only_and_language_filter() -> None:
    service, _trace_service = _build_service([_build_code_result()])

    response = service.search_code(
        user_id=9,
        query="hello",
        top_k=3,
        language="Python",
        request_id="req-code",
    )

    assert response.results[0].code_metadata.language == "python"
    assert response.results[0].code_metadata.start_line == 1
    assert service.retrieval_service.calls[0]["allowed_point_ids"] == [
        "point-for-user-9"
    ]
    assert service.retrieval_service.calls[0]["content_types"] == ["code"]
    assert service.retrieval_service.calls[0]["languages"] == ["python"]


def test_get_document_checks_acl_before_reading_document() -> None:
    order: list[str] = []
    service, _trace_service = _build_service(order=order)

    response = service.get_document(
        user_id=11,
        document_id=4,
        request_id="req-document",
    )

    assert response.id == 4
    assert order == ["permission", "document"]
    assert service.permission_service.document_access_checks == [(11, 4)]


def test_get_document_denies_acl_access_before_reading_document() -> None:
    order: list[str] = []
    service, _trace_service = _build_service(
        order=order,
        denied_document_ids={4},
    )

    with pytest.raises(DocumentAccessDeniedError):
        service.get_document(
            user_id=11,
            document_id=4,
            request_id="req-denied",
        )

    assert order == ["permission"]
    assert service.permission_service.document_access_checks == [(11, 4)]


def test_ask_knowledge_reuses_chat_service_and_saves_trace() -> None:
    service, trace_service = _build_service()

    response = service.ask_knowledge(
        user_id=12,
        question="What is the policy?",
        top_k=2,
        request_id="req-ask",
    )

    assert response.answer == "Answer"
    assert service.chat_service.calls == [
        {
            "question": "What is the policy?",
            "top_k": 2,
            "allowed_point_ids": ["point-for-user-12"],
        }
    ]
    assert trace_service.saved_traces[0].request_id == "req-ask"
    assert trace_service.saved_traces[0].user_id == 12
    assert trace_service.saved_traces[0].status == "SUCCESS"


def test_ask_knowledge_returns_explicit_unavailable_response_without_generation() -> None:
    service, trace_service = _build_service(
        chat_service=FakeUnavailableChatService(),
    )

    response = service.ask_knowledge(
        user_id=12,
        question="What is the policy?",
        top_k=2,
        request_id="req-ask-disabled",
    )

    assert response.request_id == "req-ask-disabled"
    assert response.answer.startswith("Internal answer generation is not configured.")
    assert "search_knowledge" in response.answer
    assert response.sources == []
    assert trace_service.saved_traces[0].request_id == "req-ask-disabled"
    assert trace_service.saved_traces[0].status == "ERROR"
    assert trace_service.saved_traces[0].model_name == "none"
