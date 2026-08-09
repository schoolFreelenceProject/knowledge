import argparse
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
from app.services.vector_store import QdrantVectorStore, VectorStoreError


DEFAULT_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


def parse_args() -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Store document chunk embeddings in Qdrant."
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
        "--qdrant-url",
        default=settings.qdrant_url,
        help="Qdrant HTTP URL.",
    )
    parser.add_argument(
        "--collection-name",
        default=settings.qdrant_collection_name,
        help="Qdrant collection name.",
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

        vector_store = QdrantVectorStore(
            url=args.qdrant_url,
            collection_name=args.collection_name,
        )
        result = vector_store.store_embeddings(embedded_chunks)
    except (
        DocumentLoaderError,
        EmbeddingServiceError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
        VectorStoreError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Documents directory: {args.documents_dir}")
    print(f"Extracted blocks: {len(extracted_documents)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Embeddings: {len(embedded_chunks)}")
    print(f"Qdrant URL: {args.qdrant_url}")
    print(f"Collection: {result.collection_name}")
    print(f"Stored vectors: {result.stored_count}")
    if result.vector_size is not None:
        print(f"Vector dimension: {result.vector_size}")

    if result.stored_count == 0:
        print("No vectors stored from supported PDF or Markdown documents.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
