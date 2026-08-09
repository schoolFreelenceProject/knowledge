from dataclasses import dataclass

from app.schemas.documents import RetrievalResult


@dataclass(frozen=True)
class HybridFusionConfig:
    strategy: str = "rrf"
    vector_weight: float = 0.6
    bm25_weight: float = 0.4
    rrf_k: int = 60


class HybridFusionService:
    def __init__(
        self,
        config: HybridFusionConfig | None = None,
    ) -> None:
        self.config = config or HybridFusionConfig()

    def fuse(
        self,
        vector_results: list[RetrievalResult],
        bm25_results: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be greater than 0.")

        if self.config.strategy == "rrf":
            return _fuse_with_rrf(
                vector_results=vector_results,
                bm25_results=bm25_results,
                top_k=top_k,
                config=self.config,
            )

        if self.config.strategy == "weighted_score":
            return _fuse_with_weighted_scores(
                vector_results=vector_results,
                bm25_results=bm25_results,
                top_k=top_k,
                config=self.config,
            )

        raise ValueError(f"Unsupported hybrid fusion strategy: {self.config.strategy}")


def _fuse_with_rrf(
    vector_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    top_k: int,
    config: HybridFusionConfig,
) -> list[RetrievalResult]:
    fused_items: dict[tuple, dict] = {}
    _add_rank_scores(
        fused_items=fused_items,
        results=vector_results,
        weight=config.vector_weight,
        rrf_k=config.rrf_k,
        source_priority=0,
    )
    _add_rank_scores(
        fused_items=fused_items,
        results=bm25_results,
        weight=config.bm25_weight,
        rrf_k=config.rrf_k,
        source_priority=1,
    )
    return _rank_fused_items(fused_items=fused_items, top_k=top_k)


def _fuse_with_weighted_scores(
    vector_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    top_k: int,
    config: HybridFusionConfig,
) -> list[RetrievalResult]:
    fused_items: dict[tuple, dict] = {}
    _add_normalized_scores(
        fused_items=fused_items,
        results=vector_results,
        weight=config.vector_weight,
        source_priority=0,
    )
    _add_normalized_scores(
        fused_items=fused_items,
        results=bm25_results,
        weight=config.bm25_weight,
        source_priority=1,
    )
    return _rank_fused_items(fused_items=fused_items, top_k=top_k)


def _add_rank_scores(
    fused_items: dict[tuple, dict],
    results: list[RetrievalResult],
    weight: float,
    rrf_k: int,
    source_priority: int,
) -> None:
    for rank, result in enumerate(results, start=1):
        score = weight * (1 / (rrf_k + rank))
        _add_fused_score(
            fused_items=fused_items,
            result=result,
            score=score,
            rank=rank,
            source_priority=source_priority,
        )


def _add_normalized_scores(
    fused_items: dict[tuple, dict],
    results: list[RetrievalResult],
    weight: float,
    source_priority: int,
) -> None:
    normalized_scores = _normalize_scores(results)
    for rank, result in enumerate(results, start=1):
        _add_fused_score(
            fused_items=fused_items,
            result=result,
            score=weight * normalized_scores[rank - 1],
            rank=rank,
            source_priority=source_priority,
        )


def _add_fused_score(
    fused_items: dict[tuple, dict],
    result: RetrievalResult,
    score: float,
    rank: int,
    source_priority: int,
) -> None:
    key = _result_key(result)
    item = fused_items.setdefault(
        key,
        {
            "result": result,
            "score": 0.0,
            "best_rank": rank,
            "source_priority": source_priority,
            "vector_score": None,
            "bm25_score": None,
        },
    )
    item["score"] += score
    item["best_rank"] = min(item["best_rank"], rank)
    if source_priority == 0:
        item["vector_score"] = _max_optional(
            item["vector_score"],
            result.vector_score if result.vector_score is not None else result.score,
        )
    elif source_priority == 1:
        item["bm25_score"] = _max_optional(
            item["bm25_score"],
            result.bm25_score if result.bm25_score is not None else result.score,
        )

    if source_priority < item["source_priority"]:
        item["result"] = result
        item["source_priority"] = source_priority


def _rank_fused_items(
    fused_items: dict[tuple, dict],
    top_k: int,
) -> list[RetrievalResult]:
    ranked_items = sorted(
        fused_items.values(),
        key=lambda item: (
            item["score"],
            -item["best_rank"],
            item["result"].filename,
            -item["result"].metadata.chunk_index,
        ),
        reverse=True,
    )
    return [
        item["result"].model_copy(
            update={
                "score": item["score"],
                "vector_score": item["vector_score"],
                "bm25_score": item["bm25_score"],
                "fusion_score": item["score"],
            }
        )
        for item in ranked_items[:top_k]
    ]


def _normalize_scores(results: list[RetrievalResult]) -> list[float]:
    if not results:
        return []

    scores = [result.score for result in results]
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [1.0 for _result in results]

    return [
        (score - min_score) / (max_score - min_score)
        for score in scores
    ]


def _result_key(result: RetrievalResult) -> tuple:
    metadata = result.metadata
    return (
        metadata.source_path,
        metadata.page_number,
        metadata.chunk_index,
        metadata.start_char,
        metadata.end_char,
    )


def _max_optional(current_value: float | None, next_value: float) -> float:
    if current_value is None:
        return next_value

    return max(current_value, next_value)
