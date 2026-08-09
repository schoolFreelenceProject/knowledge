from app.schemas.documents import ChunkMetadata, RetrievalResult
from app.services.retrieval_service import RetrievalConfig, RetrievalService


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts):
        text_list = list(texts)
        self.calls.append(text_list)
        return [[1.0, 0.0] for _text in text_list]


class FakeVectorStore:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def search_similar(self, query_vector, top_k, allowed_point_ids=None):
        self.calls.append(
            {
                "query_vector": query_vector,
                "top_k": top_k,
                "allowed_point_ids": allowed_point_ids,
            }
        )
        return self.results[:top_k]


class FakeBM25RetrievalService:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def retrieve(self, query, top_k, allowed_point_ids=None):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "allowed_point_ids": allowed_point_ids,
            }
        )
        return self.results[:top_k]


class FakeHybridFusionService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fuse(self, vector_results, bm25_results, top_k):
        self.calls.append(
            {
                "vector_results": vector_results,
                "bm25_results": bm25_results,
                "top_k": top_k,
            }
        )
        return (vector_results + bm25_results)[:top_k]


class FakeRerankerService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rerank(self, query, candidates, top_k):
        self.calls.append(
            {
                "query": query,
                "candidates": candidates,
                "top_k": top_k,
            }
        )
        return list(reversed(candidates))[:top_k]


def _build_result(filename: str, score: float, index: int = 1) -> RetrievalResult:
    return RetrievalResult(
        text=filename,
        filename=filename,
        page_number=None,
        score=score,
        vector_score=score,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=filename,
            file_type="markdown",
            page_number=None,
            chunk_index=index,
            start_char=0,
            end_char=10,
        ),
    )


def test_disabled_reranker_preserves_vector_top_k_behavior() -> None:
    vector_store = FakeVectorStore(
        [
            _build_result("company_policy.md", score=0.9),
            _build_result("hr_policy.md", score=0.8),
        ]
    )
    reranker_service = FakeRerankerService()
    retrieval_service = RetrievalService(
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        reranker_service=reranker_service,
        config=RetrievalConfig(mode="vector", reranker_enabled=False),
    )

    results = retrieval_service.retrieve(query="policy", top_k=1)

    assert [result.filename for result in results] == ["company_policy.md"]
    assert vector_store.calls[0]["top_k"] == 1
    assert reranker_service.calls == []


def test_enabled_reranker_retrieves_candidate_size_then_returns_top_k() -> None:
    vector_store = FakeVectorStore(
        [
            _build_result("company_policy.md", score=0.9),
            _build_result("hr_policy.md", score=0.8),
            _build_result("expense_policy.md", score=0.7),
        ]
    )
    reranker_service = FakeRerankerService()
    retrieval_service = RetrievalService(
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        reranker_service=reranker_service,
        config=RetrievalConfig(
            mode="vector",
            reranker_enabled=True,
            reranker_candidate_size=3,
        ),
    )

    results = retrieval_service.retrieve(
        query="policy",
        top_k=2,
        allowed_point_ids=["point-1"],
    )

    assert [result.filename for result in results] == [
        "expense_policy.md",
        "hr_policy.md",
    ]
    assert vector_store.calls[0]["top_k"] == 3
    assert vector_store.calls[0]["allowed_point_ids"] == ["point-1"]
    assert reranker_service.calls[0]["top_k"] == 2
    assert len(reranker_service.calls[0]["candidates"]) == 3


def test_hybrid_reranker_reranks_fused_candidates() -> None:
    vector_store = FakeVectorStore(
        [_build_result("company_policy.md", score=0.9)]
    )
    bm25_service = FakeBM25RetrievalService(
        [_build_result("expense_policy.md", score=2.0)]
    )
    fusion_service = FakeHybridFusionService()
    reranker_service = FakeRerankerService()
    retrieval_service = RetrievalService(
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        bm25_retrieval_service=bm25_service,
        hybrid_fusion_service=fusion_service,
        reranker_service=reranker_service,
        config=RetrievalConfig(
            mode="hybrid",
            hybrid_candidate_multiplier=4,
            reranker_enabled=True,
            reranker_candidate_size=3,
        ),
    )

    results = retrieval_service.retrieve(
        query="policy",
        top_k=2,
        allowed_point_ids=["point-1", "point-2"],
    )

    assert [result.filename for result in results] == [
        "expense_policy.md",
        "company_policy.md",
    ]
    assert vector_store.calls[0]["top_k"] == 12
    assert bm25_service.calls[0]["top_k"] == 12
    assert fusion_service.calls[0]["top_k"] == 3
    assert reranker_service.calls[0]["top_k"] == 2
    assert reranker_service.calls[0]["candidates"] == fusion_service.calls[0][
        "vector_results"
    ] + fusion_service.calls[0]["bm25_results"]
