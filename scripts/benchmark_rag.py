import argparse
import json
import resource
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.bm25_retrieval_service import BM25Config, BM25RetrievalService
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.hybrid_fusion_service import HybridFusionConfig, HybridFusionService
from app.services.reranker_service import CrossEncoderRerankerService, RerankerConfig
from app.services.retrieval_service import RetrievalConfig, RetrievalService
from app.services.vector_store import QdrantVectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Knowledge Base ingestion and retrieval workflows."
    )
    parser.add_argument(
        "mode",
        choices=("chat", "document-ingest", "code-ingest", "retrieval"),
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", help="JWT bearer token for API benchmarks.")
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--file", type=Path, help="PDF or Markdown file to upload.")
    parser.add_argument("--repo-url", help="Git repository URL for code-ingest.")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--retrieval-mode",
        choices=("vector", "bm25", "hybrid"),
        default=None,
    )
    parser.add_argument("--reranker-enabled", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.perf_counter()
    try:
        if args.mode == "chat":
            report = _benchmark_chat(args)
        elif args.mode == "document-ingest":
            report = _benchmark_document_ingest(args)
        elif args.mode == "code-ingest":
            report = _benchmark_code_ingest(args)
        else:
            report = _benchmark_retrieval(args)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    report["total_elapsed_ms"] = _elapsed_ms(started_at)
    report["resource_usage"] = _resource_usage()
    payload = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Benchmark report written to: {args.output}")
    else:
        print(payload)

    return 0


def _benchmark_chat(args: argparse.Namespace) -> dict:
    token = _require_token(args)
    questions = args.question or ["What is the company remote work policy?"]
    tasks = [
        (questions[index % len(questions)], args.top_k)
        for index in range(args.requests)
    ]

    latencies: list[float] = []
    errors = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                _post_json,
                url=f"{args.base_url.rstrip('/')}/api/chat",
                token=token,
                payload={"question": question, "top_k": top_k},
            )
            for question, top_k in tasks
        ]
        for future in as_completed(futures):
            latency_ms, error = future.result()
            latencies.append(latency_ms)
            errors += int(error)

    return _latency_report(
        mode="chat",
        requests=len(tasks),
        concurrency=args.concurrency,
        latencies=latencies,
        errors=errors,
    )


def _benchmark_document_ingest(args: argparse.Namespace) -> dict:
    token = _require_token(args)
    if args.file is None or not args.file.is_file():
        raise ValueError("--file must point to a PDF or Markdown document.")

    started_at = time.perf_counter()
    _post_multipart_file(
        url=f"{args.base_url.rstrip('/')}/api/ingest",
        token=token,
        field_name="file",
        file_path=args.file,
    )
    return _latency_report(
        mode="document-ingest",
        requests=1,
        concurrency=1,
        latencies=[_elapsed_ms(started_at)],
        errors=0,
    )


def _benchmark_code_ingest(args: argparse.Namespace) -> dict:
    token = _require_token(args)
    if not args.repo_url:
        raise ValueError("--repo-url is required for code-ingest.")

    started_at = time.perf_counter()
    _post_json(
        url=f"{args.base_url.rstrip('/')}/api/code/ingest",
        token=token,
        payload={"repo_url": args.repo_url, "branch": args.branch},
    )
    return _latency_report(
        mode="code-ingest",
        requests=1,
        concurrency=1,
        latencies=[_elapsed_ms(started_at)],
        errors=0,
    )


def _benchmark_retrieval(args: argparse.Namespace) -> dict:
    settings = get_settings()
    questions = args.question or ["What is the company remote work policy?"]
    retrieval_service = RetrievalService(
        embedding_service=SentenceTransformersEmbeddingService(
            model_name=settings.embedding_model_name,
        ),
        vector_store=QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection_name,
        ),
        bm25_retrieval_service=BM25RetrievalService(
            vector_store=QdrantVectorStore(
                url=settings.qdrant_url,
                collection_name=settings.qdrant_collection_name,
            ),
            config=BM25Config(k1=settings.bm25_k1, b=settings.bm25_b),
        ),
        hybrid_fusion_service=HybridFusionService(
            config=HybridFusionConfig(
                strategy=settings.hybrid_fusion_strategy,
                vector_weight=settings.hybrid_vector_weight,
                bm25_weight=settings.hybrid_bm25_weight,
            ),
        ),
        reranker_service=CrossEncoderRerankerService(
            config=RerankerConfig(
                model_name=settings.reranker_model_name,
                batch_size=settings.reranker_batch_size,
            ),
        ),
        config=RetrievalConfig(
            mode=args.retrieval_mode or settings.retrieval_mode,
            hybrid_candidate_multiplier=settings.hybrid_candidate_multiplier,
            reranker_enabled=args.reranker_enabled,
            reranker_candidate_size=settings.reranker_candidate_size,
        ),
    )

    latencies: list[float] = []
    errors = 0
    for index in range(args.requests):
        question = questions[index % len(questions)]
        started_at = time.perf_counter()
        try:
            retrieval_service.retrieve(question, top_k=args.top_k)
        except Exception:
            errors += 1
        latencies.append(_elapsed_ms(started_at))

    return _latency_report(
        mode="retrieval",
        requests=args.requests,
        concurrency=1,
        latencies=latencies,
        errors=errors,
        retrieval_mode=args.retrieval_mode or settings.retrieval_mode,
        reranker_enabled=args.reranker_enabled,
    )


def _post_json(url: str, token: str, payload: dict) -> tuple[float, bool]:
    started_at = time.perf_counter()
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            response.read()
        return _elapsed_ms(started_at), False
    except Exception:
        return _elapsed_ms(started_at), True


def _post_multipart_file(
    url: str,
    token: str,
    field_name: str,
    file_path: Path,
) -> None:
    boundary = f"----company-rag-{int(time.time() * 1000)}"
    file_content = file_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        response.read()


def _latency_report(
    mode: str,
    requests: int,
    concurrency: int,
    latencies: list[float],
    errors: int,
    **extra,
) -> dict:
    successful_latencies = latencies or [0.0]
    return {
        "mode": mode,
        "requests": requests,
        "concurrency": concurrency,
        "errors": errors,
        "latency_ms": {
            "min": min(successful_latencies),
            "max": max(successful_latencies),
            "avg": statistics.fmean(successful_latencies),
            "p50": _percentile(successful_latencies, 50),
            "p95": _percentile(successful_latencies, 95),
        },
        **extra,
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = round((percentile / 100) * (len(sorted_values) - 1))
    return sorted_values[index]


def _resource_usage() -> dict:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "max_rss_kb": usage.ru_maxrss,
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
    }


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _require_token(args: argparse.Namespace) -> str:
    if not args.token:
        raise ValueError("--token is required for API benchmarks.")

    return args.token


if __name__ == "__main__":
    raise SystemExit(main())
