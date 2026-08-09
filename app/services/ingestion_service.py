import hashlib
import re
from pathlib import Path

from app.schemas.ingest import IngestResponse
from app.services.document_loader import (
    SUPPORTED_EXTENSIONS,
    load_document,
)
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.metadata_service import (
    DocumentMetadataService,
    MetadataPersistenceError,
)
from app.services.permission_service import (
    PermissionService,
    PermissionServiceError,
)
from app.services.text_chunker import ChunkingConfig, chunk_documents
from app.services.vector_store import (
    QdrantVectorStore,
    StoredVectorBatch,
    VectorStoreError,
)


class IngestionServiceError(RuntimeError):
    """Raised when an uploaded document cannot be ingested."""


class EmptyUploadError(IngestionServiceError):
    """Raised when the uploaded file has no content."""


class UploadedDocumentConflictError(IngestionServiceError):
    """Raised when an uploaded file would overwrite an existing document."""


class UploadedDocumentStorageError(IngestionServiceError):
    """Raised when the uploaded file cannot be saved."""


class IngestionService:
    def __init__(
        self,
        documents_dir: str | Path,
        chunk_config: ChunkingConfig,
        embedding_service: SentenceTransformersEmbeddingService,
        vector_store: QdrantVectorStore,
        metadata_service: DocumentMetadataService,
        permission_service: PermissionService | None = None,
        max_upload_bytes: int | None = None,
    ) -> None:
        self.documents_dir = Path(documents_dir)
        self.chunk_config = chunk_config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.metadata_service = metadata_service
        self.permission_service = permission_service
        self.max_upload_bytes = max_upload_bytes

    def ingest_uploaded_document(
        self,
        filename: str,
        content: bytes,
        uploader_user_id: int | None = None,
    ) -> IngestResponse:
        if not content:
            raise EmptyUploadError("Uploaded document cannot be empty.")

        if self.max_upload_bytes is not None and len(content) > self.max_upload_bytes:
            raise IngestionServiceError(
                f"Uploaded document exceeds the maximum size of "
                f"{self.max_upload_bytes} bytes."
            )

        if uploader_user_id is not None and self.permission_service is None:
            raise IngestionServiceError(
                "Permission service is required to grant uploader document access."
            )

        safe_filename = _safe_filename(filename)
        _validate_supported_file_type(safe_filename)
        file_hash = _build_file_hash(content)

        document_path = self.documents_dir / safe_filename
        if document_path.exists():
            raise UploadedDocumentConflictError(
                f"Document already exists: {safe_filename}"
            )

        try:
            self.documents_dir.mkdir(parents=True, exist_ok=True)
            document_path.write_bytes(content)
        except OSError as exc:
            document_path.unlink(missing_ok=True)
            raise UploadedDocumentStorageError(
                f"Failed to save uploaded document '{safe_filename}': {exc}"
            ) from exc

        try:
            extracted_documents = load_document(
                document_path=document_path,
                documents_dir=self.documents_dir,
            )
            if not extracted_documents:
                raise IngestionServiceError(
                    "No extractable content was found in the uploaded document."
                )

            chunks = chunk_documents(
                documents=extracted_documents,
                config=self.chunk_config,
            )
            if not chunks:
                raise IngestionServiceError(
                    "No text chunks were generated from the uploaded document."
                )

            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            stored_batch = self.vector_store.store_embeddings(embedded_chunks)
        except Exception:
            document_path.unlink(missing_ok=True)
            raise

        first_metadata = extracted_documents[0].metadata
        storage_path = first_metadata.source_path

        try:
            persisted_metadata = self.metadata_service.save_document_metadata(
                extracted_documents=extracted_documents,
                chunks=chunks,
                stored_batch=stored_batch,
                file_hash=file_hash,
                storage_path=storage_path,
            )
        except MetadataPersistenceError as exc:
            cleanup_error = _cleanup_after_metadata_failure(
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                document_path=document_path,
            )
            if cleanup_error:
                raise MetadataPersistenceError(
                    f"{exc} Cleanup also failed: {cleanup_error}"
                ) from exc
            raise

        if uploader_user_id is not None:
            try:
                self.permission_service.grant_document_access(
                    document_id=persisted_metadata.document_id,
                    user_id=uploader_user_id,
                )
            except PermissionServiceError as exc:
                cleanup_error = _cleanup_after_permission_failure(
                    vector_store=self.vector_store,
                    metadata_service=self.metadata_service,
                    stored_batch=stored_batch,
                    document_id=persisted_metadata.document_id,
                    document_path=document_path,
                )
                if cleanup_error:
                    raise MetadataPersistenceError(
                        f"Failed to grant uploader document access: {exc}. "
                        f"Cleanup also failed: {cleanup_error}"
                    ) from exc
                raise MetadataPersistenceError(
                    f"Failed to grant uploader document access: {exc}"
                ) from exc

        return IngestResponse(
            document_id=persisted_metadata.document_id,
            filename=first_metadata.filename,
            storage_path=storage_path,
            file_type=first_metadata.file_type,
            file_hash=file_hash,
            status=persisted_metadata.status,
            extracted_blocks=len(extracted_documents),
            chunks=len(chunks),
            embeddings=len(embedded_chunks),
            collection_name=stored_batch.collection_name,
            stored_vectors=stored_batch.stored_count,
            saved_chunks=persisted_metadata.saved_chunks,
            vector_size=stored_batch.vector_size,
        )


def _build_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _cleanup_after_metadata_failure(
    vector_store: QdrantVectorStore,
    stored_batch: StoredVectorBatch,
    document_path: Path,
) -> str | None:
    cleanup_errors: list[str] = []

    try:
        vector_store.delete_points(stored_batch.point_ids)
    except VectorStoreError as exc:
        cleanup_errors.append(str(exc))

    try:
        document_path.unlink(missing_ok=True)
    except OSError as exc:
        cleanup_errors.append(
            f"Failed to delete uploaded file '{document_path}': {exc}"
        )

    if cleanup_errors:
        return "; ".join(cleanup_errors)

    return None


def _cleanup_after_permission_failure(
    vector_store: QdrantVectorStore,
    metadata_service: DocumentMetadataService,
    stored_batch: StoredVectorBatch,
    document_id: int,
    document_path: Path,
) -> str | None:
    cleanup_errors: list[str] = []

    try:
        vector_store.delete_points(stored_batch.point_ids)
    except VectorStoreError as exc:
        cleanup_errors.append(str(exc))

    try:
        metadata_service.delete_document(document_id)
    except MetadataPersistenceError as exc:
        cleanup_errors.append(str(exc))

    try:
        document_path.unlink(missing_ok=True)
    except OSError as exc:
        cleanup_errors.append(
            f"Failed to delete uploaded file '{document_path}': {exc}"
        )

    if cleanup_errors:
        return "; ".join(cleanup_errors)

    return None


def _safe_filename(filename: str) -> str:
    raw_filename = Path(filename or "").name.strip()
    if not raw_filename or raw_filename in {".", ".."}:
        raise IngestionServiceError("Uploaded document filename is required.")

    safe_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_filename).strip(" .")
    if not safe_filename:
        raise IngestionServiceError("Uploaded document filename is invalid.")

    return safe_filename


def _validate_supported_file_type(filename: str) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported_types = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise IngestionServiceError(
            f"Unsupported document type '{extension}'. "
            f"Supported types: {supported_types}"
        )
