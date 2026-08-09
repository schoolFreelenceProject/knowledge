from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    UserRecord,
)
from app.schemas.documents import EmbeddedChunk
from app.services.code_chunker import CodeChunkingConfig
from app.services.code_ingestion_service import CodeIngestionService
from app.services.code_metadata_service import CodeMetadataService
from app.services.code_parser import TreeSitterCodeParser
from app.services.code_repository_loader import ClonedRepository
from app.services.permission_service import PermissionService
from app.services.vector_store import StoredVectorBatch


class FakeRepositoryLoader:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def clone_repository(self, repo_url: str, branch: str):
        return ClonedRepository(
            repo_url=repo_url,
            repo_name="repo",
            branch=branch,
            commit_sha="a" * 40,
            path=self.repo_path,
            storage_path="repo/main/aaaaaaaa",
        )

    def discover_code_files(self, repository_path, include_globs, exclude_globs):
        return [repository_path / "app.py"]


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
    def store_embeddings(self, embedded_chunks):
        embedded_chunk_list = list(embedded_chunks)
        return StoredVectorBatch(
            collection_name="company_documents",
            stored_count=len(embedded_chunk_list),
            vector_size=3,
            point_ids=[
                f"code-point-{chunk.metadata.chunk_index}"
                for chunk in embedded_chunk_list
            ],
        )

    def delete_points(self, _point_ids):
        return None


def _build_services(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    metadata_service = CodeMetadataService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    permission_service = PermissionService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    with session_factory() as session:
        session.add(
            UserRecord(
                id=7,
                email="uploader@example.com",
                password_hash="$argon2id$hash",
            )
        )
        session.commit()

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "app.py").write_text(
        "def hello():\n    return 'hi'\n",
        encoding="utf-8",
    )
    service = CodeIngestionService(
        repository_loader=FakeRepositoryLoader(repo_path=repo_path),
        parser=TreeSitterCodeParser(),
        chunk_config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
        embedding_service=FakeEmbeddingService(),
        vector_store=FakeVectorStore(),
        metadata_service=metadata_service,
        permission_service=permission_service,
    )
    return service, session_factory


def test_code_ingestion_persists_metadata_and_grants_uploader_access(tmp_path) -> None:
    service, session_factory = _build_services(tmp_path)

    response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    with session_factory() as session:
        repository = session.scalars(select(CodeRepositoryRecord)).one()
        permission = session.scalars(select(CodeRepositoryPermissionRecord)).one()

    assert response.repository_id == repository.id
    assert response.files == 1
    assert response.chunks >= 1
    assert response.stored_vectors == response.chunks
    assert permission.repository_id == repository.id
    assert permission.user_id == 7
