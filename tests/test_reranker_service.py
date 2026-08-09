from app.schemas.documents import ChunkMetadata, RetrievalResult
import pytest

from app.services.reranker_service import (
    CrossEncoderRerankerService,
    RerankerConfig,
    RerankerServiceError,
)


class FakeCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[dict] = []

    def predict(self, pairs, batch_size, show_progress_bar):
        self.calls.append(
            {
                "pairs": pairs,
                "batch_size": batch_size,
                "show_progress_bar": show_progress_bar,
            }
        )
        return self.scores


def _build_result(filename: str, text: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        text=text,
        filename=filename,
        page_number=None,
        score=score,
        vector_score=score,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=filename,
            file_type="markdown",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=len(text),
        ),
    )


def test_reranker_sorts_candidates_and_preserves_debug_scores() -> None:
    fake_model = FakeCrossEncoder(scores=[0.2, 0.9])
    reranker = CrossEncoderRerankerService(
        config=RerankerConfig(model_name="fake-model", batch_size=8)
    )
    reranker._model = fake_model

    results = reranker.rerank(
        query="remote work",
        candidates=[
            _build_result("hr_policy.md", "performance reviews", score=0.95),
            _build_result("company_policy.md", "remote work policy", score=0.65),
        ],
        top_k=2,
    )

    assert [result.filename for result in results] == [
        "company_policy.md",
        "hr_policy.md",
    ]
    assert results[0].score == 0.9
    assert results[0].reranker_score == 0.9
    assert results[0].vector_score == 0.65
    assert fake_model.calls == [
        {
            "pairs": [
                ("remote work", "performance reviews"),
                ("remote work", "remote work policy"),
            ],
            "batch_size": 8,
            "show_progress_bar": False,
        }
    ]


def test_reranker_returns_empty_for_no_candidates() -> None:
    reranker = CrossEncoderRerankerService()

    assert reranker.rerank(query="remote work", candidates=[], top_k=3) == []


def test_reranker_raises_when_model_score_count_does_not_match_candidates() -> None:
    fake_model = FakeCrossEncoder(scores=[0.2])
    reranker = CrossEncoderRerankerService(
        config=RerankerConfig(model_name="fake-model", batch_size=8)
    )
    reranker._model = fake_model

    with pytest.raises(RerankerServiceError):
        reranker.rerank(
            query="remote work",
            candidates=[
                _build_result("hr_policy.md", "performance reviews", score=0.95),
                _build_result("company_policy.md", "remote work policy", score=0.65),
            ],
            top_k=2,
        )
