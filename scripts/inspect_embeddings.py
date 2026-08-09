import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.document_loader import DocumentLoaderError, load_documents
from app.services.embedding_service import (
    EmbeddingServiceError,
    SentenceTransformersEmbeddingService,
)
from app.services.text_chunker import ChunkingConfig, chunk_documents


DEFAULT_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Inspect local embeddings generated from document chunks."
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
        "--model-name",
        default=settings.embedding_model_name,
        help="sentence-transformers model name.",
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
        default=300,
        help="Maximum preview characters per chunk text.",
    )
    parser.add_argument(
        "--vector-values",
        type=int,
        default=8,
        help="Number of vector values to show in preview output.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        chunk_config = ChunkingConfig(
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        extracted_documents = load_documents(args.documents_dir)
        chunks = chunk_documents(documents=extracted_documents, config=chunk_config)
        embedding_service = SentenceTransformersEmbeddingService(
            model_name=args.model_name,
        )
        embedded_chunks = embedding_service.embed_chunks(chunks)
    except (
        DocumentLoaderError,
        EmbeddingServiceError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = [chunk.model_dump(mode="json") for chunk in embedded_chunks]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Documents directory: {args.documents_dir}")
    print(f"Extracted blocks: {len(extracted_documents)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Embeddings: {len(embedded_chunks)}")
    print(f"Embedding model: {args.model_name}")
    print(f"Chunk size: {chunk_config.chunk_size}")
    print(f"Chunk overlap: {chunk_config.chunk_overlap}")

    if not embedded_chunks:
        print("No embeddings generated from supported PDF or Markdown documents.")
        return 0

    vector_dimension = len(embedded_chunks[0].vector)
    print(f"Vector dimension: {vector_dimension}")

    for index, embedded_chunk in enumerate(embedded_chunks, start=1):
        metadata = embedded_chunk.metadata
        page_label = (
            f"page {metadata.page_number}"
            if metadata.page_number is not None
            else "document"
        )
        vector_preview = _preview_vector(
            vector=embedded_chunk.vector,
            max_values=args.vector_values,
        )
        text_preview = _preview_text(embedded_chunk.text, max_chars=args.max_chars)

        print()
        print(
            f"[{index}] {metadata.filename} "
            f"({metadata.file_type}, {page_label}, chunk {metadata.chunk_index})"
        )
        print(f"source: {metadata.source_path}")
        print(f"chars: {metadata.start_char}-{metadata.end_char}")
        print(f"vector: {vector_preview}")
        print(text_preview)

    return 0


def _preview_vector(vector: list[float], max_values: int) -> str:
    if max_values < 1:
        return f"<{len(vector)} values>"

    shown_values = ", ".join(f"{value:.6f}" for value in vector[:max_values])
    if len(vector) > max_values:
        return f"[{shown_values}, ...] ({len(vector)} values)"

    return f"[{shown_values}] ({len(vector)} values)"


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
