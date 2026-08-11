from __future__ import annotations

import shutil
import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.db.models import CodeSourceType
from app.schemas.code import (
    CodeChunkDetail,
    CodeFileDetail,
    CodeRepositoryDetail,
    CodeRepositorySummary,
    DeleteCodeRepositoryResponse,
    ReindexCodeRepositoryResponse,
)
from app.services.code_chunker import CodeChunkingConfig, chunk_code_files
from app.services.code_metadata_service import (
    CodeMetadataPersistenceError,
    CodeMetadataService,
    CodeRepositoryMetadataNotFoundError,
    StoredCodeRepositoryMetadata,
)
from app.services.code_parser import (
    BinaryCodeFileError,
    CodeParserError,
    ParsedCodeFile,
    TreeSitterCodeParser,
)
from app.services.code_repository_loader import GitRepositoryLoader
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.vector_store import QdrantVectorStore, StoredVectorBatch, VectorStoreError


class CodeRepositoryManagementError(RuntimeError):
    """Raised when a code repository management operation cannot be completed."""


class CodeRepositoryStorageError(CodeRepositoryManagementError):
    """Raised when stored repository files cannot be read or resolved."""


@dataclass(frozen=True)
class ParsedRepositoryFiles:
    files: list[ParsedCodeFile]
    skipped_files: int
    skip_reasons: dict[str, int]
    source_fingerprint: str | None = None


class CodeRepositoryManagementService:
    def __init__(
        self,
        repositories_dir: str | Path,
        repository_loader: GitRepositoryLoader,
        parser: TreeSitterCodeParser,
        chunk_config: CodeChunkingConfig,
        embedding_service: SentenceTransformersEmbeddingService,
        vector_store: QdrantVectorStore,
        metadata_service: CodeMetadataService,
    ) -> None:
        self.repositories_dir = Path(repositories_dir)
        self.repository_loader = repository_loader
        self.parser = parser
        self.chunk_config = chunk_config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.metadata_service = metadata_service

    def list_repositories(
        self,
        repository_ids: list[int] | None = None,
    ) -> list[CodeRepositorySummary]:
        return [
            _to_repository_summary(repository)
            for repository in self.metadata_service.list_repositories(
                repository_ids=repository_ids,
            )
        ]

    def get_repository(self, repository_id: int) -> CodeRepositoryDetail:
        return _to_repository_detail(
            self.metadata_service.get_repository(repository_id)
        )

    def delete_repository(
        self,
        repository_id: int,
    ) -> DeleteCodeRepositoryResponse:
        repository = self.metadata_service.get_repository(repository_id)
        point_ids = _repository_point_ids(repository)
        repository_path = self._resolve_storage_path(
            repository.storage_path,
            must_exist=False,
        )

        self.vector_store.delete_points(point_ids)
        self.metadata_service.delete_repository(repository_id)

        deleted_files, cleanup_warning = _delete_repository_files(repository_path)

        return DeleteCodeRepositoryResponse(
            repository_id=repository.id,
            deleted_vectors=len(point_ids),
            deleted_metadata=True,
            deleted_files=deleted_files,
            cleanup_warning=cleanup_warning,
        )

    def reindex_repository(
        self,
        repository_id: int,
    ) -> ReindexCodeRepositoryResponse:
        repository = self.metadata_service.get_repository(repository_id)
        old_point_ids = _repository_point_ids(repository)
        repository_path = self._resolve_storage_path(
            repository.storage_path,
            must_exist=True,
        )

        new_batch: StoredVectorBatch | None = None
        try:
            parsed_repository = self._parse_repository(
                repository=repository,
                repository_path=repository_path,
            )
            parsed_files = parsed_repository.files
            if not parsed_files:
                raise CodeRepositoryManagementError(
                    "No supported code files were found in the stored repository."
                )

            chunks = chunk_code_files(parsed_files, config=self.chunk_config)
            if not chunks:
                raise CodeRepositoryManagementError(
                    "No code chunks were generated from the stored repository."
                )

            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            new_batch = self.vector_store.store_embeddings(embedded_chunks)
            persisted = self.metadata_service.replace_repository_contents(
                repository_id=repository_id,
                parsed_files=parsed_files,
                chunks=chunks,
                stored_batch=new_batch,
                source_fingerprint=parsed_repository.source_fingerprint,
            )
        except CodeMetadataPersistenceError:
            if new_batch is not None:
                _cleanup_new_vectors_best_effort(
                    vector_store=self.vector_store,
                    point_ids=new_batch.point_ids,
                )
            _mark_failed_best_effort(self.metadata_service, repository_id)
            raise
        except Exception:
            _mark_failed_best_effort(self.metadata_service, repository_id)
            raise

        new_point_ids = set(new_batch.point_ids)
        stale_point_ids = [
            point_id
            for point_id in old_point_ids
            if point_id not in new_point_ids
        ]
        cleanup_warning = _cleanup_old_vectors_after_reindex(
            vector_store=self.vector_store,
            point_ids=stale_point_ids,
        )

        return ReindexCodeRepositoryResponse(
            repository_id=repository_id,
            status=persisted.status,
            files=persisted.saved_files,
            chunks=persisted.saved_chunks,
            stored_vectors=new_batch.stored_count,
            replaced_vectors=len(stale_point_ids),
            skipped_files=parsed_repository.skipped_files,
            skip_reasons=parsed_repository.skip_reasons,
            cleanup_warning=cleanup_warning,
        )

    def _parse_repository(
        self,
        repository: StoredCodeRepositoryMetadata,
        repository_path: Path,
    ) -> ParsedRepositoryFiles:
        discovery = self.repository_loader.discover_code_files_with_stats(
            repository_path=repository_path,
            include_globs=None,
            exclude_globs=None,
        )
        source_fingerprint = (
            _build_source_fingerprint(
                repository_path=repository_path,
                paths=discovery.paths,
            )
            if repository.source_type == CodeSourceType.LOCAL_FOLDER.value
            else None
        )
        source_path_prefix = _source_path_prefix(
            repository=repository,
            source_fingerprint=source_fingerprint,
        )
        parsed_files: list[ParsedCodeFile] = []
        skip_reasons = dict(discovery.skip_reasons)
        for path in discovery.paths:
            try:
                parsed_files.append(
                    self.parser.parse_file(
                        file_path=path,
                        repository_root=repository_path,
                        repo_url=repository.repo_url,
                        repo_name=repository.repo_name,
                        branch=repository.branch,
                        commit_sha=repository.commit_sha,
                        source_type=repository.source_type,
                        source_path_prefix=source_path_prefix,
                    )
                )
            except BinaryCodeFileError:
                _count_skip(skip_reasons, "binary_file")
            except CodeParserError:
                _count_skip(skip_reasons, "parse_error")

        return ParsedRepositoryFiles(
            files=parsed_files,
            skipped_files=sum(skip_reasons.values()),
            skip_reasons=skip_reasons,
            source_fingerprint=source_fingerprint,
        )

    def _resolve_storage_path(self, storage_path: str, must_exist: bool) -> Path:
        base_dir = self.repositories_dir.resolve()
        candidate = (base_dir / storage_path).resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError as exc:
            raise CodeRepositoryStorageError(
                f"Stored repository path escapes the repositories directory: {storage_path}"
            ) from exc

        if must_exist and not candidate.is_dir():
            raise CodeRepositoryStorageError(
                f"Stored repository directory was not found: {storage_path}"
            )

        return candidate


