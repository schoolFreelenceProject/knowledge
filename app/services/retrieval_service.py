from dataclasses import dataclass

from app.schemas.documents import RetrievalResult
from app.services.bm25_retrieval_service import BM25RetrievalService
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.hybrid_fusion_service import HybridFusionService
from app.services.reranker_service import (
    CrossEncoderRerankerService,
    RerankerServiceError,
)
from app.services.text_normalization import normalize_query_text
from app.services.trace_context import trace_timer
from app.services.vector_store import QdrantVectorStore


class RetrievalServiceError(RuntimeError):
    """Raised when retrieval input is invalid."""


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str = "vector"
    hybrid_candidate_multiplier: int = 4
    reranker_enabled: bool = False
    reranker_candidate_size: int = 20


class RetrievalService:
    def __init__(
        self,
        embedding_service: SentenceTransformersEmbeddingService,
        vector_store: QdrantVectorStore,
        bm25_retrieval_service: BM25RetrievalService | None = None,
        hybrid_fusion_service: HybridFusionService | None = None,
        reranker_service: CrossEncoderRerankerService | None = None,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.bm25_retrieval_service = bm25_retrieval_service
        self.hybrid_fusion_service = hybrid_fusion_service
        self.reranker_service = reranker_service
        self.config = config or RetrievalConfig()

    def retrieve(
        self,
        query: str,
        top_k: int,
        allowed_point_ids: list[str] | None = None,
        content_types: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> list[RetrievalResult]:
        normalized_query = normalize_query_text(query)
        if not normalized_query:
            raise RetrievalServiceError("Query cannot be empty.")

        if top_k < 1:
            raise RetrievalServiceError("top_k must be greater than 0.")

        retrieval_top_k = top_k
        if self.config.reranker_enabled:
            if self.config.reranker_candidate_size < 1:
                raise RetrievalServiceError(
                    "reranker_candidate_size must be greater than 0."
                )
            retrieval_top_k = max(top_k, self.config.reranker_candidate_size)

        with trace_timer("retrieval_time_ms"):
            retrieval_results = self._retrieve_candidates(
                query=normalized_query,
                top_k=retrieval_top_k,
                allowed_point_ids=allowed_point_ids,
                content_types=content_types,
                languages=languages,
            )

        if not self.config.reranker_enabled:
            return retrieval_results

        if self.reranker_service is None:
            raise RetrievalServiceError(
                "Reranking requires a reranker service."
            )

        try:
            return self.reranker_service.rerank(
                query=normalized_query,
                candidates=retrieval_results,
                top_k=top_k,
            )
        except RerankerServiceError as exc:
            raise RetrievalServiceError(str(exc)) from exc

    def _retrieve_candidates(
        self,
        query: str,
        top_k: int,
        allowed_point_ids: list[str] | None,
        content_types: list[str] | None,
        languages: list[str] | None,
    ) -> list[RetrievalResult]:
        if self.config.mode == "vector":
            return self._retrieve_vector(
                query=query,
                top_k=top_k,
                allowed_point_ids=allowed_point_ids,
                content_types=content_types,
                languages=languages,
            )

        if self.config.mode == "bm25":
            return self._retrieve_bm25(
                query=query,
                top_k=top_k,
                allowed_point_ids=allowed_point_ids,
                content_types=content_types,
                languages=languages,
            )

        if self.config.mode == "hybrid":
            if self.config.hybrid_candidate_multiplier < 1:
                raise RetrievalServiceError(
                    "hybrid_candidate_multiplier must be greater than 0."
                )

            candidate_top_k = top_k * self.config.hybrid_candidate_multiplier
            vector_results = self._retrieve_vector(
                query=query,
                top_k=candidate_top_k,
                allowed_point_ids=allowed_point_ids,
                content_types=content_types,
                languages=languages,
            )
            bm25_results = self._retrieve_bm25(
                query=query,
                top_k=candidate_top_k,
                allowed_point_ids=allowed_point_ids,
                content_types=content_types,
                languages=languages,
            )
            if self.hybrid_fusion_service is None:
                raise RetrievalServiceError(
                    "Hybrid retrieval requires a hybrid fusion service."
                )

            return self.hybrid_fusion_service.fuse(
                vector_results=vector_results,
                bm25_results=bm25_results,
                top_k=top_k,
            )

        raise RetrievalServiceError(
            f"Unsupported retrieval mode: {self.config.mode}"
        )

    def _retrieve_vector(
        self,
        query: str,
        top_k: int,
        allowed_point_ids: list[str] | None,
        content_types: list[str] | None,
        languages: list[str] | None,
    ) -> list[RetrievalResult]:
        query_vectors = self.embedding_service.embed_texts([query])
        if not query_vectors:
            return []

        search_kwargs = {
            "query_vector": query_vectors[0],
            "top_k": top_k,
            "allowed_point_ids": allowed_point_ids,
        }
        if content_types is not None:
            search_kwargs["content_types"] = content_types
        if languages is not None:
            search_kwargs["languages"] = languages

        return self.vector_store.search_similar(**search_kwargs)

    def _retrieve_bm25(
        self,
        query: str,
        top_k: int,
        allowed_point_ids: list[str] | None,
        content_types: list[str] | None,
        languages: list[str] | None,
    ) -> list[RetrievalResult]:
        if self.bm25_retrieval_service is None:
            raise RetrievalServiceError(
                "BM25 retrieval requires a BM25 retrieval service."
            )

        retrieve_kwargs = {
            "query": query,
            "top_k": top_k,
            "allowed_point_ids": allowed_point_ids,
        }
        if content_types is not None:
            retrieve_kwargs["content_types"] = content_types
        if languages is not None:
            retrieve_kwargs["languages"] = languages

        return self.bm25_retrieval_service.retrieve(**retrieve_kwargs)
