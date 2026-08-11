import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.schemas.documents import ChunkMetadata, EmbeddedChunk, RetrievalResult


class VectorStoreError(RuntimeError):
    """Raised when vector storage cannot be read or written."""


@dataclass(frozen=True)
class StoredVectorBatch:
    collection_name: str
    stored_count: int
    vector_size: int | None
    point_ids: list[str]


@dataclass(frozen=True)
class VectorStoreStatus:
    collection_name: str
    exists: bool
    points_count: int
    vector_size: int | None
    distance: str | None


VECTOR_UPSERT_BATCH_SIZE = 128


@dataclass(frozen=True)
class RetrievalDocument:
    point_id: str
    text: str
    metadata: ChunkMetadata


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        collection_name: str,
        client: Any | None = None,
    ) -> None:
        self.url = url
        self.collection_name = collection_name
        self._client = client

    @property
    def client(self):
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise VectorStoreError(
                "Qdrant storage requires qdrant-client. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        self._client = QdrantClient(url=self.url)
        return self._client

    def store_embeddings(
        self,
        embedded_chunks: Iterable[EmbeddedChunk],
    ) -> StoredVectorBatch:
        chunk_list = list(embedded_chunks)
        if not chunk_list:
            return StoredVectorBatch(
                collection_name=self.collection_name,
                stored_count=0,
                vector_size=None,
                point_ids=[],
            )

        vector_size = _validate_vectors(chunk_list)
        self.ensure_collection(vector_size=vector_size)
        point_ids = [build_point_id(chunk) for chunk in chunk_list]
        points = [
            _build_point(chunk, point_id=point_id)
            for chunk, point_id in zip(chunk_list, point_ids, strict=True)
        ]

        stored_point_ids: list[str] = []
        try:
            for point_batch in _batched(points, VECTOR_UPSERT_BATCH_SIZE):
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=point_batch,
                    wait=True,
                )
                stored_point_ids.extend(str(point.id) for point in point_batch)
        except Exception as exc:
            self._delete_points_best_effort(stored_point_ids)
            raise VectorStoreError(
                f"Failed to upsert vectors into Qdrant collection "
                f"'{self.collection_name}': {exc}"
            ) from exc

        return StoredVectorBatch(
            collection_name=self.collection_name,
            stored_count=len(points),
            vector_size=vector_size,
            point_ids=point_ids,
        )

    def delete_points(self, point_ids: Iterable[str]) -> None:
        point_id_list = list(point_ids)
        if not point_id_list:
            return

        try:
            from qdrant_client import models

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=point_id_list),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete points from Qdrant collection "
                f"'{self.collection_name}': {exc}"
            ) from exc

    def _delete_points_best_effort(self, point_ids: Iterable[str]) -> None:
        try:
            self.delete_points(point_ids)
        except VectorStoreError:
            pass

    def ensure_collection(self, vector_size: int) -> None:
        if vector_size < 1:
            raise VectorStoreError("Vector size must be greater than 0.")

        if not self.collection_exists():
            self._create_collection(vector_size=vector_size)
            return

        status = self.get_status()
        if status.vector_size != vector_size:
            raise VectorStoreError(
                f"Qdrant collection '{self.collection_name}' has vector size "
                f"{status.vector_size}, but embeddings have vector size {vector_size}. "
                "Use the same embedding model or create a new collection."
            )

    def collection_exists(self) -> bool:
        try:
            return bool(self.client.collection_exists(self.collection_name))
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to check Qdrant collection '{self.collection_name}': {exc}"
            ) from exc

    def get_status(self) -> VectorStoreStatus:
        if not self.collection_exists():
            return VectorStoreStatus(
                collection_name=self.collection_name,
                exists=False,
                points_count=0,
                vector_size=None,
                distance=None,
            )

        try:
            collection_info = self.client.get_collection(self.collection_name)
            vector_size, distance = _extract_vector_config(collection_info)
            points_count = int(collection_info.points_count or 0)
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to inspect Qdrant collection '{self.collection_name}': {exc}"
            ) from exc

        return VectorStoreStatus(
            collection_name=self.collection_name,
            exists=True,
            points_count=points_count,
            vector_size=vector_size,
            distance=distance,
        )

    def list_payload_samples(self, limit: int) -> list[dict[str, Any]]:
        if limit < 1 or not self.collection_exists():
            return []

        try:
            records, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to inspect Qdrant payload samples from "
                f"'{self.collection_name}': {exc}"
            ) from exc

        return [dict(record.payload or {}) for record in records]

    def list_retrieval_documents(
        self,
        allowed_point_ids: Iterable[str] | None = None,
        content_types: Iterable[str] | None = None,
        languages: Iterable[str] | None = None,
        batch_size: int = 256,
    ) -> list[RetrievalDocument]:
        if batch_size < 1:
            raise VectorStoreError("batch_size must be greater than 0.")

        allowed_point_id_list = _normalize_allowed_point_ids(allowed_point_ids)
        if allowed_point_id_list == []:
            return []
        content_type_list = _normalize_content_types(content_types)
        if content_type_list == []:
            return []
        language_list = _normalize_languages(languages)
        if language_list == []:
            return []

        if not self.collection_exists():
            raise VectorStoreError(
                f"Qdrant collection '{self.collection_name}' does not exist. "
                "Store vectors before running retrieval."
            )

        documents: list[RetrievalDocument] = []
        next_page_offset = None
        try:
            while True:
                records, next_page_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=_build_filter(
                        point_ids=allowed_point_id_list,
                        content_types=content_type_list,
                        languages=language_list,
                    ),
                    limit=batch_size,
                    offset=next_page_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                documents.extend(
                    _build_retrieval_document(record)
                    for record in records
                )
                if next_page_offset is None:
                    break
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to scroll retrieval documents from Qdrant collection "
                f"'{self.collection_name}': {exc}"
            ) from exc

        return documents

    def search_similar(
        self,
        query_vector: list[float],
        top_k: int,
        allowed_point_ids: Iterable[str] | None = None,
        content_types: Iterable[str] | None = None,
        languages: Iterable[str] | None = None,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise VectorStoreError("top_k must be greater than 0.")

        if not query_vector:
            raise VectorStoreError("Query vector cannot be empty.")

        allowed_point_id_list = _normalize_allowed_point_ids(allowed_point_ids)
        if allowed_point_id_list == []:
            return []
        content_type_list = _normalize_content_types(content_types)
        if content_type_list == []:
            return []
        language_list = _normalize_languages(languages)
        if language_list == []:
            return []

        if not self.collection_exists():
            raise VectorStoreError(
                f"Qdrant collection '{self.collection_name}' does not exist. "
                "Store vectors before running retrieval."
            )

        status = self.get_status()
        if status.vector_size != len(query_vector):
            raise VectorStoreError(
                f"Qdrant collection '{self.collection_name}' has vector size "
                f"{status.vector_size}, but query vector has size {len(query_vector)}. "
                "Use the same embedding model used for indexing."
            )

        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=_build_filter(
                    point_ids=allowed_point_id_list,
                    content_types=content_type_list,
                    languages=language_list,
                ),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to search Qdrant collection '{self.collection_name}': {exc}"
            ) from exc

        return [_build_retrieval_result(point) for point in response.points]

    def _create_collection(self, vector_size: int) -> None:
        try:
            from qdrant_client import models

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to create Qdrant collection '{self.collection_name}': {exc}"
            ) from exc


