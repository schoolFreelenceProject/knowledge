from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    CodeSourceType,
    DocumentStatus,
    UserRecord,
)
from app.schemas.documents import EmbeddedChunk
from app.services.code_chunker import CodeChunkingConfig
from app.services.code_ingestion_service import CodeFolderUploadFile, CodeIngestionService
from app.services.code_metadata_service import CodeMetadataService
from app.services.code_parser import TreeSitterCodeParser
from app.services.code_repository_loader import (
    ClonedRepository,
    CodeFileDiscovery,
    GitRepositoryLoader,
)
from app.services.permission_service import PermissionService
from app.services.vector_store import StoredVectorBatch, VectorStoreError


class FakeRepositoryLoader:
    def __init__(self, repo_path: Path, already_present: bool = False) -> None:
        self.repo_path = repo_path
        self.already_present = already_present

    def clone_repository(self, repo_url: str, branch: str):
        return ClonedRepository(
            repo_url=repo_url,
            repo_name="repo",
            branch=branch,
            commit_sha="a" * 40,
            path=self.repo_path,
            storage_path="repo/main/aaaaaaaa",
            already_present=self.already_present,
        )

    def discover_code_files(self, repository_path, include_globs, exclude_globs):
        return self.discover_code_files_with_stats(
            repository_path,
            include_globs,
            exclude_globs,
        ).paths

    def discover_code_files_with_stats(
        self,
        repository_path,
        include_globs,
        exclude_globs,
        max_file_bytes=1_000_000,
    ):
        paths = []
        skip_reasons = {}
        for path in sorted(repository_path.iterdir()):
            if not path.is_file():
                continue
            if path.suffix in {".php", ".py"}:
                paths.append(path)
                continue

            skip_reasons["unsupported_extension"] = (
                skip_reasons.get("unsupported_extension", 0) + 1
            )

        return CodeFileDiscovery(
            paths=paths,
            skipped_files=sum(skip_reasons.values()),
            skip_reasons=skip_reasons,
        )


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
    collection_name = "company_documents"

    def __init__(self) -> None:
        self.deleted_point_ids: list[str] = []
        self.stored_point_ids: list[str] = []
        self.active_point_ids: set[str] = set()

    def store_embeddings(self, embedded_chunks):
        embedded_chunk_list = list(embedded_chunks)
        point_ids = [
            f"code-point-{chunk.metadata.chunk_index}"
            for chunk in embedded_chunk_list
        ]
        self.stored_point_ids.extend(point_ids)
        self.active_point_ids.update(point_ids)
        return StoredVectorBatch(
            collection_name=self.collection_name,
            stored_count=len(embedded_chunk_list),
            vector_size=3,
            point_ids=point_ids,
        )

    def delete_points(self, point_ids):
        self.deleted_point_ids.extend(point_ids)
        self.active_point_ids.difference_update(point_ids)


class FailingVectorStore(FakeVectorStore):
    def store_embeddings(self, embedded_chunks):
        raise VectorStoreError("simulated Qdrant failure")


