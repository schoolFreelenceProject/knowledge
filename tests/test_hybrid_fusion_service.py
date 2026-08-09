from app.schemas.documents import ChunkMetadata, RetrievalResult
from app.services.hybrid_fusion_service import (
    HybridFusionConfig,
    HybridFusionService,
)


def _build_result(
    filename: str,
    score: float,
    chunk_index: int,
) -> RetrievalResult:
    return RetrievalResult(
        text=f"{filename} chunk {chunk_index}",
        filename=filename,
        page_number=None,
        score=score,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=filename,
            file_type="markdown",
            page_number=None,
            chunk_index=chunk_index,
            start_char=0,
            end_char=20,
        ),
    )


def test_rrf_fusion_promotes_results_found_by_both_retrievers() -> None:
    fusion_service = HybridFusionService(
        config=HybridFusionConfig(strategy="rrf", vector_weight=0.5, bm25_weight=0.5)
    )
    shared_result = _build_result("company_policy.md", score=0.8, chunk_index=1)

    results = fusion_service.fuse(
        vector_results=[
            _build_result("hr_policy.md", score=0.95, chunk_index=1),
            shared_result,
        ],
        bm25_results=[
            shared_result,
            _build_result("expense_policy.md", score=2.0, chunk_index=1),
        ],
        top_k=3,
    )

    assert results[0].filename == "company_policy.md"
    assert len(results) == 3


def test_weighted_score_fusion_normalizes_scores() -> None:
    fusion_service = HybridFusionService(
        config=HybridFusionConfig(
            strategy="weighted_score",
            vector_weight=0.7,
            bm25_weight=0.3,
        )
    )

    results = fusion_service.fuse(
        vector_results=[
            _build_result("company_policy.md", score=0.9, chunk_index=1),
            _build_result("hr_policy.md", score=0.1, chunk_index=1),
        ],
        bm25_results=[
            _build_result("expense_policy.md", score=10.0, chunk_index=1),
        ],
        top_k=2,
    )

    assert [result.filename for result in results] == [
        "company_policy.md",
        "expense_policy.md",
    ]
    assert results[0].score == 0.7
    assert results[1].score == 0.3