def _validate_vectors(embedded_chunks: list[EmbeddedChunk]) -> int:
    vector_size = len(embedded_chunks[0].vector)
    if vector_size < 1:
        raise VectorStoreError("Embedding vector cannot be empty.")

    for index, chunk in enumerate(embedded_chunks, start=1):
        if len(chunk.vector) != vector_size:
            raise VectorStoreError(
                f"Embedding vector at item {index} has size {len(chunk.vector)}, "
                f"expected {vector_size}."
            )

    return vector_size


def _batched(items: list[Any], batch_size: int):
    for start_index in range(0, len(items), batch_size):
        yield items[start_index : start_index + batch_size]


def _build_point(embedded_chunk: EmbeddedChunk, point_id: str):
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise VectorStoreError(
            "Qdrant storage requires qdrant-client. "
            "Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    return models.PointStruct(
        id=point_id,
        vector=embedded_chunk.vector,
        payload=_build_payload(embedded_chunk),
    )


def _normalize_allowed_point_ids(
    allowed_point_ids: Iterable[str] | None,
) -> list[str] | None:
    if allowed_point_ids is None:
        return None

    return list(dict.fromkeys(str(point_id) for point_id in allowed_point_ids))


def _normalize_content_types(
    content_types: Iterable[str] | None,
) -> list[str] | None:
    if content_types is None:
        return None

    return list(
        dict.fromkeys(
            content_type
            for content_type in (str(value).strip() for value in content_types)
            if content_type
        )
    )


def _normalize_languages(
    languages: Iterable[str] | None,
) -> list[str] | None:
    if languages is None:
        return None

    return list(
        dict.fromkeys(
            language.casefold()
            for language in (str(value).strip() for value in languages)
            if language
        )
    )


def _build_allowed_point_filter(point_ids: list[str] | None):
    return _build_filter(point_ids=point_ids, content_types=None, languages=None)


