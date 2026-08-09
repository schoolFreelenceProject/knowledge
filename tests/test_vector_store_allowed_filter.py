from types import SimpleNamespace

from app.services.vector_store import QdrantVectorStore


class FakeQdrantClient:
    def __init__(self) -> None:
        self.query_filter = None
        self.collection_checked = False

    def collection_exists(self, collection_name):
        self.collection_checked = True
        return True

    def get_collection(self, collection_name):
        return SimpleNamespace(
            points_count=0,
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(
                        size=2,
                        distance="Cosine",
                    )
                )
            ),
        )

    def query_points(
        self,
        collection_name,
        query,
        query_filter,
        limit,
        with_payload,
        with_vectors,
    ):
        self.query_filter = query_filter
        return SimpleNamespace(points=[])


def test_search_similar_applies_generic_allowed_point_filter() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )

    results = vector_store.search_similar(
        query_vector=[1.0, 0.0],
        top_k=5,
        allowed_point_ids=["point-1", "point-1", "point-2"],
    )

    assert results == []
    assert client.query_filter is not None
    assert client.query_filter.must[0].has_id == ["point-1", "point-2"]


def test_search_similar_returns_empty_when_allowed_point_filter_is_empty() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )

    results = vector_store.search_similar(
        query_vector=[1.0, 0.0],
        top_k=5,
        allowed_point_ids=[],
    )

    assert results == []
    assert client.collection_checked is False


def test_search_similar_can_filter_by_content_type() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )

    results = vector_store.search_similar(
        query_vector=[1.0, 0.0],
        top_k=5,
        allowed_point_ids=["code-point-1"],
        content_types=["code"],
    )

    assert results == []
    assert client.query_filter is not None
    assert client.query_filter.must[0].has_id == ["code-point-1"]
    assert client.query_filter.must[1].key == "content_type"
    assert client.query_filter.must[1].match.value == "code"


def test_search_similar_can_filter_by_language() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )

    results = vector_store.search_similar(
        query_vector=[1.0, 0.0],
        top_k=5,
        allowed_point_ids=["code-point-1"],
        content_types=["code"],
        languages=["Python"],
    )

    assert results == []
    assert client.query_filter is not None
    assert client.query_filter.must[0].has_id == ["code-point-1"]
    assert client.query_filter.must[1].key == "content_type"
    assert client.query_filter.must[1].match.value == "code"
    assert client.query_filter.must[2].key == "language"
    assert client.query_filter.must[2].match.value == "python"
