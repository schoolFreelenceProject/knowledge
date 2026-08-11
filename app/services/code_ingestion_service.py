from __future__ import annotations

import hashlib
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.db.models import CodeSourceType, DocumentStatus
from app.schemas.code import CodeIngestResponse
from app.services.code_chunker import CodeChunkingConfig, chunk_code_files
from app.services.code_metadata_service import (
    CodeMetadataPersistenceError,
    CodeMetadataService,
    CodeRepositoryConflictError,
    StoredCodeRepositoryMetadata,
)
from app.services.code_parser import (
    BinaryCodeFileError,
    CodeParserError,
    ParsedCodeFile,
    TreeSitterCodeParser,
)
from app.services.code_repository_loader import (
    ClonedRepository,
    CodeRepositoryAlreadyIndexedError,
    CodeRepositoryLoaderError,
    GitRepositoryLoader,
    cleanup_repository,
)
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.permission_service import PermissionService, PermissionServiceError
from app.services.vector_store import QdrantVectorStore, StoredVectorBatch, VectorStoreError


logger = logging.getLogger(__name__)


LOCAL_CODE_UPLOAD_ROOT = "local"
MAX_CODE_UPLOAD_FILE_BYTES = 1_000_000
MAX_LOCAL_SOURCE_NAME_LENGTH = 120
MAX_LOCAL_RELATIVE_PATH_LENGTH = 1024
HIDDEN_OR_SYSTEM_FILENAMES = {".ds_store", "desktop.ini", "thumbs.db"}
LOCAL_EXCLUDED_DIR_NAMES = {
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


class CodeIngestionServiceError(RuntimeError):
    """Raised when a code repository cannot be ingested."""


class CodeRepositoryIngestionConflictError(CodeIngestionServiceError):
    """Raised when a repository revision is already indexed."""


@dataclass(frozen=True)
class ParsedRepositoryFiles:
    files: list[ParsedCodeFile]
    skipped_files: int
    skip_reasons: dict[str, int]
    source_fingerprint: str | None = None


@dataclass(frozen=True)
class CodeFolderUploadFile:
    relative_path: str
    content: bytes


@dataclass(frozen=True)
class PreparedCodeSource:
    source_type: str
    repo_name: str
    repo_url: str | None
    branch: str | None
    commit_sha: str | None
    source_fingerprint: str | None
    path: Path
    storage_path: str
    cleanup_on_failure: bool


class CodeIngestionService:
    def __init__(
        self,
        repository_loader: GitRepositoryLoader,
        parser: TreeSitterCodeParser,
        chunk_config: CodeChunkingConfig,
        embedding_service: SentenceTransformersEmbeddingService,
        vector_store: QdrantVectorStore,
        metadata_service: CodeMetadataService,
        permission_service: PermissionService,
    ) -> None:
        self.repository_loader = repository_loader
        self.parser = parser
        self.chunk_config = chunk_config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.metadata_service = metadata_service
        self.permission_service = permission_service

    def ingest_repository(
        self,
        repo_url: str,
        branch: str,
        include_globs: list[str] | None,
        exclude_globs: list[str] | None,
        uploader_user_id: int,
    ) -> CodeIngestResponse:
        source: PreparedCodeSource | None = None
        try:
            cloned_repository = self.repository_loader.clone_repository(
                repo_url=repo_url,
                branch=branch,
            )
            source = _source_from_cloned_repository(cloned_repository)
            existing_repository = self.metadata_service.get_repository_revision(
                repo_url=cloned_repository.repo_url,
                branch=cloned_repository.branch,
                commit_sha=cloned_repository.commit_sha,
            )
            if existing_repository is not None:
                _grant_existing_source_access(
                    permission_service=self.permission_service,
                    repository_id=existing_repository.id,
                    user_id=uploader_user_id,
                )
                if _is_complete_indexed_repository(existing_repository):
                    cleanup_repository(cloned_repository)
                    return _existing_repository_response(
                        repository=existing_repository,
                        collection_name=_collection_name(self.vector_store),
                    )

            parsed_repository = self._parse_source(
                source=source,
                include_globs=include_globs,
                exclude_globs=exclude_globs,
            )
            return self._index_source(
                source=source,
                parsed_repository=parsed_repository,
                uploader_user_id=uploader_user_id,
                existing_repository=existing_repository,
            )
        except CodeRepositoryAlreadyIndexedError as exc:
            raise CodeRepositoryIngestionConflictError(str(exc)) from exc
        except (CodeRepositoryLoaderError, CodeParserError, CodeIngestionServiceError):
            if source is not None and source.cleanup_on_failure:
                _delete_source_directory_best_effort(source.path)
            raise
        except Exception:
            if source is not None and source.cleanup_on_failure:
                _delete_source_directory_best_effort(source.path)
            raise

    def ingest_uploaded_folder(
        self,
        folder_name: str,
        files: list[CodeFolderUploadFile],
        uploader_user_id: int,
    ) -> CodeIngestResponse:
        safe_folder_name = _safe_source_name(folder_name)
        source: PreparedCodeSource | None = None
        temp_path = (
            self.repository_loader.repositories_dir
            / "_tmp"
            / "local-folders"
            / f"{safe_folder_name}-{uuid4().hex}"
        )
        temp_path.mkdir(parents=True, exist_ok=True)

        try:
            initial_skip_reasons = _write_uploaded_folder_files(
                root_path=temp_path,
                files=files,
            )
            discovery = self.repository_loader.discover_code_files_with_stats(
                repository_path=temp_path,
                include_globs=None,
                exclude_globs=None,
                max_file_bytes=MAX_CODE_UPLOAD_FILE_BYTES,
            )
            source_fingerprint = _build_source_fingerprint(
                repository_path=temp_path,
                paths=discovery.paths,
            )
            if source_fingerprint is None:
                raise CodeIngestionServiceError(
                    "No supported code files were found in the uploaded folder."
                )

            existing_repository = self.metadata_service.get_local_folder_source(
                repo_name=safe_folder_name,
                source_fingerprint=source_fingerprint,
            )
            if existing_repository is not None:
                _grant_existing_source_access(
                    permission_service=self.permission_service,
                    repository_id=existing_repository.id,
                    user_id=uploader_user_id,
                )
                if _is_complete_indexed_repository(existing_repository):
                    shutil.rmtree(temp_path, ignore_errors=True)
                    return _existing_repository_response(
                        repository=existing_repository,
                        collection_name=_collection_name(self.vector_store),
                    )

            final_path, storage_path, cleanup_on_failure = _install_local_source(
                temp_path=temp_path,
                repositories_dir=self.repository_loader.repositories_dir,
                repo_name=safe_folder_name,
                source_fingerprint=source_fingerprint,
                existing_repository=existing_repository,
            )
            source = PreparedCodeSource(
                source_type=CodeSourceType.LOCAL_FOLDER.value,
                repo_name=safe_folder_name,
                repo_url=None,
                branch=None,
                commit_sha=None,
                source_fingerprint=source_fingerprint,
                path=final_path,
                storage_path=storage_path,
                cleanup_on_failure=cleanup_on_failure,
            )
            parsed_repository = self._parse_source(
                source=source,
                include_globs=None,
                exclude_globs=None,
                initial_skip_reasons=initial_skip_reasons,
            )
            return self._index_source(
                source=source,
                parsed_repository=parsed_repository,
                uploader_user_id=uploader_user_id,
                existing_repository=existing_repository,
            )
        except PermissionServiceError:
            _cleanup_local_upload_after_failure(source=source, temp_path=temp_path)
            raise
        except Exception:
            _cleanup_local_upload_after_failure(source=source, temp_path=temp_path)
            raise

    def _parse_source(
        self,
        source: PreparedCodeSource,
        include_globs: list[str] | None,
        exclude_globs: list[str] | None,
        initial_skip_reasons: dict[str, int] | None = None,
    ) -> ParsedRepositoryFiles:
        discovery = self.repository_loader.discover_code_files_with_stats(
            repository_path=source.path,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_file_bytes=MAX_CODE_UPLOAD_FILE_BYTES,
        )
        source_fingerprint = (
            _build_source_fingerprint(
                repository_path=source.path,
                paths=discovery.paths,
            )
            if source.source_type == CodeSourceType.LOCAL_FOLDER.value
            else source.source_fingerprint
        )
        source_path_prefix = _source_path_prefix(
            source=source,
            source_fingerprint=source_fingerprint,
        )
        parsed_files: list[ParsedCodeFile] = []
        skip_reasons = _merge_skip_reasons(
            initial_skip_reasons or {},
            discovery.skip_reasons,
        )
        for path in discovery.paths:
            try:
                parsed_files.append(
                    self.parser.parse_file(
                        file_path=path,
                        repository_root=source.path,
                        repo_url=source.repo_url,
                        repo_name=source.repo_name,
                        branch=source.branch,
                        commit_sha=source.commit_sha,
                        source_type=source.source_type,
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

    def _index_source(
        self,
        source: PreparedCodeSource,
        parsed_repository: ParsedRepositoryFiles,
        uploader_user_id: int,
        existing_repository: StoredCodeRepositoryMetadata | None,
    ) -> CodeIngestResponse:
        parsed_files = parsed_repository.files
        if not parsed_files:
            raise CodeIngestionServiceError(
                "No supported code files were found in the source."
            )

        stored_batch: StoredVectorBatch | None = None
        repository_id: int | None = None
        old_point_ids = _repository_point_ids(existing_repository)
        old_point_id_set = set(old_point_ids)
        try:
            chunks = chunk_code_files(parsed_files, config=self.chunk_config)
            if not chunks:
                raise CodeIngestionServiceError(
                    "No code chunks were generated from the source."
                )

            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            stored_batch = self.vector_store.store_embeddings(embedded_chunks)
            if existing_repository is not None:
                persisted = self.metadata_service.replace_repository_contents(
                    repository_id=existing_repository.id,
                    parsed_files=parsed_files,
                    chunks=chunks,
                    stored_batch=stored_batch,
                    source_fingerprint=parsed_repository.source_fingerprint,
                )
                _cleanup_old_vectors_after_repository_recovery(
                    vector_store=self.vector_store,
                    point_ids=[
                        point_id
                        for point_id in old_point_ids
                        if point_id not in set(stored_batch.point_ids)
                    ],
                )
                return _source_response(
                    source=source,
                    repository_id=existing_repository.id,
                    status=persisted.status,
                    files=persisted.saved_files,
                    chunks=len(chunks),
                    embeddings=len(embedded_chunks),
                    stored_batch=stored_batch,
                    saved_chunks=persisted.saved_chunks,
                    skipped_files=parsed_repository.skipped_files,
                    skip_reasons=parsed_repository.skip_reasons,
                    recovered=True,
                    message=_recovered_message(source.source_type),
                )

            persisted = self.metadata_service.save_repository_metadata(
                parsed_files=parsed_files,
                chunks=chunks,
                stored_batch=stored_batch,
                repo_url=source.repo_url,
                repo_name=source.repo_name,
                branch=source.branch,
                commit_sha=source.commit_sha,
                storage_path=source.storage_path,
                source_type=source.source_type,
                source_fingerprint=parsed_repository.source_fingerprint,
            )
            repository_id = persisted.repository_id

            self.permission_service.grant_code_repository_access(
                repository_id=repository_id,
                user_id=uploader_user_id,
            )

            return _source_response(
                source=source,
                repository_id=repository_id,
                status=persisted.status,
                files=persisted.saved_files,
                chunks=len(chunks),
                embeddings=len(embedded_chunks),
                stored_batch=stored_batch,
                saved_chunks=persisted.saved_chunks,
                skipped_files=parsed_repository.skipped_files,
                skip_reasons=parsed_repository.skip_reasons,
                message=_indexed_message(source.source_type),
            )
        except CodeRepositoryConflictError as exc:
            _cleanup_source_state(
                source=source,
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                metadata_service=self.metadata_service,
                repository_id=repository_id,
                delete_source=source.cleanup_on_failure,
            )
            raise CodeRepositoryIngestionConflictError(str(exc)) from exc
        except PermissionServiceError as exc:
            cleanup_error = _cleanup_source_state(
                source=source,
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                metadata_service=self.metadata_service,
                repository_id=repository_id,
                delete_source=source.cleanup_on_failure,
            )
            detail = f"Failed to grant uploader code source access: {exc}"
            if cleanup_error:
                detail = f"{detail}. Cleanup also failed: {cleanup_error}"
            raise CodeMetadataPersistenceError(detail) from exc
        except CodeMetadataPersistenceError:
            if stored_batch is not None:
                _cleanup_new_vectors_best_effort(
                    vector_store=self.vector_store,
                    point_ids=[
                        point_id
                        for point_id in stored_batch.point_ids
                        if point_id not in old_point_id_set
                    ],
                )
            if existing_repository is None:
                _cleanup_source_state(
                    source=source,
                    vector_store=self.vector_store,
                    stored_batch=None,
                    metadata_service=self.metadata_service,
                    repository_id=repository_id,
                    delete_source=source.cleanup_on_failure,
                )
            raise


def _source_from_cloned_repository(
    cloned_repository: ClonedRepository,
) -> PreparedCodeSource:
    return PreparedCodeSource(
        source_type=CodeSourceType.GIT_REPOSITORY.value,
        repo_name=cloned_repository.repo_name,
        repo_url=cloned_repository.repo_url,
        branch=cloned_repository.branch,
        commit_sha=cloned_repository.commit_sha,
        source_fingerprint=None,
        path=cloned_repository.path,
        storage_path=cloned_repository.storage_path,
        cleanup_on_failure=not cloned_repository.already_present,
    )


def _write_uploaded_folder_files(
    root_path: Path,
    files: list[CodeFolderUploadFile],
) -> dict[str, int]:
    if not files:
        raise CodeIngestionServiceError("Uploaded code folder cannot be empty.")

    skip_reasons: dict[str, int] = {}
    seen_paths: set[str] = set()
    root = root_path.resolve()
    for upload in files:
        try:
            safe_relative_path = _safe_relative_path(upload.relative_path)
        except CodeIngestionServiceError:
            _count_skip(skip_reasons, "unsafe_path")
            continue

        skip_reason = _local_upload_skip_reason(
            raw_relative_path=upload.relative_path,
            safe_relative_path=safe_relative_path,
            content=upload.content,
        )
        if skip_reason is not None:
            _count_skip(skip_reasons, skip_reason)
            continue
        if safe_relative_path in seen_paths:
            _count_skip(skip_reasons, "duplicate_path")
            continue
        seen_paths.add(safe_relative_path)

        target_path = (root / safe_relative_path).resolve()
        try:
            target_path.relative_to(root)
        except ValueError:
            _count_skip(skip_reasons, "unsafe_path")
            continue

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(upload.content)
        except OSError as exc:
            raise CodeIngestionServiceError(
                f"Uploaded code file could not be stored: {safe_relative_path}"
            ) from exc

    return skip_reasons


def _install_local_source(
    temp_path: Path,
    repositories_dir: Path,
    repo_name: str,
    source_fingerprint: str,
    existing_repository: StoredCodeRepositoryMetadata | None,
) -> tuple[Path, str, bool]:
    final_path = (
        repositories_dir
        / LOCAL_CODE_UPLOAD_ROOT
        / repo_name
        / source_fingerprint[:16]
    )
    storage_path = final_path.relative_to(repositories_dir).as_posix()

    if final_path.exists():
        shutil.rmtree(temp_path, ignore_errors=True)
        return final_path, storage_path, False

    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temp_path), str(final_path))
    return final_path, storage_path, existing_repository is None


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


def _local_upload_skip_reason(
    raw_relative_path: str,
    safe_relative_path: str,
    content: bytes,
) -> str | None:
    raw_parts = tuple(
        part
        for part in PurePosixPath(
            (raw_relative_path or "").replace("\\", "/").strip()
        ).parts
        if part not in {"", "."}
    )
    raw_filename = raw_parts[-1] if raw_parts else safe_relative_path
    directory_names = [part.casefold() for part in raw_parts[:-1]]

    if any(
        directory_name in LOCAL_EXCLUDED_DIR_NAMES
        for directory_name in directory_names
    ):
        return "excluded_path"

    if raw_filename.casefold() in HIDDEN_OR_SYSTEM_FILENAMES or any(
        part.startswith(".") for part in raw_parts
    ):
        return "hidden_or_system_file"

    if not content:
        return "empty_file"

    if len(content) > MAX_CODE_UPLOAD_FILE_BYTES:
        return "too_large"

    return None


def _safe_source_name(folder_name: str) -> str:
    normalized_name = (folder_name or "").replace("\\", "/").strip()
    raw_name = next(
        (
            part
            for part in reversed(PurePosixPath(normalized_name).parts)
            if part not in {"", ".", ".."}
        ),
        "",
    )
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name).strip("._-")
    if not safe_name:
        raise CodeIngestionServiceError("Uploaded code folder name is required.")

    return safe_name[:MAX_LOCAL_SOURCE_NAME_LENGTH]


