import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.db.models import DocumentStatus
from app.schemas.ingest import (
    FolderIngestFileResult,
    FolderIngestResponse,
    IngestResponse,
)
from app.services.document_loader import (
    MARKDOWN_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    CorruptPdfError,
    DocumentLoaderError,
    EncryptedPdfError,
    PdfExtractionConfig,
    PdfExtractionError,
    ScannedPdfRequiresOcrError,
    load_document,
)
from app.services.embedding_service import (
    EmbeddingServiceError,
    SentenceTransformersEmbeddingService,
)
from app.services.metadata_service import (
    DocumentMetadataService,
    MetadataPersistenceError,
    StoredDocumentMetadata,
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


logger = logging.getLogger(__name__)


FOLDER_EXCLUDED_DIR_NAMES = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "cache",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "out",
    "target",
    "temp",
    "tmp",
    "vendor",
}
SYSTEM_FILENAMES = {".ds_store", "desktop.ini", "thumbs.db"}
MAX_STORED_FILENAME_LENGTH = 255
BINARY_SCAN_BYTES = 4096


class IngestionServiceError(RuntimeError):
    """Raised when an uploaded document cannot be ingested."""


class EmptyUploadError(IngestionServiceError):
    """Raised when the uploaded file has no content."""


class UploadedDocumentConflictError(IngestionServiceError):
    """Raised when an uploaded file would overwrite an existing document."""


class UploadedDocumentStorageError(IngestionServiceError):
    """Raised when the uploaded file cannot be saved."""


