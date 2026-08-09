from datetime import datetime, timezone

from fastapi import Response
from starlette.requests import Request

from app.api.chat import REQUEST_ID_HEADER
from app.api.chat import chat
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.documents import GeneratedAnswer
from app.services.auth_service import AuthenticatedUser
from app.services.chat_service import RAGChatService


class FakeRetrievalService:
    def __init__(self) -> None:
        self.allowed_point_ids: list[str] | None = None

    def retrieve(self, query, top_k, allowed_point_ids=None):
        self.allowed_point_ids = allowed_point_ids
        return []


class FakeGenerationService:
    def generate_answer(self, question, retrieval_results):
        return GeneratedAnswer(answer="No context.", sources=[])


class FakePermissionService:
    def list_accessible_qdrant_point_ids(self, user_id: int) -> list[str]:
        return ["point-1", "point-2"]


class FakeChatService:
    def __init__(self) -> None:
        self.allowed_point_ids: list[str] | None = None

    def answer_question(self, question, top_k, allowed_point_ids=None):
        self.allowed_point_ids = allowed_point_ids
        return ChatResponse(answer="Answer", sources=[])


class FakeTraceService:
    def save_trace(self, trace_context):
        return None


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_http_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [(REQUEST_ID_HEADER.lower().encode(), b"req-1")],
        }
    )


def test_chat_service_passes_generic_allowed_point_filter() -> None:
    retrieval_service = FakeRetrievalService()
    chat_service = RAGChatService(
        retrieval_service=retrieval_service,
        generation_service=FakeGenerationService(),
    )

    chat_service.answer_question(
        question="What is the password policy?",
        top_k=5,
        allowed_point_ids=["point-1"],
    )

    assert retrieval_service.allowed_point_ids == ["point-1"]


def test_chat_api_uses_permission_service_for_allowed_points() -> None:
    chat_service = FakeChatService()

    chat(
        chat_request=ChatRequest(question="What is the password policy?"),
        http_request=_build_http_request(),
        response=Response(),
        current_user=_build_user(),
        chat_service=chat_service,
        permission_service=FakePermissionService(),
        trace_service=FakeTraceService(),
    )

    assert chat_service.allowed_point_ids == ["point-1", "point-2"]
