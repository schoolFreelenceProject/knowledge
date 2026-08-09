import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DocumentChunkRecord, DocumentRecord, DocumentStatus
from app.schemas.documents import EmbeddedChunk
from app.services.document_management_service import DocumentManagementService
from app.services.metadata_service import DocumentMetadataService
from app.services.text_chunker import ChunkingConfig
from app.services.vector_store import StoredVectorBatch, VectorStoreError


class FakeEmbeddingService:
    def embed_chunks(self, chunks):
        return [
            EmbeddedChunk(
                vector=[float(index), 1.0],
                text=chunk.text,
                metadata=chunk.metadata,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]


class FakeVectorStore:
    def __init__(
        self,
        point_prefix: str = "new-point",
        fail_delete: bool = False,
    ) -> None:
        self.point_prefix = point_prefix
        self.fail_delete = fail_delete
        self.deleted_point_ids: list[str] = []
        self.stored_point_ids: list[str] = []

    def store_embeddings(self, embedded_chunks):
        embedded_chunk_list = list(embedded_chunks)
        point_ids = [
            f"{self.point_prefix}-{chunk.metadata.chunk_index}"
            for chunk in embedded_chunk_list
        ]
        self.stored_point_ids.extend(point_ids)
        return StoredVectorBatch(
            collection_name="company_documents",
            stored_count=len(point_ids),
            vector_size=2,
            point_ids=point_ids,
        )

    def delete_points(self, point_ids):
        if self.fail_delete:
            raise VectorStoreError("simulated Qdrant delete failure")

        self.deleted_point_ids.extend(point_ids)


def _build_services(tmp_path, vector_store=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    metadata_service = DocumentMetadataService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    management_service = DocumentManagementService(
        documents_dir=tmp_path,
        chunk_config=ChunkingConfig(chunk_size=200, chunk_overlap=20),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store or FakeVectorStore(),
        metadata_service=metadata_service,
    )
    return management_service, session_factory


def _create_document(session_factory, tmp_path, content: bytes = b"# Policy\n\nOld text."):
    document_path = tmp_path / "policy.md"
    document_path.write_bytes(content)
    with session_factory() as session:
        document = DocumentRecord(
            filename="policy.md",
            file_type="markdown",
            storage_path="policy.md",
            file_hash=hashlib.sha256(content).hexdigest(),
            status=DocumentStatus.INDEXED.value,
        )
        document.chunks.append(
            DocumentChunkRecord(
                qdrant_point_id="old-point-1",
                chunk_index=1,
                page_number=None,
                start_char=0,
                end_char=20,
            )
        )
        session.add(document)
        session.commit()
        return document.id


def test_list_and_get_documents_from_postgres_metadata(tmp_path) -> None:
    service, session_factory = _build_services(tmp_path)
    document_id = _create_document(session_factory, tmp_path)

    documents = service.list_documents()
    document = service.get_document(document_id)

    assert len(documents) == 1
    assert documents[0].id == document_id
    assert documents[0].chunk_count == 1
    assert document.id == document_id
    assert document.chunks[0].qdrant_point_id == "old-point-1"


def test_delete_stops_when_qdrant_cleanup_fails(tmp_path) -> None:
    vector_store = FakeVectorStore(fail_delete=True)
    service, session_factory = _build_services(tmp_path, vector_store=vector_store)
    document_id = _create_document(session_factory, tmp_path)

    with pytest.raises(VectorStoreError):
        service.delete_document(document_id)

    with session_factory() as session:
        assert session.get(DocumentRecord, document_id) is not None

    assert (tmp_path / "policy.md").exists()


def test_delete_removes_metadata_vectors_and_file(tmp_path) -> None:
    vector_store = FakeVectorStore()
    service, session_factory = _build_services(tmp_path, vector_store=vector_store)
    document_id = _create_document(session_factory, tmp_path)

    response = service.delete_document(document_id)

    with session_factory() as session:
        assert session.get(DocumentRecord, document_id) is None

    assert response.deleted_vectors == 1
    assert response.deleted_metadata is True
    assert response.deleted_file is True
    assert response.cleanup_warning is None
    assert vector_store.deleted_point_ids == ["old-point-1"]
    assert not (tmp_path / "policy.md").exists()


def test_delete_returns_warning_when_file_cleanup_fails_after_db_delete(tmp_path) -> None:
    vector_store = FakeVectorStore()
    service, session_factory = _build_services(tmp_path, vector_store=vector_store)
    document_id = _create_document(session_factory, tmp_path)
    (tmp_path / "policy.md").unlink()

    response = service.delete_document(document_id)

    with session_factory() as session:
        assert session.get(DocumentRecord, document_id) is None

    assert response.deleted_metadata is True
    assert response.deleted_file is False
    assert response.cleanup_warning is not None


def test_reindex_replaces_metadata_then_deletes_old_vectors(tmp_path) -> None:
    vector_store = FakeVectorStore(point_prefix="new-point")
    service, session_factory = _build_services(tmp_path, vector_store=vector_store)
    new_content = b"# Policy\n\nNew reindexed text."
    document_id = _create_document(
        session_factory=session_factory,
        tmp_path=tmp_path,
        content=new_content,
    )

    response = service.reindex_document(document_id)

    with session_factory() as session:
        document = session.get(DocumentRecord, document_id)
        chunks = session.scalars(select(DocumentChunkRecord)).all()

    assert document is not None
    assert document.status == DocumentStatus.INDEXED.value
    assert document.file_hash == hashlib.sha256(new_content).hexdigest()
    assert [chunk.qdrant_point_id for chunk in chunks] == ["new-point-1"]
    assert response.stored_vectors == 1
    assert response.replaced_vectors == 1
    assert vector_store.deleted_point_ids == ["old-point-1"]


def test_reindex_does_not_delete_shared_deterministic_point_ids(tmp_path) -> None:
    vector_store = FakeVectorStore(point_prefix="old-point")
    service, session_factory = _build_services(tmp_path, vector_store=vector_store)
    document_id = _create_document(session_factory, tmp_path)

    response = service.reindex_document(document_id)

    assert response.replaced_vectors == 0
    assert vector_store.deleted_point_ids == []