def _build_services(tmp_path, already_present: bool = False):
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
        session.add(
            UserRecord(
                id=8,
                email="second@example.com",
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
    vector_store = FakeVectorStore()
    service = CodeIngestionService(
        repository_loader=FakeRepositoryLoader(
            repo_path=repo_path,
            already_present=already_present,
        ),
        parser=TreeSitterCodeParser(),
        chunk_config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        metadata_service=metadata_service,
        permission_service=permission_service,
    )
    return service, metadata_service, permission_service, vector_store, session_factory


def _build_folder_services(tmp_path, vector_store=None):
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
        session.add_all(
            [
                UserRecord(
                    id=7,
                    email="uploader@example.com",
                    password_hash="$argon2id$hash",
                ),
                UserRecord(
                    id=8,
                    email="second@example.com",
                    password_hash="$argon2id$hash",
                ),
            ]
        )
        session.commit()

    repositories_dir = tmp_path / "repositories"
    vector_store = vector_store or FakeVectorStore()
    service = CodeIngestionService(
        repository_loader=GitRepositoryLoader(repositories_dir=repositories_dir),
        parser=TreeSitterCodeParser(),
        chunk_config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        metadata_service=metadata_service,
        permission_service=permission_service,
    )
    return service, metadata_service, permission_service, vector_store, session_factory


def test_code_ingestion_persists_metadata_and_grants_uploader_access(tmp_path) -> None:
    (
        service,
        _metadata_service,
        _permission_service,
        vector_store,
        session_factory,
    ) = _build_services(tmp_path)

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
        chunks = session.scalars(select(CodeChunkRecord)).all()

    assert response.repository_id == repository.id
    assert response.files == 1
    assert response.chunks >= 1
    assert response.stored_vectors == response.chunks
    assert response.already_indexed is False
    assert response.recovered is False
    assert permission.repository_id == repository.id
    assert permission.user_id == 7
    assert vector_store.active_point_ids == {chunk.qdrant_point_id for chunk in chunks}


def test_code_ingestion_returns_existing_revision_on_repeat_ingest(tmp_path) -> None:
    (
        service,
        _metadata_service,
        _permission_service,
        vector_store,
        session_factory,
    ) = _build_services(tmp_path, already_present=True)

    first_response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )
    second_response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    with session_factory() as session:
        repositories = session.scalars(select(CodeRepositoryRecord)).all()
        permissions = session.scalars(select(CodeRepositoryPermissionRecord)).all()

    assert len(repositories) == 1
    assert len(permissions) == 1
    assert second_response.repository_id == first_response.repository_id
    assert second_response.already_indexed is True
    assert second_response.message == "This revision is already indexed."
    assert second_response.stored_vectors == 0
    assert vector_store.stored_point_ids == ["code-point-1"]


def test_existing_successful_revision_grants_acl_and_becomes_list_visible(
    tmp_path,
) -> None:
    (
        service,
        metadata_service,
        permission_service,
        _vector_store,
        _session_factory,
    ) = _build_services(tmp_path, already_present=True)
    first_response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    second_response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=8,
    )
    visible_ids = permission_service.list_accessible_code_repository_ids(8)
    visible_repositories = metadata_service.list_repositories(
        repository_ids=visible_ids,
    )

    assert second_response.repository_id == first_response.repository_id
    assert second_response.already_indexed is True
    assert visible_ids == [first_response.repository_id]
    assert [repository.id for repository in visible_repositories] == [
        first_response.repository_id
    ]


def test_existing_failed_revision_is_recovered_without_duplicate_metadata(
    tmp_path,
) -> None:
    (
        service,
        _metadata_service,
        _permission_service,
        vector_store,
        session_factory,
    ) = _build_services(tmp_path, already_present=True)
    with session_factory() as session:
        failed_repository = CodeRepositoryRecord(
            repo_url="file:///repo",
            repo_name="repo",
            branch="main",
            commit_sha="a" * 40,
            storage_path="repo/main/aaaaaaaa",
            status=DocumentStatus.FAILED.value,
        )
        session.add(failed_repository)
        session.flush()
        stale_file = CodeFileRecord(
            repository_id=failed_repository.id,
            file_path="app.py",
            language="python",
            file_hash="b" * 64,
            size_bytes=28,
        )
        session.add(stale_file)
        session.flush()
        session.add(
            CodeChunkRecord(
                repository_id=failed_repository.id,
                code_file_id=stale_file.id,
                qdrant_point_id="old-code-point-1",
                chunk_index=1,
                start_line=1,
                end_line=2,
                start_char=0,
                end_char=28,
            )
        )
        session.commit()
        repository_id = failed_repository.id
    vector_store.active_point_ids.add("old-code-point-1")

    response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    with session_factory() as session:
        repositories = session.scalars(select(CodeRepositoryRecord)).all()
        repository = session.get(CodeRepositoryRecord, repository_id)
        chunks = session.scalars(select(CodeChunkRecord)).all()
        permission = session.scalars(select(CodeRepositoryPermissionRecord)).one()
        chunk_positions = {
            (chunk.repository_id, chunk.code_file_id, chunk.chunk_index)
            for chunk in chunks
        }

    assert len(repositories) == 1
    assert response.repository_id == repository_id
    assert response.recovered is True
    assert repository is not None
    assert repository.status == DocumentStatus.INDEXED.value
    assert len(chunks) == response.chunks
    assert len(chunk_positions) == len(chunks)
    assert permission.repository_id == repository_id
    assert "old-code-point-1" in vector_store.deleted_point_ids
    assert vector_store.active_point_ids == {chunk.qdrant_point_id for chunk in chunks}