@dataclass(frozen=True)
class FolderUploadItem:
    relative_path: str
    content: bytes


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
        pdf_extraction_config: PdfExtractionConfig | None = None,
    ) -> None:
        self.documents_dir = Path(documents_dir)
        self.chunk_config = chunk_config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.metadata_service = metadata_service
        self.permission_service = permission_service
        self.max_upload_bytes = max_upload_bytes
        self.pdf_extraction_config = pdf_extraction_config

    def ingest_uploaded_document(
        self,
        filename: str,
        content: bytes,
        uploader_user_id: int | None = None,
        preserve_relative_path: bool = False,
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

        safe_filename = (
            _safe_relative_path(filename)
            if preserve_relative_path
            else _safe_filename(filename)
        )
        _validate_supported_file_type(safe_filename)
        file_hash = _build_file_hash(content)
        existing_document = _get_existing_document_by_file_hash(
            metadata_service=self.metadata_service,
            file_hash=file_hash,
        )
        if _is_complete_indexed_document(existing_document):
            if uploader_user_id is not None:
                try:
                    self.permission_service.grant_document_access(
                        document_id=existing_document.id,
                        user_id=uploader_user_id,
                    )
                except PermissionServiceError as exc:
                    raise MetadataPersistenceError(
                        f"Failed to grant uploader document access: {exc}"
                    ) from exc

            return _existing_document_response(
                document=existing_document,
                collection_name=_collection_name(self.vector_store),
            )

        document_path = self.documents_dir / safe_filename
        if document_path.exists():
            raise UploadedDocumentConflictError(
                f"Document already exists: {safe_filename}"
            )

        try:
            document_path.parent.mkdir(parents=True, exist_ok=True)
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
                pdf_config=self.pdf_extraction_config,
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
            message="Document indexed.",
        )

    def ingest_folder_documents(
        self,
        folder_name: str,
        files: list[FolderUploadItem],
        uploader_user_id: int,
    ) -> FolderIngestResponse:
        safe_folder_name = _safe_folder_name(folder_name)
        results: list[FolderIngestFileResult] = []
        skip_reasons: dict[str, int] = {}

        for upload in files:
            result = self._ingest_folder_document(
                upload=upload,
                uploader_user_id=uploader_user_id,
            )
            results.append(result)
            if result.status == "skipped" and result.reason is not None:
                _count_reason(skip_reasons, result.reason)

        return FolderIngestResponse(
            folder_name=safe_folder_name,
            files_discovered=len(files),
            indexed=sum(1 for result in results if result.status == "indexed"),
            skipped=sum(1 for result in results if result.status == "skipped"),
            failed=sum(1 for result in results if result.status == "failed"),
            skip_reasons=skip_reasons,
            results=results,
        )

    def _ingest_folder_document(
        self,
        upload: FolderUploadItem,
        uploader_user_id: int,
    ) -> FolderIngestFileResult:
        try:
            safe_relative_path = _safe_relative_path(upload.relative_path)
        except IngestionServiceError:
            return FolderIngestFileResult(
                relative_path=_safe_result_path(upload.relative_path),
                status="skipped",
                reason="unsafe_path",
                message="Skipped unsafe relative path.",
            )

        skip_reason = _folder_skip_reason(
            raw_relative_path=upload.relative_path,
            relative_path=safe_relative_path,
            content=upload.content,
            max_upload_bytes=self.max_upload_bytes,
        )
        if skip_reason is not None:
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="skipped",
                reason=skip_reason,
                message=_skip_message(skip_reason),
            )

        try:
            response = self.ingest_uploaded_document(
                filename=safe_relative_path,
                content=upload.content,
                uploader_user_id=uploader_user_id,
                preserve_relative_path=True,
            )
        except EmptyUploadError:
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="skipped",
                reason="empty_file",
                message=_skip_message("empty_file"),
            )
        except UploadedDocumentConflictError:
            logger.exception(
                "Folder document path conflicts with existing stored document",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="storage_path_conflict",
                message="Document path already exists with different content.",
            )
        except UploadedDocumentStorageError:
            logger.exception(
                "Folder document could not be saved",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="storage_error",
                message="Document could not be saved.",
            )
        except ScannedPdfRequiresOcrError:
            logger.exception(
                "Folder document requires OCR",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="scanned_pdf_requires_ocr",
                message="PDF appears to be scanned and requires OCR.",
            )
        except EncryptedPdfError:
            logger.exception(
                "Folder document is encrypted",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="encrypted_pdf",
                message="PDF is encrypted and cannot be processed.",
            )
        except CorruptPdfError:
            logger.exception(
                "Folder document is unsupported or corrupt",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="unsupported_or_corrupt_pdf",
                message="PDF is unsupported or corrupt.",
            )
        except (PdfExtractionError, DocumentLoaderError, ValueError):
            logger.exception(
                "Folder document could not be processed",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="extraction_failed",
                message="Document text could not be extracted.",
            )
        except IngestionServiceError:
            logger.exception(
                "Folder document could not be processed",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="processing_error",
                message="Document could not be processed.",
            )
        except EmbeddingServiceError:
            logger.exception(
                "Folder document embeddings could not be generated",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="embedding_error",
                message="Document embeddings could not be generated.",
            )
        except VectorStoreError:
            logger.exception(
                "Folder document vectors could not be stored",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="vector_store_error",
                message="Document vectors could not be stored.",
            )
        except MetadataPersistenceError:
            logger.exception(
                "Folder document metadata could not be saved",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="metadata_error",
                message="Document metadata could not be saved.",
            )
        except Exception:
            logger.exception(
                "Unexpected folder document ingestion failure",
                extra={"relative_path": safe_relative_path},
            )
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="failed",
                reason="processing_error",
                message="Document could not be processed.",
            )

        if response.already_indexed:
            return FolderIngestFileResult(
                relative_path=safe_relative_path,
                status="skipped",
                document_id=response.document_id,
                filename=response.filename,
                file_type=response.file_type,
                chunks=response.saved_chunks,
                stored_vectors=0,
                reason="already_indexed",
                message="This file is already indexed.",
            )

        return FolderIngestFileResult(
            relative_path=safe_relative_path,
            status="indexed",
            document_id=response.document_id,
            filename=response.filename,
            file_type=response.file_type,
            chunks=response.chunks,
            stored_vectors=response.stored_vectors,
            message="Document indexed.",
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


def _safe_relative_path(relative_path: str) -> str:
    normalized_path = (relative_path or "").replace("\\", "/").strip()
    if (
        not normalized_path
        or normalized_path.startswith("/")
        or "\x00" in normalized_path
        or re.match(r"^[A-Za-z]:/", normalized_path)
    ):
        raise IngestionServiceError("Uploaded document relative path is invalid.")

    path = PurePosixPath(normalized_path)
    safe_parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise IngestionServiceError("Uploaded document relative path is unsafe.")
        safe_part = _safe_path_component(part)
        if not safe_part:
            raise IngestionServiceError(
                "Uploaded document relative path contains an invalid segment."
            )
        safe_parts.append(safe_part)

    if not safe_parts:
        raise IngestionServiceError("Uploaded document relative path is required.")

    safe_path = PurePosixPath(*safe_parts).as_posix()
    if len(safe_path) > MAX_STORED_FILENAME_LENGTH:
        raise IngestionServiceError("Uploaded document relative path is too long.")

    return safe_path


def _safe_path_component(component: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", component.strip()).strip(" .")


def _safe_folder_name(folder_name: str) -> str:
    normalized_name = (folder_name or "").replace("\\", "/").strip()
    raw_name = next(
        (
            part
            for part in reversed(PurePosixPath(normalized_name).parts)
            if part not in {"", ".", ".."}
        ),
        "",
    )
    safe_name = _safe_path_component(raw_name)
    return safe_name or "Selected folder"


def _safe_result_path(relative_path: str) -> str:
    cleaned = (relative_path or "").replace("\\", "/").replace("\x00", "").strip()
    cleaned = re.sub(r"/+", "/", cleaned)
    return cleaned[:MAX_STORED_FILENAME_LENGTH] or "Unknown file"


def _validate_supported_file_type(filename: str) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported_types = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise IngestionServiceError(
            f"Unsupported document type '{extension}'. "
            f"Supported types: {supported_types}"
        )


def _folder_skip_reason(
    raw_relative_path: str,
    relative_path: str,
    content: bytes,
    max_upload_bytes: int | None,
) -> str | None:
    raw_parts = tuple(
        part
        for part in PurePosixPath(
            (raw_relative_path or "").replace("\\", "/").strip()
        ).parts
        if part not in {"", "."}
    )
    safe_parts = PurePosixPath(relative_path).parts
    filename = safe_parts[-1]
    raw_filename = raw_parts[-1] if raw_parts else filename
    lower_filename = raw_filename.casefold()
    directory_names = [part.casefold() for part in raw_parts[:-1]]

    if any(
        directory_name in FOLDER_EXCLUDED_DIR_NAMES
        for directory_name in directory_names
    ):
        return "excluded_directory"

    if lower_filename in SYSTEM_FILENAMES or any(
        part.startswith(".") for part in raw_parts
    ):
        return "hidden_or_system_file"

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return "unsupported_extension"

    if not content:
        return "empty_file"

    if max_upload_bytes is not None and len(content) > max_upload_bytes:
        return "too_large"

    if extension in MARKDOWN_EXTENSIONS and _looks_binary(content):
        return "binary_file"

    return None


def _looks_binary(content: bytes) -> bool:
    sample = content[:BINARY_SCAN_BYTES]
    if b"\x00" in sample:
        return True
    if not sample:
        return False

    control_bytes = sum(
        1
        for byte in sample
        if byte < 32 and byte not in {9, 10, 12, 13}
    )
    return control_bytes / len(sample) > 0.30


def _skip_message(reason: str) -> str:
    return {
        "already_indexed": "This file is already indexed.",
        "binary_file": "Skipped binary file.",
        "empty_file": "Skipped empty file.",
        "excluded_directory": "Skipped excluded directory.",
        "hidden_or_system_file": "Skipped hidden or system file.",
        "too_large": "Skipped file over the upload size limit.",
        "unsupported_extension": "Skipped unsupported file type.",
        "unsafe_path": "Skipped unsafe relative path.",
    }.get(reason, "Skipped file.")


def _count_reason(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


def _is_complete_indexed_document(
    document: StoredDocumentMetadata | None,
) -> bool:
    return (
        document is not None
        and document.status == DocumentStatus.INDEXED.value
        and bool(document.chunks)
    )


def _get_existing_document_by_file_hash(
    metadata_service: DocumentMetadataService,
    file_hash: str,
) -> StoredDocumentMetadata | None:
    get_by_hash = getattr(metadata_service, "get_document_by_file_hash", None)
    if get_by_hash is None:
        return None

    return get_by_hash(file_hash)


def _existing_document_response(
    document: StoredDocumentMetadata,
    collection_name: str,
) -> IngestResponse:
    return IngestResponse(
        document_id=document.id,
        filename=document.filename,
        storage_path=document.storage_path,
        file_type=document.file_type,
        file_hash=document.file_hash,
        status=document.status,
        extracted_blocks=0,
        chunks=len(document.chunks),
        embeddings=0,
        collection_name=collection_name,
        stored_vectors=0,
        saved_chunks=len(document.chunks),
        vector_size=None,
        already_indexed=True,
        message="This file is already indexed.",
    )


def _collection_name(vector_store: QdrantVectorStore) -> str:
    return getattr(vector_store, "collection_name", "company_documents")
