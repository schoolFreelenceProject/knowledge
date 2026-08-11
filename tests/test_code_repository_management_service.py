from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeChunkRecord,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    CodeSourceType,
    DocumentStatus,
    UserRecord,
)
from app.schemas.documents import EmbeddedChunk
from app.services.code_chunker import CodeChunkingConfig, chunk_code_files
from app.services.code_metadata_service import CodeMetadataService
from app.services.code_parser import ParsedCodeFile
from app.services.code_repository_management_service import (
    CodeRepositoryManagementService,
)
from app.services.code_repository_loader import CodeFileDiscovery
from app.services.permission_service import PermissionService
from app.services.vector_store import StoredVectorBatch, VectorStoreError


class FakeRepositoryLoader:
    def discover_code_files(self, repository_path, include_globs, exclude_globs):
        return [repository_path / "app.py"]

    def discover_code_files_with_stats(
        self,
        repository_path,
        include_globs,
        exclude_globs,
    ):
        return CodeFileDiscovery(
            paths=[repository_path / "app.py"],
            skipped_files=0,
            skip_reasons={},
        )


class FakeParser:
    def parse_file(
        self,
        file_path: Path,
        repository_root: Path,
        repo_url: str | None,
        repo_name: str,
        branch: str | None,
        commit_sha: str | None,
        source_type: str = "GIT_REPOSITORY",
        source_path_prefix: str | None = None,
    ) -> ParsedCodeFile:
        text = file_path.read_text(encoding="utf-8")
        relative_path = file_path.relative_to(repository_root).as_posix()
        prefix = source_path_prefix or f"{repo_name}@{commit_sha}"
        return ParsedCodeFile(
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            commit_sha=commit_sha,
            source_type=source_type,
            file_path=relative_path,
            language="python",
            text=text,
            file_hash="b" * 64,
            size_bytes=len(text.encode("utf-8")),
            source_path=f"{prefix}/{relative_path}",
            symbols=[],
        )


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
        point_prefix: str = "new-code-point",
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
    metadata_service = CodeMetadataService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    permission_service = PermissionService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    management_service = CodeRepositoryManagementService(
        repositories_dir=tmp_path,
        repository_loader=FakeRepositoryLoader(),
        parser=FakeParser(),
        chunk_config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store or FakeVectorStore(),
        metadata_service=metadata_service,
    )
    return management_service, metadata_service, permission_service, session_factory


def _create_repository(
    metadata_service,
    session_factory,
    tmp_path,
    content: str = "def old():\n    return 'old'\n",
) -> int:
    repository_path = tmp_path / "repo" / "main" / ("a" * 40)
    repository_path.mkdir(parents=True)
    app_path = repository_path / "app.py"
    app_path.write_text(content, encoding="utf-8")
    parsed_file = FakeParser().parse_file(
        file_path=app_path,
        repository_root=repository_path,
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
    )
    chunks = chunk_code_files(
        [parsed_file],
        config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
    )
    persisted = metadata_service.save_repository_metadata(
        parsed_files=[parsed_file],
        chunks=chunks,
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=len(chunks),
            vector_size=2,
            point_ids=["old-code-point-1"],
        ),
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
        storage_path=f"repo/main/{'a' * 40}",
    )
    with session_factory() as session:
        session.add(
            UserRecord(
                id=7,
                email="developer@example.com",
                password_hash="$argon2id$hash",
            )
        )
        session.commit()

    return persisted.repository_id


def _create_local_folder_repository(
    metadata_service,
    session_factory,
    tmp_path,
    content: str = "def old():\n    return 'old'\n",
) -> int:
    source_fingerprint = "b" * 64
    repository_path = tmp_path / "local" / "LocalCode" / source_fingerprint[:16]
    repository_path.mkdir(parents=True)
    app_path = repository_path / "app.py"
    app_path.write_text(content, encoding="utf-8")
    parsed_file = FakeParser().parse_file(
        file_path=app_path,
        repository_root=repository_path,
        repo_url=None,
        repo_name="LocalCode",
        branch=None,
        commit_sha=None,
        source_type=CodeSourceType.LOCAL_FOLDER.value,
        source_path_prefix=f"LocalCode@local-{source_fingerprint[:12]}",
    )
    chunks = chunk_code_files(
        [parsed_file],
        config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
    )
    persisted = metadata_service.save_repository_metadata(
        parsed_files=[parsed_file],
        chunks=chunks,
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=len(chunks),
            vector_size=2,
            point_ids=["old-code-point-1"],
        ),
        repo_url=None,
        repo_name="LocalCode",
        branch=None,
        commit_sha=None,
        storage_path=f"local/LocalCode/{source_fingerprint[:16]}",
        source_type=CodeSourceType.LOCAL_FOLDER.value,
        source_fingerprint=source_fingerprint,
    )
    with session_factory() as session:
        session.add(
            UserRecord(
                id=7,
                email="developer@example.com",
                password_hash="$argon2id$hash",
            )
        )
        session.commit()

    return persisted.repository_id


def test_list_and_get_code_repositories_from_postgres_metadata(tmp_path) -> None:
    service, metadata_service, _permission_service, session_factory = _build_services(
        tmp_path
    )
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)

    repositories = service.list_repositories()
    repository = service.get_repository(repository_id)

    assert len(repositories) == 1
    assert repositories[0].id == repository_id
    assert repositories[0].branch == "main"
    assert repositories[0].commit_sha == "a" * 40
    assert repositories[0].file_count == 1
    assert repositories[0].chunk_count == 1
    assert repository.files[0].file_path == "app.py"
    assert repository.chunks[0].qdrant_point_id == "old-code-point-1"


