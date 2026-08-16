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
    section_heading: str | None
    heading_path: str | None
    block_kind: str | None
    workbook: str | None
    sheet_name: str | None
    cell_range: str | None
    row_start: int | None
    row_end: int | None
    slide_number: int | None
    slide_title: str | None
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


@dataclass(frozen=True)
class StoredDocumentChunkSource:
    document: StoredDocumentMetadata
    chunk: StoredChunkMetadata


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
        _validate_unique_chunk_positions(chunks)

        first_metadata = extracted_documents[0].metadata

        try:
            self.init_database()
            with self.session_factory() as session:
                with session.begin():
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

    def get_document_chunk_source(
        self,
        qdrant_point_id: str,
    ) -> StoredDocumentChunkSource:
        try:
            self.init_database()
            with self.session_factory() as session:
                chunk = session.scalars(
                    select(DocumentChunkRecord)
                    .options(
                        selectinload(DocumentChunkRecord.document).selectinload(
                            DocumentRecord.chunks
                        )
                    )
                    .where(DocumentChunkRecord.qdrant_point_id == qdrant_point_id)
                ).one_or_none()
                if chunk is None:
                    raise DocumentMetadataNotFoundError(
                        f"Document chunk not found for point: {qdrant_point_id}"
                    )

                document = _to_stored_document_metadata(chunk.document)
                stored_chunk = next(
                    (
                        item
                        for item in document.chunks
                        if item.qdrant_point_id == qdrant_point_id
                    ),
                    None,
                )
                if stored_chunk is None:
                    raise DocumentMetadataNotFoundError(
                        f"Document chunk not found for point: {qdrant_point_id}"
                    )
                return StoredDocumentChunkSource(
                    document=document,
                    chunk=stored_chunk,
                )
        except DocumentMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to read document chunk metadata: {exc}"
            ) from exc

    def list_chunk_point_ids(
        self,
        document_ids: list[int] | None = None,
    ) -> list[str]:
        if document_ids is not None and not document_ids:
            return []

        try:
            self.init_database()
            with self.session_factory() as session:
                statement = (
                    select(DocumentChunkRecord.qdrant_point_id)
                    .join(
                        DocumentRecord,
                        DocumentRecord.id == DocumentChunkRecord.document_id,
                    )
                    .where(DocumentRecord.status == DocumentStatus.INDEXED.value)
                    .order_by(
                        DocumentRecord.id.asc(),
                        DocumentChunkRecord.chunk_index.asc(),
                    )
                )
                if document_ids is not None:
                    statement = statement.where(DocumentRecord.id.in_(document_ids))

                return list(session.scalars(statement).all())
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to list document chunk point IDs: {exc}"
            ) from exc

    def get_document_by_file_hash(
        self,
        file_hash: str,
    ) -> StoredDocumentMetadata | None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = session.scalars(
                    select(DocumentRecord)
                    .options(selectinload(DocumentRecord.chunks))
                    .where(DocumentRecord.file_hash == file_hash)
                    .order_by(
                        DocumentRecord.created_at.desc(),
                        DocumentRecord.id.desc(),
                    )
                ).first()
                if record is None:
                    return None

                return _to_stored_document_metadata(record)
        except SQLAlchemyError as exc:
            raise MetadataPersistenceError(
                f"Failed to read document metadata by file hash: {exc}"
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
        _validate_unique_chunk_positions(chunks)

        try:
            self.init_database()
            with self.session_factory() as session:
                with session.begin():
                    record = _get_document_record(
                        session=session,
                        document_id=document_id,
                        load_chunks=False,
                        for_update=True,
                    )
                    record.status = DocumentStatus.PROCESSING.value
                    session.flush()

                    session.execute(
                        delete(DocumentChunkRecord).where(
                            DocumentChunkRecord.document_id == document_id
                        ),
                        execution_options={"synchronize_session": False},
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
            section_heading=chunk.metadata.section_heading,
            heading_path=chunk.metadata.heading_path,
            block_kind=chunk.metadata.block_kind,
            workbook=chunk.metadata.workbook,
            sheet_name=chunk.metadata.sheet_name,
            cell_range=chunk.metadata.cell_range,
            row_start=chunk.metadata.row_start,
            row_end=chunk.metadata.row_end,
            slide_number=chunk.metadata.slide_number,
            slide_title=chunk.metadata.slide_title,
            start_char=chunk.metadata.start_char,
            end_char=chunk.metadata.end_char,
        )
        for chunk, qdrant_point_id in zip(chunks, qdrant_point_ids, strict=True)
    ]


def _validate_unique_chunk_positions(chunks: list[DocumentChunk]) -> None:
    seen: set[int] = set()
    duplicates: set[int] = set()
    for chunk in chunks:
        chunk_index = chunk.metadata.chunk_index
        if chunk_index in seen:
            duplicates.add(chunk_index)
        seen.add(chunk_index)

    if duplicates:
        duplicate_list = ", ".join(str(index) for index in sorted(duplicates))
        raise MetadataPersistenceError(
            f"Generated document chunks contain duplicate chunk positions: "
            f"{duplicate_list}."
        )


def _get_document_record(
    session: Session,
    document_id: int,
    load_chunks: bool = True,
    for_update: bool = False,
) -> DocumentRecord:
    statement = select(DocumentRecord).where(DocumentRecord.id == document_id)
    if load_chunks:
        statement = statement.options(selectinload(DocumentRecord.chunks))
    if for_update:
        statement = statement.with_for_update()

    record = session.scalars(statement).one_or_none()
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
            for chunk in chunks
        ],
    )