def _count_skip(skip_reasons: dict[str, int], reason: str) -> None:
    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1


def _to_repository_summary(
    repository: StoredCodeRepositoryMetadata,
) -> CodeRepositorySummary:
    return CodeRepositorySummary(
        id=repository.id,
        repo_name=repository.repo_name,
        source_type=repository.source_type,
        repo_url=repository.repo_url,
        branch=repository.branch,
        commit_sha=repository.commit_sha,
        source_fingerprint=repository.source_fingerprint,
        storage_path=repository.storage_path,
        status=repository.status,
        created_at=repository.created_at,
        updated_at=repository.updated_at,
        file_count=len(repository.files),
        chunk_count=len(repository.chunks),
    )


def _to_repository_detail(
    repository: StoredCodeRepositoryMetadata,
) -> CodeRepositoryDetail:
    summary = _to_repository_summary(repository)
    return CodeRepositoryDetail(
        **summary.model_dump(),
        files=[
            CodeFileDetail(
                id=file.id,
                file_path=file.file_path,
                language=file.language,
                file_hash=file.file_hash,
                size_bytes=file.size_bytes,
                created_at=file.created_at,
                chunk_count=file.chunk_count,
            )
            for file in repository.files
        ],
        chunks=[
            CodeChunkDetail(
                id=chunk.id,
                code_file_id=chunk.code_file_id,
                qdrant_point_id=chunk.qdrant_point_id,
                chunk_index=chunk.chunk_index,
                symbol_name=chunk.symbol_name,
                symbol_kind=chunk.symbol_kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                created_at=chunk.created_at,
            )
            for chunk in repository.chunks
        ],
    )


def _repository_point_ids(repository: StoredCodeRepositoryMetadata) -> list[str]:
    return [chunk.qdrant_point_id for chunk in repository.chunks]


def _build_source_fingerprint(
    repository_path: Path,
    paths: list[Path],
) -> str | None:
    if not paths:
        return None

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(repository_path).as_posix()):
        relative_path = path.relative_to(repository_path).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")

    return digest.hexdigest()


def _source_path_prefix(
    repository: StoredCodeRepositoryMetadata,
    source_fingerprint: str | None,
) -> str:
    if repository.source_type == CodeSourceType.LOCAL_FOLDER.value:
        fingerprint = source_fingerprint or repository.source_fingerprint or "unknown"
        return f"{repository.repo_name}@local-{fingerprint[:12]}"

    return f"{repository.repo_name}@{repository.commit_sha}"


def _delete_repository_files(repository_path: Path) -> tuple[bool, str | None]:
    try:
        shutil.rmtree(repository_path)
        return True, None
    except FileNotFoundError:
        return False, f"Stored repository directory was already missing: {repository_path}"
    except OSError as exc:
        return (
            False,
            f"Failed to delete stored repository directory '{repository_path}': {exc}",
        )


def _cleanup_old_vectors_after_reindex(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> str | None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError as exc:
        return f"Failed to delete old Qdrant vectors after reindex: {exc}"

    return None


def _cleanup_new_vectors_best_effort(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError:
        pass


def _mark_failed_best_effort(
    metadata_service: CodeMetadataService,
    repository_id: int,
) -> None:
    try:
        metadata_service.mark_repository_failed(repository_id)
    except (CodeRepositoryMetadataNotFoundError, CodeMetadataPersistenceError):
        pass