def _safe_relative_path(relative_path: str) -> str:
    normalized_path = (relative_path or "").replace("\\", "/").strip()
    if (
        not normalized_path
        or normalized_path.startswith("/")
        or "\x00" in normalized_path
        or re.match(r"^[A-Za-z]:/", normalized_path)
    ):
        raise CodeIngestionServiceError("Uploaded code file path is invalid.")

    path = PurePosixPath(normalized_path)
    safe_parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise CodeIngestionServiceError("Uploaded code file path is unsafe.")
        safe_part = re.sub(r"[^A-Za-z0-9._ -]", "_", part.strip()).strip(" .")
        if not safe_part:
            raise CodeIngestionServiceError(
                "Uploaded code file path contains an invalid segment."
            )
        safe_parts.append(safe_part)

    safe_path = PurePosixPath(*safe_parts).as_posix()
    if not safe_path or len(safe_path) > MAX_LOCAL_RELATIVE_PATH_LENGTH:
        raise CodeIngestionServiceError("Uploaded code file path is invalid.")

    return safe_path


def _source_path_prefix(
    source: PreparedCodeSource,
    source_fingerprint: str | None,
) -> str:
    if source.source_type == CodeSourceType.LOCAL_FOLDER.value:
        fingerprint = source_fingerprint or source.source_fingerprint or "unknown"
        return f"{source.repo_name}@local-{fingerprint[:12]}"

    return f"{source.repo_name}@{source.commit_sha}"


