from types import SimpleNamespace

import pytest

from app.schemas.documents import ChunkMetadata, EmbeddedChunk
from app.services.vector_store import (
    QdrantVectorStore,
    VECTOR_UPSERT_BATCH_SIZE,
    VectorStoreError,
)


class FakeQdrantClient:
    def __init__(self) -> None:
        self.query_filter = None
        self.collection_checked = False
        self.upsert_batches = []
        self.deleted_point_ids = []
        self.fail_on_upsert_call = None

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

    def upsert(self, collection_name, points, wait):
        self.upsert_batches.append(points)
        if self.fail_on_upsert_call == len(self.upsert_batches):
            raise RuntimeError("simulated Qdrant request failure")

    def delete(self, collection_name, points_selector, wait):
        self.deleted_point_ids.extend(points_selector.points)


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


def test_store_embeddings_batches_qdrant_upserts() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )
    chunks = _embedded_chunks(VECTOR_UPSERT_BATCH_SIZE + 1)

    stored_batch = vector_store.store_embeddings(chunks)

    assert stored_batch.stored_count == VECTOR_UPSERT_BATCH_SIZE + 1
    assert len(client.upsert_batches) == 2
    assert [len(batch) for batch in client.upsert_batches] == [
        VECTOR_UPSERT_BATCH_SIZE,
        1,
    ]
    assert client.deleted_point_ids == []


def test_store_embeddings_cleans_successful_batches_when_later_upsert_fails() -> None:
    client = FakeQdrantClient()
    client.fail_on_upsert_call = 2
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )
    chunks = _embedded_chunks(VECTOR_UPSERT_BATCH_SIZE + 1)

    with pytest.raises(VectorStoreError):
        vector_store.store_embeddings(chunks)

    assert len(client.upsert_batches) == 2
    assert len(client.deleted_point_ids) == VECTOR_UPSERT_BATCH_SIZE


def test_store_embeddings_includes_office_metadata_in_payload() -> None:
    client = FakeQdrantClient()
    vector_store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="company_documents",
        client=client,
    )
    chunk = EmbeddedChunk(
        vector=[1.0, 0.0],
        text="Workbook: 勤務表.xlsx\nSheet: 勤怠",
        metadata=ChunkMetadata(
            filename="勤務表.xlsx",
            source_path="勤務表.xlsx",
            file_type="xlsx",
            page_number=None,
            workbook="勤務表.xlsx",
            sheet_name="勤怠",
            cell_range="A1:B2",
            row_start=1,
            row_end=2,
            chunk_index=1,
            start_char=0,
            end_char=30,
        ),
    )

    vector_store.store_embeddings([chunk])

    payload = client.upsert_batches[0][0].payload
    assert payload["file_type"] == "xlsx"
    assert payload["workbook"] == "勤務表.xlsx"
    assert payload["sheet_name"] == "勤怠"
    assert payload["cell_range"] == "A1:B2"
    assert payload["text"].startswith("Workbook")


def _embedded_chunks(count: int) -> list[EmbeddedChunk]:
    return [
        EmbeddedChunk(
            vector=[1.0, 0.0],
            text=f"chunk {index}",
            metadata=ChunkMetadata(
                filename=f"file-{index}.php",
                source_path=f"repo/file-{index}.php",
                file_type="code",
                content_type="code",
                chunk_index=index,
                start_char=0,
                end_char=10,
                repo_name="repo",
                repo_url="file:///repo",
                branch="main",
                commit_sha="a" * 40,
                language="php",
                repository_file_path=f"file-{index}.php",
            ),
        )
        for index in range(1, count + 1)
    ]