def _build_filter(
    point_ids: list[str] | None,
    content_types: list[str] | None,
    languages: list[str] | None,
):
    if point_ids is None and content_types is None and languages is None:
        return None

    try:
        from qdrant_client import models
    except ImportError as exc:
        raise VectorStoreError(
            "Qdrant filtering requires qdrant-client. "
            "Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    conditions = []
    if point_ids is not None:
        conditions.append(models.HasIdCondition(has_id=point_ids))

    if content_types is not None:
        if len(content_types) == 1:
            conditions.append(
                models.FieldCondition(
                    key="content_type",
                    match=models.MatchValue(value=content_types[0]),
                )
            )
        else:
            conditions.append(
                models.FieldCondition(
                    key="content_type",
                    match=models.MatchAny(any=content_types),
                )
            )

    if languages is not None:
        if len(languages) == 1:
            conditions.append(
                models.FieldCondition(
                    key="language",
                    match=models.MatchValue(value=languages[0]),
                )
            )
        else:
            conditions.append(
                models.FieldCondition(
                    key="language",
                    match=models.MatchAny(any=languages),
                )
            )

    return models.Filter(must=conditions)


def build_point_id(embedded_chunk: EmbeddedChunk) -> str:
    metadata = embedded_chunk.metadata
    text_hash = hashlib.sha256(embedded_chunk.text.encode("utf-8")).hexdigest()
    key = json.dumps(
        {
            "source_path": metadata.source_path,
            "page_number": metadata.page_number,
            "chunk_index": metadata.chunk_index,
            "start_char": metadata.start_char,
            "end_char": metadata.end_char,
            "text_hash": text_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _build_payload(embedded_chunk: EmbeddedChunk) -> dict[str, Any]:
    metadata = embedded_chunk.metadata.model_dump(mode="json")
    return {
        **metadata,
        "text": embedded_chunk.text,
    }


def _build_retrieval_result(scored_point: Any) -> RetrievalResult:
    payload = dict(scored_point.payload or {})

    try:
        metadata = ChunkMetadata(
            filename=payload["filename"],
            source_path=payload["source_path"],
            file_type=payload["file_type"],
            content_type=payload.get("content_type", "document"),
            page_number=payload.get("page_number"),
            chunk_index=payload["chunk_index"],
            start_char=payload["start_char"],
            end_char=payload["end_char"],
            repo_name=payload.get("repo_name"),
            repo_url=payload.get("repo_url"),
            branch=payload.get("branch"),
            commit_sha=payload.get("commit_sha"),
            source_type=payload.get("source_type"),
            language=payload.get("language"),
            symbol_name=payload.get("symbol_name"),
            symbol_kind=payload.get("symbol_kind"),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
            repository_file_path=payload.get("repository_file_path"),
        )
        text = str(payload["text"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VectorStoreError(
            "Qdrant search result payload is missing required document metadata."
        ) from exc

    return RetrievalResult(
        point_id=str(scored_point.id),
        text=text,
        filename=metadata.filename,
        page_number=metadata.page_number,
        score=float(scored_point.score),
        content_type=metadata.content_type,
        vector_score=float(scored_point.score),
        metadata=metadata,
    )


def _build_retrieval_document(record: Any) -> RetrievalDocument:
    payload = dict(record.payload or {})

    try:
        metadata = ChunkMetadata(
            filename=payload["filename"],
            source_path=payload["source_path"],
            file_type=payload["file_type"],
            content_type=payload.get("content_type", "document"),
            page_number=payload.get("page_number"),
            chunk_index=payload["chunk_index"],
            start_char=payload["start_char"],
            end_char=payload["end_char"],
            repo_name=payload.get("repo_name"),
            repo_url=payload.get("repo_url"),
            branch=payload.get("branch"),
            commit_sha=payload.get("commit_sha"),
            source_type=payload.get("source_type"),
            language=payload.get("language"),
            symbol_name=payload.get("symbol_name"),
            symbol_kind=payload.get("symbol_kind"),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
            repository_file_path=payload.get("repository_file_path"),
        )
        text = str(payload["text"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VectorStoreError(
            "Qdrant retrieval document payload is missing required metadata."
        ) from exc

    return RetrievalDocument(
        point_id=str(record.id),
        text=text,
        metadata=metadata,
    )


def _extract_vector_config(collection_info: Any) -> tuple[int | None, str | None]:
    vectors_config = collection_info.config.params.vectors

    if isinstance(vectors_config, dict):
        if not vectors_config:
            return None, None
        first_vector_config = next(iter(vectors_config.values()))
        return _extract_single_vector_config(first_vector_config)

    return _extract_single_vector_config(vectors_config)


def _extract_single_vector_config(vector_config: Any) -> tuple[int | None, str | None]:
    vector_size = getattr(vector_config, "size", None)
    distance = getattr(vector_config, "distance", None)
    if distance is not None:
        distance = getattr(distance, "value", distance)
        distance = str(distance)

    return vector_size, distance