def _source_response(
    source: PreparedCodeSource,
    repository_id: int,
    status: str,
    files: int,
    chunks: int,
    embeddings: int,
    stored_batch: StoredVectorBatch,
    saved_chunks: int,
    skipped_files: int,
    skip_reasons: dict[str, int],
    recovered: bool = False,
    message: str | None = None,
    source_fingerprint: str | None = None,
) -> CodeIngestResponse:
    return CodeIngestResponse(
        repository_id=repository_id,
        repo_name=source.repo_name,
        source_type=source.source_type,
        repo_url=source.repo_url,
        branch=source.branch,
        commit_sha=source.commit_sha,
        source_fingerprint=source_fingerprint or source.source_fingerprint,
        storage_path=source.storage_path,
        status=status,
        files=files,
        chunks=chunks,
        embeddings=embeddings,
        collection_name=stored_batch.collection_name,
        stored_vectors=stored_batch.stored_count,
        saved_chunks=saved_chunks,
        vector_size=stored_batch.vector_size,
        skipped_files=skipped_files,
        skip_reasons=skip_reasons,
        recovered=recovered,
        message=message,
    )


def _existing_repository_response(
    repository: StoredCodeRepositoryMetadata,
    collection_name: str,
) -> CodeIngestResponse:
    return CodeIngestResponse(
        repository_id=repository.id,
        repo_name=repository.repo_name,
        source_type=repository.source_type,
        repo_url=repository.repo_url,
        branch=repository.branch,
        commit_sha=repository.commit_sha,
        source_fingerprint=repository.source_fingerprint,
        storage_path=repository.storage_path,
        status=repository.status,
        files=len(repository.files),
        chunks=len(repository.chunks),
        embeddings=0,
        collection_name=collection_name,
        stored_vectors=0,
        saved_chunks=len(repository.chunks),
        vector_size=None,
        already_indexed=True,
        message=_already_indexed_message(repository.source_type),
    )


