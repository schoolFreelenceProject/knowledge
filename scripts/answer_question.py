import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.bm25_retrieval_service import BM25Config, BM25RetrievalService
from app.services.embedding_service import (
    EmbeddingServiceError,
    SentenceTransformersEmbeddingService,
)
from app.services.generation_service import (
    GenerationServiceError,
    OllamaGenerationService,
    RAGGenerationService,
)
from app.services.hybrid_fusion_service import (
    HybridFusionConfig,
    HybridFusionService,
)
from app.services.prompt_builder import RAGPromptBuilder
from app.services.reranker_service import CrossEncoderRerankerService, RerankerConfig
from app.services.retrieval_service import (
    RetrievalConfig,
    RetrievalService,
    RetrievalServiceError,
)
from app.services.vector_store import QdrantVectorStore, VectorStoreError


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Generate a simple RAG answer from stored Qdrant vectors."
    )
    parser.add_argument("question", help="User question to answer.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of relevant chunks to retrieve.",
    )
    parser.add_argument(
        "--embedding-model-name",
        default=settings.embedding_model_name,
        help="sentence-transformers model name for query embedding.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=settings.qdrant_url,
        help="Qdrant HTTP URL.",
    )
    parser.add_argument(
        "--collection-name",
        default=settings.qdrant_collection_name,
        help="Qdrant collection name.",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=settings.ollama_base_url,
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--ollama-model",
        default=settings.ollama_model,
        help="Ollama model name.",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("vector", "bm25", "hybrid"),
        default=settings.retrieval_mode,
        help="Retrieval mode.",
    )
    parser.add_argument(
        "--fusion-strategy",
        choices=("rrf", "weighted_score"),
        default=settings.hybrid_fusion_strategy,
        help="Hybrid fusion strategy.",
    )
    parser.add_argument(
        "--vector-weight",
        type=float,
        default=settings.hybrid_vector_weight,
        help="Vector result weight for hybrid fusion.",
    )
    parser.add_argument(
        "--bm25-weight",
        type=float,
        default=settings.hybrid_bm25_weight,
        help="BM25 result weight for hybrid fusion.",
    )
    parser.add_argument(
        "--hybrid-candidate-multiplier",
        type=int,
        default=settings.hybrid_candidate_multiplier,
        help="Candidate multiplier before hybrid fusion.",
    )
    parser.add_argument(
        "--bm25-k1",
        type=float,
        default=settings.bm25_k1,
        help="BM25 k1 parameter.",
    )
    parser.add_argument(
        "--bm25-b",
        type=float,
        default=settings.bm25_b,
        help="BM25 b parameter.",
    )
    parser.add_argument(
        "--reranker-enabled",
        action="store_true",
        default=settings.reranker_enabled,
        help="Enable cross-encoder reranking after retrieval.",
    )
    parser.add_argument(
        "--reranker-model-name",
        default=settings.reranker_model_name,
        help="Cross-encoder reranker model name.",
    )
    parser.add_argument(
        "--reranker-candidate-size",
        type=int,
        default=settings.reranker_candidate_size,
        help="Candidate count to retrieve before reranking.",
    )
    parser.add_argument(
        "--reranker-batch-size",
        type=int,
        default=settings.reranker_batch_size,
        help="Reranker model batch size.",
    )
    parser.add_argument(
        "--format",
        choices=("preview", "json"),
        default="preview",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        embedding_service = SentenceTransformersEmbeddingService(
            model_name=args.embedding_model_name,
        )
        vector_store = QdrantVectorStore(
            url=args.qdrant_url,
            collection_name=args.collection_name,
        )
        retrieval_service = RetrievalService(
            embedding_service=embedding_service,
            vector_store=vector_store,
            bm25_retrieval_service=BM25RetrievalService(
                vector_store=vector_store,
                config=BM25Config(k1=args.bm25_k1, b=args.bm25_b),
            ),
            hybrid_fusion_service=HybridFusionService(
                config=HybridFusionConfig(
                    strategy=args.fusion_strategy,
                    vector_weight=args.vector_weight,
                    bm25_weight=args.bm25_weight,
                ),
            ),
            reranker_service=CrossEncoderRerankerService(
                config=RerankerConfig(
                    model_name=args.reranker_model_name,
                    batch_size=args.reranker_batch_size,
                ),
            ),
            config=RetrievalConfig(
                mode=args.retrieval_mode,
                hybrid_candidate_multiplier=args.hybrid_candidate_multiplier,
                reranker_enabled=args.reranker_enabled,
                reranker_candidate_size=args.reranker_candidate_size,
            ),
        )
        retrieval_results = retrieval_service.retrieve(
            query=args.question,
            top_k=args.top_k,
        )

        generation_service = RAGGenerationService(
            ollama_service=OllamaGenerationService(
                base_url=args.ollama_base_url,
                model=args.ollama_model,
            ),
            prompt_builder=RAGPromptBuilder(),
        )
        generated_answer = generation_service.generate_answer(
            question=args.question,
            retrieval_results=retrieval_results,
        )
    except (
        EmbeddingServiceError,
        GenerationServiceError,
        RetrievalServiceError,
        ValueError,
        VectorStoreError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(
            json.dumps(
                generated_answer.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Question: {args.question}")
    print(f"Retrieved chunks: {len(retrieval_results)}")
    print(f"Retrieval mode: {args.retrieval_mode}")
    print(f"Reranker enabled: {args.reranker_enabled}")
    print(f"Ollama model: {args.ollama_model}")
    print()
    print("Answer:")
    print(generated_answer.answer)

    if not generated_answer.sources:
        print()
        print("Sources: none")
        return 0

    print()
    print("Sources:")
    for index, source in enumerate(generated_answer.sources, start=1):
        page_label = (
            f"page {source.page_number}"
            if source.page_number is not None
            else "document"
        )
        print(
            f"[{index}] {source.filename} "
            f"({page_label}, score {source.score:.6f})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
