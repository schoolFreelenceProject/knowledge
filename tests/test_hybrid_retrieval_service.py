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


def _build_result(filename: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        text=filename,
        filename=filename,
        page_number=None,
        score=score,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=filename,
            file_type="markdown",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=10,
        ),
    )


def test_vector_mode_preserves_existing_vector_retrieval_behavior() -> None:
    embedding_service = FakeEmbeddingService()
    vector_store = FakeVectorStore(
        [_build_result("company_policy.md", score=0.9)]
    )
    bm25_service = FakeBM25RetrievalService([])
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        bm25_retrieval_service=bm25_service,
        config=RetrievalConfig(mode="vector"),
    )

    results = retrieval_service.retrieve(
        query=" remote work ",
        top_k=3,
        allowed_point_ids=["point-1"],
    )

    assert [result.filename for result in results] == ["company_policy.md"]
    assert embedding_service.calls == [["remote work"]]
    assert vector_store.calls == [
        {
            "query_vector": [1.0, 0.0],
            "top_k": 3,
            "allowed_point_ids": ["point-1"],
        }
    ]
    assert bm25_service.calls == []


def test_vector_mode_normalizes_japanese_query_before_embedding() -> None:
    embedding_service = FakeEmbeddingService()
    vector_store = FakeVectorStore([])
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        config=RetrievalConfig(mode="vector"),
    )

    retrieval_service.retrieve(
        query=" ＶＰＮ　接続 ",
        top_k=3,
        allowed_point_ids=["point-1"],
    )

    assert embedding_service.calls == [["VPN 接続"]]


def test_bm25_mode_uses_bm25_without_vector_embedding() -> None:
    embedding_service = FakeEmbeddingService()
    bm25_service = FakeBM25RetrievalService(
        [_build_result("expense_policy.md", score=2.0)]
    )
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=FakeVectorStore([]),
        bm25_retrieval_service=bm25_service,
        config=RetrievalConfig(mode="bm25"),
    )

    results = retrieval_service.retrieve(
        query="receipts",
        top_k=2,
        allowed_point_ids=["point-2"],
    )

    assert [result.filename for result in results] == ["expense_policy.md"]
    assert embedding_service.calls == []
    assert bm25_service.calls == [
        {
            "query": "receipts",
            "top_k": 2,
            "allowed_point_ids": ["point-2"],
        }
    ]


def test_hybrid_mode_retrieves_candidates_and_fuses_results() -> None:
    embedding_service = FakeEmbeddingService()
    vector_store = FakeVectorStore(
        [_build_result("company_policy.md", score=0.9)]
    )
    bm25_service = FakeBM25RetrievalService(
        [_build_result("expense_policy.md", score=2.0)]
    )
    fusion_service = FakeHybridFusionService()
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        bm25_retrieval_service=bm25_service,
        hybrid_fusion_service=fusion_service,
        config=RetrievalConfig(mode="hybrid", hybrid_candidate_multiplier=4),
    )

    results = retrieval_service.retrieve(
        query="policy",
        top_k=2,
        allowed_point_ids=["point-1", "point-2"],
    )

    assert [result.filename for result in results] == [
        "company_policy.md",
        "expense_policy.md",
    ]
    assert vector_store.calls[0]["top_k"] == 8
    assert vector_store.calls[0]["allowed_point_ids"] == ["point-1", "point-2"]
    assert bm25_service.calls[0]["top_k"] == 8
    assert bm25_service.calls[0]["allowed_point_ids"] == ["point-1", "point-2"]
    assert fusion_service.calls[0]["top_k"] == 2
