from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db.models import DocumentChunkRecord, DocumentRecord, DocumentStatus
from app.schemas.documents import DocumentChunk, ExtractedDocument
from app.services.vector_store import StoredVectorBatch


class MetadataPersistenceError(RuntimeError):
    """Raised when document metadata cannot be saved to the database."""


@dataclass(frozen=True)
class PersistedDocumentMetadata:
    document_id: int
    saved_chunks: int
    status: str


@dataclass(frozen=True)
class StoredChunkMetadata:
    id: int
    qdrant_point_id: str
    chunk_index: int
    page_number: int | None
    start_char: int
    end_char: int
    created_at: datetime


@dataclass(frozen=True)
class StoredDocumentMetadata:
    id: int
    filename: str
    file_type: str
    storage_path: str
    file_hash: str
    status: str
    created_at: datetime
    updated_at: datetime
    chunks: list[StoredChunkMetadata]


class DocumentMetadataNotFoundError(MetadataPersistenceError):
    """Raised when a requested document metadata row does not exist."""


class DocumentMetadataService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def save_document_metadata(
        self,
        extracted_documents: list[ExtractedDocument],
        chunks: list[DocumentChunk],
        stored_batch: StoredVectorBatch,
        file_hash: str,
        storage_path: str,
    ) -> PersistedDocumentMetadata:
        if not extracted_documents:
            raise MetadataPersistenceError("Cannot save metadata for zero documents.")

        if len(chunks) != len(stored_batch.point_ids):
            raise MetadataPersistenceError(
                "Stored Qdrant point ID count does not match generated chunk count."
            )

        first_metadata = extracted_documents[0].metadata

        try:
            self.init_database()
            with self.session_factory() as session:
                document_record = DocumentRecord(
                    filename=first_metadata.filename,
                    file_type=first_metadata.file_type,
                    storage_path=storage_path,
                    file_hash=file_hash,
                    status=DocumentStatus.PROCESSING.value,
                )
                session.add(document_record)
                session.flush()

                session.add_all(
                    _build_chunk_records(
                        document_id=document_record.id,
                        chunks=chunks,
                        qdrant_point_ids=stored_batch.point_ids,
                    )
                )
                document_record.status = DocumentStatus.INDEXED.value
                session.commit()
                return PersistedDocumentMetadata(
                    document_id=document_record.id,
                    saved_chunks=len(chunks),
                    status=document_record.status,
                )
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to save document metadata: {exc}"
            ) from exc

    def list_documents(
        self,
        document_ids: list[int] | None = None,
    ) -> list[StoredDocumentMetadata]:
        if document_ids is not None and not document_ids:
            return []

        try:
            self.init_database()
            with self.session_factory() as session:
                statement = (
                    select(DocumentRecord)
                    .options(selectinload(DocumentRecord.chunks))
                    .order_by(
                        DocumentRecord.created_at.desc(),
                        DocumentRecord.id.desc(),
                    )
                )
                if document_ids is not None:
                    statement = statement.where(DocumentRecord.id.in_(document_ids))

                records = session.scalars(
                    statement
                ).all()
                return [_to_stored_document_metadata(record) for record in records]
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to list document metadata: {exc}"
            ) from exc

    def get_document(self, document_id: int) -> StoredDocumentMetadata:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_document_record(session=session, document_id=document_id)
                return _to_stored_document_metadata(record)
        except DocumentMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to read document metadata: {exc}"
            ) from exc

    def delete_document(self, document_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_document_record(session=session, document_id=document_id)
                session.delete(record)
                session.commit()
        except DocumentMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to delete document metadata: {exc}"
            ) from exc

    def replace_document_chunks(
        self,
        document_id: int,
        chunks: list[DocumentChunk],
        stored_batch: StoredVectorBatch,
        file_hash: str,
    ) -> PersistedDocumentMetadata:
        if len(chunks) != len(stored_batch.point_ids):
            raise MetadataPersistenceError(
                "Stored Qdrant point ID count does not match generated chunk count."
            )

        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_document_record(session=session, document_id=document_id)
                record.status = DocumentStatus.PROCESSING.value
                session.flush()

                session.execute(
                    delete(DocumentChunkRecord).where(
                        DocumentChunkRecord.document_id == document_id
                    )
                )
                session.flush()

                session.add_all(
                    _build_chunk_records(
                        document_id=document_id,
                        chunks=chunks,
                        qdrant_point_ids=stored_batch.point_ids,
                    )
                )
                record.file_hash = file_hash
                record.status = DocumentStatus.INDEXED.value
                session.commit()
                return PersistedDocumentMetadata(
                    document_id=record.id,
                    saved_chunks=len(chunks),
                    status=record.status,
                )
        except DocumentMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to replace document metadata: {exc}"
            ) from exc

    def mark_document_failed(self, document_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_document_record(session=session, document_id=document_id)
                record.status = DocumentStatus.FAILED.value
                session.commit()
        except DocumentMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to mark document metadata as failed: {exc}"
            ) from exc


def _build_chunk_records(
    document_id: int,
    chunks: list[DocumentChunk],
    qdrant_point_ids: list[str],
) -> list[DocumentChunkRecord]:
    return [
        DocumentChunkRecord(
            document_id=document_id,
            qdrant_point_id=qdrant_point_id,
            chunk_index=chunk.metadata.chunk_index,
            page_number=chunk.metadata.page_number,
            start_char=chunk.metadata.start_char,
            end_char=chunk.metadata.end_char,
        )
        for chunk, qdrant_point_id in zip(chunks, qdrant_point_ids, strict=True)
    ]


def _get_document_record(session: Session, document_id: int) -> DocumentRecord:
    record = session.scalars(
        select(DocumentRecord)
        .options(selectinload(DocumentRecord.chunks))
        .where(DocumentRecord.id == document_id)
    ).one_or_none()
    if record is None:
        raise DocumentMetadataNotFoundError(f"Document not found: {document_id}")

    return record


def _to_stored_document_metadata(
    record: DocumentRecord,
) -> StoredDocumentMetadata:
    chunks = sorted(record.chunks, key=lambda chunk: chunk.chunk_index)
    return StoredDocumentMetadata(
        id=record.id,
        filename=record.filename,
        file_type=record.file_type,
        storage_path=record.storage_path,
        file_hash=record.file_hash,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        chunks=[
            StoredChunkMetadata(
                id=chunk.id,
                qdrant_point_id=chunk.qdrant_point_id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                created_at=chunk.created_at,
            )
            for chunk in chunks
        ],
    )