def _is_complete_indexed_repository(
    repository: StoredCodeRepositoryMetadata | None,
) -> bool:
    return (
        repository is not None
        and repository.status == DocumentStatus.INDEXED.value
        and bool(repository.files)
        and bool(repository.chunks)
    )


def _repository_point_ids(
    repository: StoredCodeRepositoryMetadata | None,
) -> list[str]:
    if repository is None:
        return []

    return [chunk.qdrant_point_id for chunk in repository.chunks]


def _collection_name(vector_store: QdrantVectorStore) -> str:
    return getattr(vector_store, "collection_name", "company_documents")


def _cleanup_source_state(
    source: PreparedCodeSource,
    vector_store: QdrantVectorStore,
    stored_batch: StoredVectorBatch | None,
    metadata_service: CodeMetadataService,
    repository_id: int | None,
    delete_source: bool,
) -> str | None:
    cleanup_errors: list[str] = []

    if stored_batch is not None:
        try:
            vector_store.delete_points(stored_batch.point_ids)
        except VectorStoreError as exc:
            cleanup_errors.append(str(exc))

    if repository_id is not None:
        try:
            metadata_service.delete_repository(repository_id)
        except CodeMetadataPersistenceError as exc:
            cleanup_errors.append(str(exc))

    if delete_source:
        try:
            shutil.rmtree(source.path, ignore_errors=True)
        except OSError as exc:
            cleanup_errors.append(
                f"Failed to delete stored code source '{source.path}': {exc}"
            )

    if cleanup_errors:
        return "; ".join(cleanup_errors)

    return None


