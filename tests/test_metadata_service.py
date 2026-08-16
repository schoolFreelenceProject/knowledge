from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DocumentChunkRecord, DocumentRecord, DocumentStatus
from app.schemas.documents import (
    ChunkMetadata,
    DocumentChunk,
    DocumentMetadata,
    ExtractedDocument,
)
from app.services.metadata_service import DocumentMetadataService
from app.services.vector_store import StoredVectorBatch


def _build_metadata_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        DocumentMetadataService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _build_document() -> ExtractedDocument:
    return ExtractedDocument(
        text="Password rules require at least twelve characters.",
        metadata=DocumentMetadata(
            filename="security.md",
            source_path="security.md",
            file_type="markdown",
            page_number=None,
        ),
    )


def _build_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            text="Password rules require at least twelve characters.",
            metadata=ChunkMetadata(
                filename="security.md",
                source_path="security.md",
                file_type="markdown",
                page_number=None,
                chunk_index=1,
                start_char=0,
                end_char=52,
            ),
        )
    ]


def _build_office_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            text="Workbook: 勤務表.xlsx\nSheet: 勤怠\nRow 2: A=山田太郎",
            metadata=ChunkMetadata(
                filename="勤務表.xlsx",
                source_path="勤務表.xlsx",
                file_type="xlsx",
                page_number=None,
                workbook="勤務表.xlsx",
                sheet_name="勤怠",
                cell_range="A1:C2",
                row_start=1,
                row_end=2,
                block_kind="sheet_rows",
                chunk_index=1,
                start_char=0,
                end_char=49,
            ),
        )
    ]


def test_document_metadata_creation() -> None:
    metadata_service, session_factory = _build_metadata_service()

    persisted = metadata_service.save_document_metadata(
        extracted_documents=[_build_document()],
        chunks=_build_chunks(),
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=1,
            vector_size=384,
            point_ids=["point-1"],
        ),
        file_hash="b" * 64,
        storage_path="security.md",
    )

    with session_factory() as session:
        document = session.scalars(select(DocumentRecord)).one()
        assert persisted.document_id == document.id
        assert document.filename == "security.md"
        assert document.storage_path == "security.md"
        assert document.file_hash == "b" * 64
        assert document.status == DocumentStatus.INDEXED.value


def test_chunk_metadata_creation() -> None:
    metadata_service, session_factory = _build_metadata_service()

    persisted = metadata_service.save_document_metadata(
        extracted_documents=[_build_document()],
        chunks=_build_chunks(),
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=1,
            vector_size=384,
            point_ids=["point-1"],
        ),
        file_hash="c" * 64,
        storage_path="security.md",
    )

    with session_factory() as session:
        chunk = session.scalars(select(DocumentChunkRecord)).one()
        assert persisted.saved_chunks == 1
        assert chunk.document_id == persisted.document_id
        assert chunk.qdrant_point_id == "point-1"
        assert chunk.chunk_index == 1
        assert chunk.start_char == 0
        assert chunk.end_char == 52


def test_chunk_metadata_preserves_office_location_fields() -> None:
    metadata_service, session_factory = _build_metadata_service()
    document = ExtractedDocument(
        text="Workbook: 勤務表.xlsx\nSheet: 勤怠\nRow 2: A=山田太郎",
        metadata=DocumentMetadata(
            filename="勤務表.xlsx",
            source_path="勤務表.xlsx",
            file_type="xlsx",
            workbook="勤務表.xlsx",
            sheet_name="勤怠",
            cell_range="A1:C2",
            row_start=1,
            row_end=2,
            block_kind="sheet_rows",
        ),
    )

    persisted = metadata_service.save_document_metadata(
        extracted_documents=[document],
        chunks=_build_office_chunks(),
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=1,
            vector_size=384,
            point_ids=["point-office-1"],
        ),
        file_hash="d" * 64,
        storage_path="勤務表.xlsx",
    )

    stored = metadata_service.get_document(persisted.document_id)

    assert stored.chunks[0].workbook == "勤務表.xlsx"
    assert stored.chunks[0].sheet_name == "勤怠"
    assert stored.chunks[0].cell_range == "A1:C2"
    assert stored.chunks[0].row_start == 1
    assert stored.chunks[0].row_end == 2
