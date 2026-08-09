from app.schemas.documents import AnswerSource, GeneratedAnswer, RetrievalResult
from app.services.prompt_builder import RAGPromptBuilder
from app.services.trace_context import trace_timer


class GenerationServiceError(RuntimeError):
    """Raised when answer generation cannot be completed."""


class OllamaGenerationService:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str) -> str:
        try:
            import ollama
        except ImportError as exc:
            raise GenerationServiceError(
                "Answer generation requires ollama. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        try:
            client = ollama.Client(host=self.base_url)
            response = client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
        except Exception as exc:
            raise GenerationServiceError(
                f"Failed to call Ollama model '{self.model}' at "
                f"'{self.base_url}': {exc}"
            ) from exc

        answer = _extract_ollama_answer(response)
        if not answer:
            raise GenerationServiceError("Ollama returned an empty answer.")

        return answer


class RAGGenerationService:
    def __init__(
        self,
        ollama_service: OllamaGenerationService,
        prompt_builder: RAGPromptBuilder,
    ) -> None:
        self.ollama_service = ollama_service
        self.prompt_builder = prompt_builder

    def generate_answer(
        self,
        question: str,
        retrieval_results: list[RetrievalResult],
    ) -> GeneratedAnswer:
        normalized_question = question.strip()
        if not normalized_question:
            raise GenerationServiceError("Question cannot be empty.")

        with trace_timer("generation_time_ms"):
            prompt = self.prompt_builder.build_prompt(
                question=normalized_question,
                retrieval_results=retrieval_results,
            )
            answer = self.ollama_service.generate(prompt)

        return GeneratedAnswer(
            answer=answer,
            sources=_build_answer_sources(retrieval_results),
        )


def _build_answer_sources(
    retrieval_results: list[RetrievalResult],
) -> list[AnswerSource]:
    return [
        AnswerSource(
            filename=result.filename,
            page_number=result.page_number,
            score=result.score,
        )
        for result in retrieval_results
    ]


def _extract_ollama_answer(response) -> str:
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if content is not None:
                return str(content).strip()

        content = getattr(message, "content", None)
        if content is not None:
            return str(content).strip()

        return str(response.get("response") or "").strip()

    message = getattr(response, "message", None)
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()

    content = getattr(message, "content", None)
    if content is not None:
        return str(content).strip()

    response_text = getattr(response, "response", None)
    if response_text is not None:
        return str(response_text).strip()

    return ""
