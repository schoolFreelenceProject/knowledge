import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.vector_store import QdrantVectorStore, VectorStoreError


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Inspect Qdrant vector collection status."
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
        "--format",
        choices=("preview", "json"),
        default="preview",
        help="Output format.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="Number of payload samples to show.",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=180,
        help="Maximum payload text characters per preview sample.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        vector_store = QdrantVectorStore(
            url=args.qdrant_url,
            collection_name=args.collection_name,
        )
        status = vector_store.get_status()
        samples = (
            vector_store.list_payload_samples(args.sample_size)
            if status.exists and status.points_count > 0
            else []
        )
    except (ValueError, VectorStoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(
            json.dumps(
                {
                    "status": asdict(status),
                    "samples": samples,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Qdrant URL: {args.qdrant_url}")
    print(f"Collection: {status.collection_name}")
    print(f"Exists: {status.exists}")
    print(f"Points: {status.points_count}")
    print(f"Vector dimension: {status.vector_size}")
    print(f"Distance: {status.distance}")

    if not status.exists:
        print("Collection does not exist yet.")
        return 0

    if not samples:
        print("No payload samples available.")
        return 0

    print()
    print("Payload samples:")
    for index, payload in enumerate(samples, start=1):
        page_number = payload.get("page_number")
        page_label = f"page {page_number}" if page_number is not None else "document"
        text = _preview_text(
            text=str(payload.get("text", "")),
            max_chars=args.max_text_chars,
        )

        print()
        print(
            f"[{index}] {payload.get('filename')} "
            f"({payload.get('file_type')}, {page_label}, "
            f"chunk {payload.get('chunk_index')})"
        )
        print(f"source: {payload.get('source_path')}")
        print(f"chars: {payload.get('start_char')}-{payload.get('end_char')}")
        print(text)

    return 0


def _preview_text(text: str, max_chars: int) -> str:
    if not text:
        return "<empty text>"

    if max_chars < 1:
        return ""

    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars].rstrip()}\n..."


if __name__ == "__main__":
    raise SystemExit(main())
