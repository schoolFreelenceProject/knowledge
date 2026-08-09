from dataclasses import dataclass

from app.schemas.documents import RetrievalResult
from app.services.trace_context import trace_timer


class RerankerServiceError(RuntimeError):
    """Raised when reranking cannot be completed."""


@dataclass(frozen=True)
class RerankerConfig:
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 16


class CrossEncoderRerankerService:
    def __init__(self, config: RerankerConfig | None = None) -> None:
        self.config = config or RerankerConfig()
        self._model = None

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise RerankerServiceError("top_k must be greater than 0.")

        if self.config.batch_size < 1:
            raise RerankerServiceError("batch_size must be greater than 0.")

        normalized_query = query.strip()
        if not normalized_query or not candidates:
            return []

        with trace_timer("reranker_time_ms"):
            model = self._load_model()
            pairs = [
                (normalized_query, candidate.text)
                for candidate in candidates
            ]

            try:
                raw_scores = model.predict(
                    pairs,
                    batch_size=self.config.batch_size,
                    show_progress_bar=False,
                )
            except Exception as exc:
                raise RerankerServiceError(
                    f"Failed to rerank candidates with model "
                    f"'{self.config.model_name}': {exc}"
                ) from exc

            scores = [float(score) for score in raw_scores]
            if len(scores) != len(candidates):
                raise RerankerServiceError(
                    "Reranker model returned an unexpected number of scores."
                )

            scored_candidates = [
                (
                    score,
                    index,
                    candidate.model_copy(
                        update={
                            "score": score,
                            "reranker_score": score,
                        }
                    ),
                )
                for index, (candidate, score) in enumerate(zip(candidates, scores))
            ]
            scored_candidates.sort(
                key=lambda item: (item[0], -item[1]),
                reverse=True,
            )

            return [
                candidate
                for _score, _index, candidate in scored_candidates[:top_k]
            ]

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RerankerServiceError(
                "Reranking requires sentence-transformers. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        try:
            self._model = CrossEncoder(self.config.model_name)
        except Exception as exc:
            raise RerankerServiceError(
                f"Failed to load reranker model '{self.config.model_name}': {exc}"
            ) from exc

        return self._model