def test_orphaned_repository_clone_is_indexed_and_visible(tmp_path) -> None:
    (
        service,
        metadata_service,
        permission_service,
        _vector_store,
        session_factory,
    ) = _build_services(tmp_path, already_present=True)

    response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    visible_ids = permission_service.list_accessible_code_repository_ids(7)
    visible_repositories = metadata_service.list_repositories(
        repository_ids=visible_ids,
    )
    with session_factory() as session:
        repositories = session.scalars(select(CodeRepositoryRecord)).all()

    assert len(repositories) == 1
    assert response.repository_id in visible_ids
    assert [repository.id for repository in visible_repositories] == [
        response.repository_id
    ]


def test_code_ingestion_indexes_php_files_and_records_skips(tmp_path) -> None:
    (
        service,
        _metadata_service,
        _permission_service,
        _vector_store,
        session_factory,
    ) = _build_services(tmp_path)
    repo_path = tmp_path / "repo"
    (repo_path / "app.py").unlink()
    (repo_path / "Controller.php").write_text(
        "<?php\nclass Controller {\n    public function index() { return 'ok'; }\n}\n",
        encoding="utf-8",
    )
    (repo_path / "bad.py").write_bytes(b"\xff\xfe\x00")
    (repo_path / "logo.png").write_bytes(b"not source")

    response = service.ingest_repository(
        repo_url="file:///repo",
        branch="main",
        include_globs=["**/*.php", "**/*.py"],
        exclude_globs=[],
        uploader_user_id=7,
    )

    with session_factory() as session:
        repository = session.get(CodeRepositoryRecord, response.repository_id)

    assert repository is not None
    assert repository.status == DocumentStatus.INDEXED.value
    assert response.files == 1
    assert response.chunks == 1
    assert response.skipped_files == 2
    assert response.skip_reasons == {
        "binary_file": 1,
        "unsupported_extension": 1,
    }


def test_code_folder_ingestion_indexes_nested_mixed_language_paths_and_acl(
    tmp_path,
) -> None:
    (
        service,
        metadata_service,
        permission_service,
        vector_store,
        session_factory,
    ) = _build_folder_services(tmp_path)

    response = service.ingest_uploaded_folder(
        folder_name="LocalCode",
        files=[
            CodeFolderUploadFile(
                relative_path="src/lio_node.cpp",
                content=b"#include <iostream>\nint main() { return 0; }\n",
            ),
            CodeFolderUploadFile(
                relative_path="include/common.hpp",
                content=b"#pragma once\nstruct Config { int value; };\n",
            ),
            CodeFolderUploadFile(
                relative_path="launch/lio_launch.py",
                content=b"def launch():\n    return 'ok'\n",
            ),
        ],
        uploader_user_id=7,
    )

    visible_ids = permission_service.list_accessible_code_repository_ids(7)
    visible_repositories = metadata_service.list_repositories(repository_ids=visible_ids)
    with session_factory() as session:
        repository = session.get(CodeRepositoryRecord, response.repository_id)
        files = session.scalars(select(CodeFileRecord)).all()
        chunks = session.scalars(select(CodeChunkRecord)).all()
        permission = session.scalars(select(CodeRepositoryPermissionRecord)).one()

    assert response.source_type == CodeSourceType.LOCAL_FOLDER.value
    assert response.repo_url is None
    assert response.branch is None
    assert response.commit_sha is None
    assert response.source_fingerprint is not None
    assert response.files == 3
    assert repository is not None
    assert repository.source_type == CodeSourceType.LOCAL_FOLDER.value
    assert repository.source_fingerprint == response.source_fingerprint
    assert repository.storage_path.startswith("local/LocalCode/")
    assert {file.file_path for file in files} == {
        "include/common.hpp",
        "launch/lio_launch.py",
        "src/lio_node.cpp",
    }
    assert {file.language for file in files} == {"cpp", "python"}
    assert permission.repository_id == repository.id
    assert permission.user_id == 7
    assert visible_ids == [repository.id]
    assert [item.id for item in visible_repositories] == [repository.id]
    assert len({(chunk.repository_id, chunk.chunk_index) for chunk in chunks}) == len(chunks)
    assert vector_store.active_point_ids == {chunk.qdrant_point_id for chunk in chunks}


