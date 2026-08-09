import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.documents import RetrievalResult
from app.services.vector_store import QdrantVectorStore, RetrievalDocument


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class BM25Config:
    k1: float = 1.5
    b: float = 0.75


@dataclass(frozen=True)
class BM25IndexedDocument:
    document: RetrievalDocument
    token_counts: Counter[str]
    token_count: int


class BM25RetrievalService:
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        config: BM25Config | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.config = config or BM25Config()
        self._indexed_documents: list[BM25IndexedDocument] | None = None
        self._document_frequency: dict[str, int] = {}
        self._average_document_length = 0.0

    def rebuild_index(self) -> None:
        documents = self.vector_store.list_retrieval_documents()
        self._indexed_documents = [
            _build_indexed_document(document)
            for document in documents
        ]
        self._document_frequency = _build_document_frequency(
            self._indexed_documents
        )
        self._average_document_length = _average_document_length(
            self._indexed_documents
        )

    def retrieve(
        self,
        query: str,
        top_k: int,
        allowed_point_ids: Iterable[str] | None = None,
        content_types: Iterable[str] | None = None,
        languages: Iterable[str] | None = None,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be greater than 0.")

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        indexed_documents = self._get_indexed_documents()
        allowed_point_id_set = _normalize_allowed_point_ids(allowed_point_ids)
        if allowed_point_id_set == set():
            return []
        content_type_set = _normalize_filter_values(content_types)
        if content_type_set == set():
            return []
        language_set = _normalize_filter_values(languages)
        if language_set == set():
            return []

        scored_documents = [
            (
                _score_document(
                    query_tokens=query_tokens,
                    indexed_document=indexed_document,
                    total_documents=len(indexed_documents),
                    document_frequency=self._document_frequency,
                    average_document_length=self._average_document_length,
                    config=self.config,
                ),
                indexed_document.document,
            )
            for indexed_document in indexed_documents
            if _point_is_allowed(
                point_id=indexed_document.document.point_id,
                allowed_point_ids=allowed_point_id_set,
            )
            and _metadata_matches(
                document=indexed_document.document,
                content_types=content_type_set,
                languages=language_set,
            )
        ]
        ranked_documents = [
            (score, document)
            for score, document in scored_documents
            if score > 0
        ]
        ranked_documents.sort(
            key=lambda item: (
                item[0],
                item[1].metadata.filename,
                -item[1].metadata.chunk_index,
            ),
            reverse=True,
        )

        return [
            _to_retrieval_result(document=document, score=score)
            for score, document in ranked_documents[:top_k]
        ]

    def _get_indexed_documents(self) -> list[BM25IndexedDocument]:
        if self._indexed_documents is None:
            self.rebuild_index()

        return self._indexed_documents or []


def _build_indexed_document(document: RetrievalDocument) -> BM25IndexedDocument:
    tokens = _tokenize(document.text)
    return BM25IndexedDocument(
        document=document,
        token_counts=Counter(tokens),
        token_count=len(tokens),
    )


def _build_document_frequency(
    indexed_documents: list[BM25IndexedDocument],
) -> dict[str, int]:
    document_frequency: dict[str, int] = {}
    for indexed_document in indexed_documents:
        for token in indexed_document.token_counts:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    return document_frequency


def _average_document_length(
    indexed_documents: list[BM25IndexedDocument],
) -> float:
    if not indexed_documents:
        return 0.0

    return sum(document.token_count for document in indexed_documents) / len(
        indexed_documents
    )


def _score_document(
    query_tokens: list[str],
    indexed_document: BM25IndexedDocument,
    total_documents: int,
    document_frequency: dict[str, int],
    average_document_length: float,
    config: BM25Config,
) -> float:
    if total_documents == 0 or indexed_document.token_count == 0:
        return 0.0

    score = 0.0
    for token in query_tokens:
        term_frequency = indexed_document.token_counts.get(token, 0)
        if term_frequency == 0:
            continue

        df = document_frequency.get(token, 0)
        idf = math.log(1 + (total_documents - df + 0.5) / (df + 0.5))
        denominator = term_frequency + config.k1 * (
            1
            - config.b
            + config.b
            * indexed_document.token_count
            / max(average_document_length, 1.0)
        )
        score += idf * (
            term_frequency
            * (config.k1 + 1)
            / denominator
        )

    return score


def _to_retrieval_result(
    document: RetrievalDocument,
    score: float,
) -> RetrievalResult:
    metadata = document.metadata
    return RetrievalResult(
        text=document.text,
        filename=metadata.filename,
        page_number=metadata.page_number,
        score=score,
        content_type=metadata.content_type,
        bm25_score=score,
        metadata=metadata,
    )


def _tokenize(text: str) -> list[str]:
    return [
        token.casefold()
        for token in TOKEN_PATTERN.findall(text)
    ]


def _normalize_allowed_point_ids(
    allowed_point_ids: Iterable[str] | None,
) -> set[str] | None:
    if allowed_point_ids is None:
        return None

    return {str(point_id) for point_id in allowed_point_ids}


def _normalize_filter_values(
    values: Iterable[str] | None,
) -> set[str] | None:
    if values is None:
        return None

    return {
        normalized_value
        for normalized_value in (
            str(value).strip().casefold()
            for value in values
        )
        if normalized_value
    }


def _point_is_allowed(
    point_id: str,
    allowed_point_ids: set[str] | None,
) -> bool:
    if allowed_point_ids is None:
        return True

    return point_id in allowed_point_ids


def _metadata_matches(
    document: RetrievalDocument,
    content_types: set[str] | None,
    languages: set[str] | None,
) -> bool:
    metadata = document.metadata
    if content_types is not None and metadata.content_type.casefold() not in content_types:
        return False

    if languages is not None:
        language = metadata.language.casefold() if metadata.language else ""
        if language not in languages:
            return False

    return True
