import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.bm25_retrieval_service import BM25Config, BM25RetrievalService
from app.services.embedding_service import (
    EmbeddingServiceError,
    SentenceTransformersEmbeddingService,
)
from app.services.evaluation_service import (
    EvaluationDatasetError,
    EvaluationService,
    EvaluationServiceError,
    load_evaluation_dataset,
    save_evaluation_report,
)
from app.services.feedback_evaluation_service import (
    FeedbackEvaluationService,
    FeedbackEvaluationServiceError,
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


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "evaluation" / "rag_eval.json"


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Evaluate retrieval and answer quality for the RAG pipeline."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to the evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Default retrieval top K when a case does not override it.",
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
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the full JSON evaluation report.",
    )
    parser.add_argument(
        "--max-answer-chars",
        type=int,
        default=500,
        help="Maximum answer characters shown in preview output.",
    )
    parser.add_argument(
        "--include-feedback-metrics",
        action="store_true",
        help="Include offline human feedback metrics in the evaluation summary.",
    )
    parser.add_argument(
        "--feedback-user-id",
        type=int,
        help="Optional feedback metrics filter by user id.",
    )
    parser.add_argument(
        "--feedback-retrieval-mode",
        choices=("vector", "bm25", "hybrid"),
        help="Optional feedback metrics filter by retrieval mode.",
    )
    parser.add_argument(
        "--feedback-status",
        choices=("PROCESSING", "SUCCESS", "ERROR"),
        help="Optional feedback metrics filter by trace status.",
    )
    parser.add_argument(
        "--feedback-created-from",
        type=_parse_datetime,
        help="Optional feedback metrics lower datetime bound.",
    )
    parser.add_argument(
        "--feedback-created-to",
        type=_parse_datetime,
        help="Optional feedback metrics upper datetime bound.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        dataset = load_evaluation_dataset(args.dataset)

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
        generation_service = RAGGenerationService(
            ollama_service=OllamaGenerationService(
                base_url=args.ollama_base_url,
                model=args.ollama_model,
            ),
            prompt_builder=RAGPromptBuilder(),
        )
        evaluation_service = EvaluationService(
            retrieval_service=retrieval_service,
            generation_service=generation_service,
        )
        feedback_metrics = None
        if args.include_feedback_metrics:
            feedback_metrics = FeedbackEvaluationService(
                session_factory=get_session_factory(),
                init_database=init_db,
            ).calculate_feedback_metrics(
                user_id=args.feedback_user_id,
                retrieval_mode=args.feedback_retrieval_mode,
                status=args.feedback_status,
                created_from=args.feedback_created_from,
                created_to=args.feedback_created_to,
            )
        report = evaluation_service.evaluate_cases(
            cases=dataset.cases,
            default_top_k=args.top_k,
            metadata={
                "dataset": str(args.dataset),
                "dataset_name": dataset.name,
                "embedding_model_name": args.embedding_model_name,
                "qdrant_url": args.qdrant_url,
                "collection_name": args.collection_name,
                "ollama_base_url": args.ollama_base_url,
                "ollama_model": args.ollama_model,
                "retrieval_mode": args.retrieval_mode,
                "fusion_strategy": args.fusion_strategy,
                "hybrid_vector_weight": args.vector_weight,
                "hybrid_bm25_weight": args.bm25_weight,
                "hybrid_candidate_multiplier": args.hybrid_candidate_multiplier,
                "bm25_k1": args.bm25_k1,
                "bm25_b": args.bm25_b,
                "reranker_enabled": args.reranker_enabled,
                "reranker_model_name": args.reranker_model_name,
                "reranker_candidate_size": args.reranker_candidate_size,
                "reranker_batch_size": args.reranker_batch_size,
                "feedback_metrics_enabled": args.include_feedback_metrics,
                "feedback_user_id": args.feedback_user_id,
                "feedback_retrieval_mode": args.feedback_retrieval_mode,
                "feedback_status": args.feedback_status,
                "feedback_created_from": args.feedback_created_from,
                "feedback_created_to": args.feedback_created_to,
            },
            feedback_metrics=feedback_metrics,
        )

        if args.output is not None:
            save_evaluation_report(report=report, output_path=args.output)
    except (
        EmbeddingServiceError,
        EvaluationDatasetError,
        EvaluationServiceError,
        FeedbackEvaluationServiceError,
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
                report.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    _print_preview(report, max_answer_chars=args.max_answer_chars)
    if args.output is not None:
        print()
        print(f"Report written to: {args.output}")

    return 0


def _print_preview(report, max_answer_chars: int) -> None:
    summary = report.summary
    print("RAG Evaluation Report")
    print(f"Total cases: {summary.total_cases}")
    print(f"Retrieval hit rate: {_format_optional(summary.retrieval_hit_rate)}")
    print(
        "Average expected source rank: "
        f"{_format_optional(summary.average_expected_source_rank)}"
    )
    print(
        "Average best source score: "
        f"{_format_optional(summary.average_best_source_score)}"
    )
    print(
        "Answer keyword coverage rate: "
        f"{_format_optional(summary.answer_keyword_coverage_rate)}"
    )
    if summary.feedback_count is not None:
        print(f"Feedback count: {summary.feedback_count}")
        print(
            "Average user rating: "
            f"{_format_optional(summary.average_user_rating)}"
        )
        print(
            "Bad answer rate: "
            f"{_format_optional(summary.bad_answer_rate)}"
        )
        print(
            "Good answer rate: "
            f"{_format_optional(summary.good_answer_rate)}"
        )

    for case_result in report.cases:
        retrieval_score = case_result.retrieval_score
        print()
        print(f"[{case_result.id}] {case_result.question}")
        print(
            "Retrieval: "
            f"hit={retrieval_score.hit}, "
            f"rank={retrieval_score.expected_source_rank}, "
            f"best_score={_format_optional(retrieval_score.best_expected_source_score)}"
        )
        print(
            "Answer keyword coverage: "
            f"{_format_optional(case_result.answer_score.coverage)}"
        )
        if case_result.retrieved_documents:
            print("Retrieved:")
            for document in case_result.retrieved_documents:
                page_label = (
                    f"page {document.page_number}"
                    if document.page_number is not None
                    else "document"
                )
                print(
                    f"  [{document.rank}] {document.filename} "
                    f"({page_label}, chunk {document.chunk_index}, "
                    f"score {document.score:.6f})"
                )
        else:
            print("Retrieved: none")

        print("Answer:")
        print(_preview_text(case_result.answer_output, max_chars=max_answer_chars))


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"

    return f"{value:.4f}"


def _preview_text(text: str, max_chars: int) -> str:
    if not text:
        return "<empty answer>"

    if max_chars < 1:
        return ""

    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars].rstrip()}\n..."


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime value: {value}"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