def test_code_folder_ingestion_skips_unsupported_binary_and_vendor_files(
    tmp_path,
) -> None:
    service, *_ = _build_folder_services(tmp_path)

    response = service.ingest_uploaded_folder(
        folder_name="/Users/uploader/LocalCode",
        files=[
            CodeFolderUploadFile(
                relative_path="src/app.py",
                content=b"def app():\n    return 'ok'\n",
            ),
            CodeFolderUploadFile(
                relative_path="node_modules/pkg/index.js",
                content=b"console.log('vendor')\n",
            ),
            CodeFolderUploadFile(
                relative_path="dist/bundle.js",
                content=b"console.log('generated')\n",
            ),
            CodeFolderUploadFile(
                relative_path="README.md",
                content=b"# Project\n",
            ),
            CodeFolderUploadFile(
                relative_path="src/bad.py",
                content=b"\xff\xfe\x00",
            ),
        ],
        uploader_user_id=7,
    )

    assert response.repo_name == "LocalCode"
    assert response.files == 1
    assert response.skipped_files == 4
    assert response.skip_reasons == {
        "binary_file": 1,
        "excluded_path": 2,
        "unsupported_extension": 1,
    }


def test_code_folder_duplicate_upload_returns_existing_and_grants_acl(
    tmp_path,
) -> None:
    (
        service,
        _metadata_service,
        _permission_service,
        vector_store,
        session_factory,
    ) = _build_folder_services(tmp_path)
    files = [
        CodeFolderUploadFile(
            relative_path="src/app.py",
            content=b"def app():\n    return 'ok'\n",
        )
    ]

    first_response = service.ingest_uploaded_folder(
        folder_name="LocalCode",
        files=files,
        uploader_user_id=7,
    )
    second_response = service.ingest_uploaded_folder(
        folder_name="LocalCode",
        files=files,
        uploader_user_id=8,
    )

    with session_factory() as session:
        repositories = session.scalars(select(CodeRepositoryRecord)).all()
        permissions = session.scalars(select(CodeRepositoryPermissionRecord)).all()

    assert len(repositories) == 1
    assert len(permissions) == 2
    assert {permission.user_id for permission in permissions} == {7, 8}
    assert second_response.repository_id == first_response.repository_id
    assert second_response.already_indexed is True
    assert second_response.message == "This code folder is already indexed."
    assert second_response.stored_vectors == 0
    assert len(vector_store.stored_point_ids) == first_response.chunks


def test_code_folder_ingestion_rejects_path_traversal_without_escaping_storage(
    tmp_path,
) -> None:
    service, *_services, session_factory = _build_folder_services(tmp_path)

    response = service.ingest_uploaded_folder(
        folder_name="LocalCode",
        files=[
            CodeFolderUploadFile(
                relative_path="../escape.py",
                content=b"print('escape')\n",
            ),
            CodeFolderUploadFile(
                relative_path="src/app.py",
                content=b"def app():\n    return 'ok'\n",
            ),
        ],
        uploader_user_id=7,
    )

    with session_factory() as session:
        files = session.scalars(select(CodeFileRecord)).all()

    assert response.files == 1
    assert response.skip_reasons == {"unsafe_path": 1}
    assert {file.file_path for file in files} == {"src/app.py"}
    assert not (tmp_path / "repositories" / "_tmp" / "escape.py").exists()
    assert not (tmp_path / "repositories" / "escape.py").exists()


def test_code_folder_ingestion_cleans_source_and_metadata_on_vector_failure(
    tmp_path,
) -> None:
    vector_store = FailingVectorStore()
    service, *_services, session_factory = _build_folder_services(
        tmp_path,
        vector_store=vector_store,
    )

    try:
        service.ingest_uploaded_folder(
            folder_name="LocalCode",
            files=[
                CodeFolderUploadFile(
                    relative_path="src/app.py",
                    content=b"def app():\n    return 'ok'\n",
                )
            ],
            uploader_user_id=7,
        )
    except VectorStoreError:
        pass
    else:
        raise AssertionError("expected vector storage failure")

    with session_factory() as session:
        assert session.scalars(select(CodeRepositoryRecord)).all() == []
        assert session.scalars(select(CodeFileRecord)).all() == []
        assert session.scalars(select(CodeChunkRecord)).all() == []

    assert vector_store.active_point_ids == set()
    assert not (tmp_path / "repositories" / "local" / "LocalCode").exists()