def test_delete_stops_when_qdrant_cleanup_fails(tmp_path) -> None:
    vector_store = FakeVectorStore(fail_delete=True)
    service, metadata_service, _permission_service, session_factory = _build_services(
        tmp_path,
        vector_store=vector_store,
    )
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)

    with pytest.raises(VectorStoreError):
        service.delete_repository(repository_id)

    with session_factory() as session:
        assert session.get(CodeRepositoryRecord, repository_id) is not None

    assert (tmp_path / "repo" / "main" / ("a" * 40)).exists()


def test_delete_removes_metadata_vectors_permissions_and_files(tmp_path) -> None:
    vector_store = FakeVectorStore()
    (
        service,
        metadata_service,
        permission_service,
        session_factory,
    ) = _build_services(tmp_path, vector_store=vector_store)
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)
    permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=7,
    )

    response = service.delete_repository(repository_id)

    with session_factory() as session:
        assert session.get(CodeRepositoryRecord, repository_id) is None
        assert session.scalars(select(CodeRepositoryPermissionRecord)).all() == []

    assert response.deleted_vectors == 1
    assert response.deleted_metadata is True
    assert response.deleted_files is True
    assert response.cleanup_warning is None
    assert vector_store.deleted_point_ids == ["old-code-point-1"]
    assert not (tmp_path / "repo" / "main" / ("a" * 40)).exists()


def test_delete_returns_warning_when_repository_files_are_missing(tmp_path) -> None:
    vector_store = FakeVectorStore()
    service, metadata_service, _permission_service, session_factory = _build_services(
        tmp_path,
        vector_store=vector_store,
    )
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)
    repository_path = tmp_path / "repo" / "main" / ("a" * 40)
    for child in repository_path.iterdir():
        child.unlink()
    repository_path.rmdir()

    response = service.delete_repository(repository_id)

    with session_factory() as session:
        assert session.get(CodeRepositoryRecord, repository_id) is None

    assert response.deleted_metadata is True
    assert response.deleted_files is False
    assert response.cleanup_warning is not None
    assert vector_store.deleted_point_ids == ["old-code-point-1"]


def test_reindex_replaces_files_chunks_and_deletes_stale_vectors(tmp_path) -> None:
    vector_store = FakeVectorStore(point_prefix="new-code-point")
    (
        service,
        metadata_service,
        permission_service,
        session_factory,
    ) = _build_services(tmp_path, vector_store=vector_store)
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)
    permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=7,
    )
    app_path = tmp_path / "repo" / "main" / ("a" * 40) / "app.py"
    app_path.write_text("def new():\n    return 'new'\n", encoding="utf-8")

    response = service.reindex_repository(repository_id)

    with session_factory() as session:
        repository = session.get(CodeRepositoryRecord, repository_id)
        chunks = session.scalars(select(CodeChunkRecord)).all()
        permission = session.scalars(select(CodeRepositoryPermissionRecord)).one()

    assert repository is not None
    assert repository.status == DocumentStatus.INDEXED.value
    assert [chunk.qdrant_point_id for chunk in chunks] == ["new-code-point-1"]
    assert permission.repository_id == repository_id
    assert permission.user_id == 7
    assert response.files == 1
    assert response.chunks == 1
    assert response.stored_vectors == 1
    assert response.replaced_vectors == 1
    assert vector_store.deleted_point_ids == ["old-code-point-1"]


def test_reindex_does_not_delete_reused_deterministic_point_ids(tmp_path) -> None:
    vector_store = FakeVectorStore(point_prefix="old-code-point")
    service, metadata_service, _permission_service, session_factory = _build_services(
        tmp_path,
        vector_store=vector_store,
    )
    repository_id = _create_repository(metadata_service, session_factory, tmp_path)

    response = service.reindex_repository(repository_id)

    assert response.replaced_vectors == 0
    assert vector_store.deleted_point_ids == []


def test_reindex_local_folder_preserves_source_acl_and_qdrant_consistency(
    tmp_path,
) -> None:
    vector_store = FakeVectorStore(point_prefix="new-code-point")
    (
        service,
        metadata_service,
        permission_service,
        session_factory,
    ) = _build_services(tmp_path, vector_store=vector_store)
    repository_id = _create_local_folder_repository(
        metadata_service,
        session_factory,
        tmp_path,
    )
    permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=7,
    )
    app_path = tmp_path / "local" / "LocalCode" / ("b" * 16) / "app.py"
    app_path.write_text("def new():\n    return 'new'\n", encoding="utf-8")

    first_response = service.reindex_repository(repository_id)
    second_response = service.reindex_repository(repository_id)

    with session_factory() as session:
        repositories = session.scalars(select(CodeRepositoryRecord)).all()
        repository = session.get(CodeRepositoryRecord, repository_id)
        chunks = session.scalars(select(CodeChunkRecord)).all()
        permission = session.scalars(select(CodeRepositoryPermissionRecord)).one()

    assert len(repositories) == 1
    assert repository is not None
    assert repository.source_type == CodeSourceType.LOCAL_FOLDER.value
    assert repository.repo_url is None
    assert repository.branch is None
    assert repository.commit_sha is None
    assert repository.source_fingerprint != "b" * 64
    assert repository.status == DocumentStatus.INDEXED.value
    assert permission.repository_id == repository_id
    assert permission.user_id == 7
    assert len({(chunk.repository_id, chunk.chunk_index) for chunk in chunks}) == len(chunks)
    assert first_response.replaced_vectors == 1
    assert second_response.replaced_vectors == 0
    assert vector_store.deleted_point_ids == ["old-code-point-1"]
