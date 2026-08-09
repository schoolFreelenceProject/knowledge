import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DocumentChunkRecord, DocumentRecord, DocumentStatus
from app.schemas.documents import EmbeddedChunk
from app.services.ingestion_service import IngestionService
from app.services.metadata_service import (
    DocumentMetadataService,
    MetadataPersistenceError,
)
from app.services.permission_service import PermissionPersistenceError
from app.services.text_chunker import ChunkingConfig
from app.services.vector_store import StoredVectorBatch


class FakeEmbeddingService:
    def embed_chunks(self, chunks):
        return [
            EmbeddedChunk(
                vector=[float(index), 0.0, 1.0],
                text=chunk.text,
                metadata=chunk.metadata,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_point_ids: list[str] = []

    def store_embeddings(self, embedded_chunks):
        embedded_chunk_list = list(embedded_chunks)
        return StoredVectorBatch(
            collection_name="company_documents",
            stored_count=len(embedded_chunk_list),
            vector_size=3,
            point_ids=[
                f"point-{chunk.metadata.chunk_index}"
                for chunk in embedded_chunk_list
            ],
        )

    def delete_points(self, point_ids):
        self.deleted_point_ids.extend(point_ids)


class FailingMetadataService:
    def save_document_metadata(self, **_kwargs):
        raise MetadataPersistenceError("simulated PostgreSQL transaction failure")


class FakePermissionService:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.grants: list[tuple[int, int]] = []

    def grant_document_access(self, document_id: int, user_id: int):
        if self.should_fail:
            raise PermissionPersistenceError("simulated permission failure")

        self.grants.append((document_id, user_id))


def _build_sqlite_metadata_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    metadata_service = DocumentMetadataService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    return metadata_service, session_factory


def test_ingestion_metadata_persistence(tmp_path) -> None:
    metadata_service, session_factory = _build_sqlite_metadata_service()
    content = b"# Security Policy\n\nEmployees must report incidents quickly."

    ingestion_service = IngestionService(
        documents_dir=tmp_path,
        chunk_config=ChunkingConfig(chunk_size=200, chunk_overlap=20),
        embedding_service=FakeEmbeddingService(),
        vector_store=FakeVectorStore(),
        metadata_service=metadata_service,
    )

    response = ingestion_service.ingest_uploaded_document(
        filename="security.md",
        content=content,
    )

    with session_factory() as session:
        document = session.scalars(select(DocumentRecord)).one()
        chunks = session.scalars(select(DocumentChunkRecord)).all()

    assert response.document_id == document.id
    assert response.status == DocumentStatus.INDEXED.value
    assert response.file_hash == hashlib.sha256(content).hexdigest()
    assert document.storage_path == "security.md"
    assert document.file_hash == response.file_hash
    assert document.status == DocumentStatus.INDEXED.value
    assert len(chunks) == response.saved_chunks == response.chunks
    assert chunks[0].qdrant_point_id == "point-1"


def test_metadata_failure_cleans_up_qdrant_points_and_uploaded_file(tmp_path) -> None:
    vector_store = FakeVectorStore()
    ingestion_service = IngestionService(
        documents_dir=tmp_path,
        chunk_config=ChunkingConfig(chunk_size=200, chunk_overlap=20),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        metadata_service=FailingMetadataService(),
    )

    with pytest.raises(MetadataPersistenceError):
        ingestion_service.ingest_uploaded_document(
            filename="security.md",
            content=b"# Security Policy\n\nEmployees must report incidents quickly.",
        )

    assert vector_store.deleted_point_ids == ["point-1"]
    assert not (tmp_path / "security.md").exists()


def test_ingestion_auto_grants_uploader_document_access(tmp_path) -> None:
    metadata_service, session_factory = _build_sqlite_metadata_service()
    permission_service = FakePermissionService()
    ingestion_service = IngestionService(
        documents_dir=tmp_path,
        chunk_config=ChunkingConfig(chunk_size=200, chunk_overlap=20),
        embedding_service=FakeEmbeddingService(),
        vector_store=FakeVectorStore(),
        metadata_service=metadata_service,
        permission_service=permission_service,
    )

    response = ingestion_service.ingest_uploaded_document(
        filename="security.md",
        content=b"# Security Policy\n\nEmployees must report incidents quickly.",
        uploader_user_id=7,
    )

    assert permission_service.grants == [(response.document_id, 7)]
    with session_factory() as session:
        assert session.get(DocumentRecord, response.document_id) is not None


def test_permission_failure_cleans_up_ingested_state(tmp_path) -> None:
    metadata_service, session_factory = _build_sqlite_metadata_service()
    vector_store = FakeVectorStore()
    ingestion_service = IngestionService(
        documents_dir=tmp_path,
        chunk_config=ChunkingConfig(chunk_size=200, chunk_overlap=20),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        metadata_service=metadata_service,
        permission_service=FakePermissionService(should_fail=True),
    )

    with pytest.raises(MetadataPersistenceError):
        ingestion_service.ingest_uploaded_document(
            filename="security.md",
            content=b"# Security Policy\n\nEmployees must report incidents quickly.",
            uploader_user_id=7,
        )

    with session_factory() as session:
        assert session.query(DocumentRecord).count() == 0
        assert session.query(DocumentChunkRecord).count() == 0

    assert vector_store.deleted_point_ids == ["point-1"]
    assert not (tmp_path / "security.md").exists()
