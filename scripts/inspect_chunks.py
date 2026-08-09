import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.document_loader import DocumentLoaderError, load_documents
from app.services.text_chunker import ChunkingConfig, chunk_documents


DEFAULT_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Inspect text chunks generated from PDF and Markdown documents."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DEFAULT_DOCUMENTS_DIR,
        help="Directory containing PDF and Markdown files.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.document_chunk_size,
        help="Maximum characters per chunk.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=settings.document_chunk_overlap,
        help="Overlapping characters between adjacent chunks.",
    )
    parser.add_argument(
        "--format",
        choices=("preview", "json"),
        default="preview",
        help="Output format.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=500,
        help="Maximum preview characters per chunk.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        config = ChunkingConfig(
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        extracted_documents = load_documents(args.documents_dir)
        chunks = chunk_documents(documents=extracted_documents, config=config)
    except (
        DocumentLoaderError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = [chunk.model_dump(mode="json") for chunk in chunks]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Documents directory: {args.documents_dir}")
    print(f"Extracted blocks: {len(extracted_documents)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Chunk size: {config.chunk_size}")
    print(f"Chunk overlap: {config.chunk_overlap}")

    if not chunks:
        print("No chunks generated from supported PDF or Markdown documents.")
        return 0

    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.metadata
        page_label = (
            f"page {metadata.page_number}"
            if metadata.page_number is not None
            else "document"
        )
        preview = _preview_text(chunk.text, max_chars=args.max_chars)

        print()
        print(
            f"[{index}] {metadata.filename} "
            f"({metadata.file_type}, {page_label}, chunk {metadata.chunk_index})"
        )
        print(f"source: {metadata.source_path}")
        print(f"chars: {metadata.start_char}-{metadata.end_char}")
        print(f"length: {len(chunk.text)}")
        print(preview)

    return 0


def _preview_text(text: str, max_chars: int) -> str:
    if not text:
        return "<empty chunk>"

    if max_chars < 1:
        return ""

    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars].rstrip()}\n..."


if __name__ == "__main__":
    raise SystemExit(main())
