from app.schemas.chat import ChatResponse
from app.services.generation_service import (
    InternalGenerationUnavailableError,
    RAGGenerationService,
)
from app.services.retrieval_service import RetrievalService
from app.services.trace_context import get_current_trace_context


class RAGChatService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        generation_service: RAGGenerationService | None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service

    def answer_question(
        self,
        question: str,
        top_k: int,
        allowed_point_ids: list[str] | None = None,
    ) -> ChatResponse:
        if self.generation_service is None:
            raise InternalGenerationUnavailableError()

        retrieval_results = self.retrieval_service.retrieve(
            query=question,
            top_k=top_k,
            allowed_point_ids=allowed_point_ids,
        )
        trace_context = get_current_trace_context()
        if trace_context is not None:
            trace_context.record_retrieved_sources(retrieval_results)

        generated_answer = self.generation_service.generate_answer(
            question=question,
            retrieval_results=retrieval_results,
        )

        return ChatResponse.model_validate(generated_answer.model_dump(mode="json"))
