import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from app.schemas.document_management import (
    DeleteDocumentResponse,
    DocumentChunkDetail,
    DocumentDetail,
    DocumentSummary,
    ReindexDocumentResponse,
)
from app.services.document_loader import PdfExtractionConfig, load_document
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.metadata_service import (
    DocumentMetadataService,
    MetadataPersistenceError,
    StoredDocumentMetadata,
)
from app.services.text_chunker import ChunkingConfig, chunk_documents
from app.services.vector_store import (
    QdrantVectorStore,
    StoredVectorBatch,
    VectorStoreError,
)


logger = logging.getLogger(__name__)


class DocumentManagementError(RuntimeError):
    """Raised when a document management operation cannot be completed."""


class DocumentStorageError(DocumentManagementError):
    """Raised when a stored document file cannot be read or resolved."""


class DocumentManagementService:
    def __init__(
        self,
        documents_dir: str | Path,
        chunk_config: ChunkingConfig,
        embedding_service: SentenceTransformersEmbeddingService,
        vector_store: QdrantVectorStore,
        metadata_service: DocumentMetadataService,
        pdf_extraction_config: PdfExtractionConfig | None = None,
        retrieval_index_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.documents_dir = Path(documents_dir)
        self.chunk_config = chunk_config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.metadata_service = metadata_service
        self.pdf_extraction_config = pdf_extraction_config
        self.retrieval_index_refresh = retrieval_index_refresh

    def list_documents(
        self,
        document_ids: list[int] | None = None,
    ) -> list[DocumentSummary]:
        return [
            _to_document_summary(document)
            for document in self.metadata_service.list_documents(
                document_ids=document_ids,
            )
        ]

    def get_document(self, document_id: int) -> DocumentDetail:
        return _to_document_detail(self.metadata_service.get_document(document_id))

    def delete_document(self, document_id: int) -> DeleteDocumentResponse:
        document = self.metadata_service.get_document(document_id)
        point_ids = _document_point_ids(document)
        document_path = self._resolve_storage_path(document.storage_path)

        self.vector_store.delete_points(point_ids)
        self.metadata_service.delete_document(document_id)

        deleted_file, cleanup_warning = _delete_stored_file(document_path)
        _refresh_retrieval_index_best_effort(self.retrieval_index_refresh)

        return DeleteDocumentResponse(
            document_id=document.id,
            deleted_vectors=len(point_ids),
            deleted_metadata=True,
            deleted_file=deleted_file,
            cleanup_warning=cleanup_warning,
        )

    def reindex_document(self, document_id: int) -> ReindexDocumentResponse:
        document = self.metadata_service.get_document(document_id)
        old_point_ids = _document_point_ids(document)
        document_path = self._resolve_storage_path(document.storage_path)

        try:
            content = document_path.read_bytes()
        except OSError as exc:
            raise DocumentStorageError(
                f"Failed to read stored document '{document.storage_path}': {exc}"
            ) from exc

        new_batch: StoredVectorBatch | None = None
        old_point_id_set = set(old_point_ids)
        try:
            extracted_documents = load_document(
                document_path=document_path,
                documents_dir=self.documents_dir,
                pdf_config=self.pdf_extraction_config,
            )
            chunks = chunk_documents(
                documents=extracted_documents,
                config=self.chunk_config,
            )
            if not chunks:
                raise DocumentManagementError(
                    "No text chunks were generated from the stored document."
                )

            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            new_batch = self.vector_store.store_embeddings(embedded_chunks)
            persisted = self.metadata_service.replace_document_chunks(
                document_id=document_id,
                chunks=chunks,
                stored_batch=new_batch,
                file_hash=_build_file_hash(content),
            )
        except MetadataPersistenceError:
            if new_batch is not None:
                _cleanup_new_vectors_best_effort(
                    self.vector_store,
                    [
                        point_id
                        for point_id in new_batch.point_ids
                        if point_id not in old_point_id_set
                    ],
                )
            raise

        new_point_ids = set(new_batch.point_ids)
        stale_point_ids = [
            point_id
            for point_id in old_point_ids
            if point_id not in new_point_ids
        ]
        cleanup_warning = _cleanup_old_vectors_after_reindex(
            vector_store=self.vector_store,
            point_ids=stale_point_ids,
        )
        _refresh_retrieval_index_best_effort(self.retrieval_index_refresh)

        return ReindexDocumentResponse(
            document_id=document_id,
            status=persisted.status,
            chunks=persisted.saved_chunks,
            stored_vectors=new_batch.stored_count,
            replaced_vectors=len(stale_point_ids),
            cleanup_warning=cleanup_warning,
        )

    def _resolve_storage_path(self, storage_path: str) -> Path:
        base_dir = self.documents_dir.resolve()
        candidate = (base_dir / storage_path).resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError as exc:
            raise DocumentStorageError(
                f"Stored document path escapes the documents directory: {storage_path}"
            ) from exc

        return candidate


def _to_document_summary(document: StoredDocumentMetadata) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        filename=document.filename,
        file_type=document.file_type,
        storage_path=document.storage_path,
        file_hash=document.file_hash,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunk_count=len(document.chunks),
    )


def _to_document_detail(document: StoredDocumentMetadata) -> DocumentDetail:
    summary = _to_document_summary(document)
    return DocumentDetail(
        **summary.model_dump(),
        chunks=[
            DocumentChunkDetail(
                id=chunk.id,
                qdrant_point_id=chunk.qdrant_point_id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_heading=chunk.section_heading,
                heading_path=chunk.heading_path,
                block_kind=chunk.block_kind,
                workbook=chunk.workbook,
                sheet_name=chunk.sheet_name,
                cell_range=chunk.cell_range,
                row_start=chunk.row_start,
                row_end=chunk.row_end,
                slide_number=chunk.slide_number,
                slide_title=chunk.slide_title,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                created_at=chunk.created_at,
            )
            for chunk in document.chunks
        ],
    )


def _document_point_ids(document: StoredDocumentMetadata) -> list[str]:
    return [chunk.qdrant_point_id for chunk in document.chunks]


def _delete_stored_file(document_path: Path) -> tuple[bool, str | None]:
    try:
        document_path.unlink()
        return True, None
    except FileNotFoundError:
        return False, f"Stored document file was already missing: {document_path}"
    except OSError as exc:
        return False, f"Failed to delete stored document file '{document_path}': {exc}"


def _cleanup_old_vectors_after_reindex(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> str | None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError as exc:
        return f"Failed to delete old Qdrant vectors after reindex: {exc}"

    return None


def _cleanup_new_vectors_best_effort(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError:
        pass


def _build_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _refresh_retrieval_index_best_effort(
    refresh: Callable[[], None] | None,
) -> None:
    if refresh is None:
        return

    try:
        refresh()
    except Exception:
        logger.warning(
            "Failed to refresh retrieval indexes after document management change.",
            exc_info=True,
        )