def _cleanup_new_vectors_best_effort(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError:
        pass


def _cleanup_old_vectors_after_repository_recovery(
    vector_store: QdrantVectorStore,
    point_ids: list[str],
) -> None:
    try:
        vector_store.delete_points(point_ids)
    except VectorStoreError:
        pass


def _grant_existing_source_access(
    permission_service: PermissionService,
    repository_id: int,
    user_id: int,
) -> None:
    try:
        permission_service.grant_code_repository_access(
            repository_id=repository_id,
            user_id=user_id,
        )
    except PermissionServiceError as exc:
        raise CodeMetadataPersistenceError(
            f"Failed to grant uploader code source access: {exc}"
        ) from exc


def _merge_skip_reasons(*reason_maps: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for reason_map in reason_maps:
        for reason, count in reason_map.items():
            merged[reason] = merged.get(reason, 0) + count
    return merged


def _delete_source_directory_best_effort(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
        parent = path.parent
        for _ in range(2):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    except OSError:
        pass


def _cleanup_local_upload_after_failure(
    source: PreparedCodeSource | None,
    temp_path: Path,
) -> None:
    if source is not None and source.cleanup_on_failure:
        _delete_source_directory_best_effort(source.path)
        return

    shutil.rmtree(temp_path, ignore_errors=True)


def _already_indexed_message(source_type: str) -> str:
    if source_type == CodeSourceType.LOCAL_FOLDER.value:
        return "This code folder is already indexed."

    return "This revision is already indexed."


def _indexed_message(source_type: str) -> str:
    if source_type == CodeSourceType.LOCAL_FOLDER.value:
        return "Code folder indexed."

    return "Repository indexed."


def _recovered_message(source_type: str) -> str:
    if source_type == CodeSourceType.LOCAL_FOLDER.value:
        return "Existing code folder source was recovered and indexed."

    return "Existing repository revision was recovered and indexed."


def _count_skip(skip_reasons: dict[str, int], reason: str) -> None:
    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
