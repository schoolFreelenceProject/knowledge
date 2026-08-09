from __future__ import annotations

from app.schemas.code import CodeIngestResponse
from app.services.code_chunker import CodeChunkingConfig, chunk_code_files
from app.services.code_metadata_service import (
    CodeMetadataPersistenceError,
    CodeMetadataService,
    CodeRepositoryConflictError,
)
from app.services.code_parser import CodeParserError, ParsedCodeFile, TreeSitterCodeParser
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


class CodeIngestionServiceError(RuntimeError):
    """Raised when a code repository cannot be ingested."""


class CodeRepositoryIngestionConflictError(CodeIngestionServiceError):
    """Raised when a repository revision is already indexed."""


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
        cloned_repository: ClonedRepository | None = None
        stored_batch: StoredVectorBatch | None = None
        repository_id: int | None = None

        try:
            cloned_repository = self.repository_loader.clone_repository(
                repo_url=repo_url,
                branch=branch,
            )
            if self.metadata_service.repository_revision_exists(
                repo_url=cloned_repository.repo_url,
                branch=cloned_repository.branch,
                commit_sha=cloned_repository.commit_sha,
            ):
                raise CodeRepositoryIngestionConflictError(
                    "Code repository revision is already indexed."
                )

            parsed_files = self._parse_repository(
                repository=cloned_repository,
                include_globs=include_globs,
                exclude_globs=exclude_globs,
            )
            if not parsed_files:
                raise CodeIngestionServiceError(
                    "No supported code files were found in the repository."
                )

            chunks = chunk_code_files(parsed_files, config=self.chunk_config)
            if not chunks:
                raise CodeIngestionServiceError(
                    "No code chunks were generated from the repository."
                )

            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            stored_batch = self.vector_store.store_embeddings(embedded_chunks)
            persisted = self.metadata_service.save_repository_metadata(
                parsed_files=parsed_files,
                chunks=chunks,
                stored_batch=stored_batch,
                repo_url=cloned_repository.repo_url,
                repo_name=cloned_repository.repo_name,
                branch=cloned_repository.branch,
                commit_sha=cloned_repository.commit_sha,
                storage_path=cloned_repository.storage_path,
            )
            repository_id = persisted.repository_id

            self.permission_service.grant_code_repository_access(
                repository_id=repository_id,
                user_id=uploader_user_id,
            )

            return CodeIngestResponse(
                repository_id=repository_id,
                repo_name=cloned_repository.repo_name,
                repo_url=cloned_repository.repo_url,
                branch=cloned_repository.branch,
                commit_sha=cloned_repository.commit_sha,
                storage_path=cloned_repository.storage_path,
                status=persisted.status,
                files=persisted.saved_files,
                chunks=len(chunks),
                embeddings=len(embedded_chunks),
                collection_name=stored_batch.collection_name,
                stored_vectors=stored_batch.stored_count,
                saved_chunks=persisted.saved_chunks,
                vector_size=stored_batch.vector_size,
            )
        except CodeRepositoryAlreadyIndexedError as exc:
            raise CodeRepositoryIngestionConflictError(str(exc)) from exc
        except CodeRepositoryConflictError as exc:
            _cleanup_repository_state(
                cloned_repository=cloned_repository,
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                metadata_service=self.metadata_service,
                repository_id=repository_id,
            )
            raise CodeRepositoryIngestionConflictError(str(exc)) from exc
        except PermissionServiceError as exc:
            cleanup_error = _cleanup_repository_state(
                cloned_repository=cloned_repository,
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                metadata_service=self.metadata_service,
                repository_id=repository_id,
            )
            detail = f"Failed to grant uploader code repository access: {exc}"
            if cleanup_error:
                detail = f"{detail}. Cleanup also failed: {cleanup_error}"
            raise CodeMetadataPersistenceError(detail) from exc
        except (
            CodeRepositoryLoaderError,
            CodeParserError,
            CodeIngestionServiceError,
        ):
            if cloned_repository is not None:
                cleanup_repository(cloned_repository)
            raise
        except Exception:
            _cleanup_repository_state(
                cloned_repository=cloned_repository,
                vector_store=self.vector_store,
                stored_batch=stored_batch,
                metadata_service=self.metadata_service,
                repository_id=repository_id,
            )
            raise

    def _parse_repository(
        self,
        repository: ClonedRepository,
        include_globs: list[str] | None,
        exclude_globs: list[str] | None,
    ) -> list[ParsedCodeFile]:
        paths = self.repository_loader.discover_code_files(
            repository_path=repository.path,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
        )
        return [
            self.parser.parse_file(
                file_path=path,
                repository_root=repository.path,
                repo_url=repository.repo_url,
                repo_name=repository.repo_name,
                branch=repository.branch,
                commit_sha=repository.commit_sha,
            )
            for path in paths
        ]


def _cleanup_repository_state(
    cloned_repository: ClonedRepository | None,
    vector_store: QdrantVectorStore,
    stored_batch: StoredVectorBatch | None,
    metadata_service: CodeMetadataService,
    repository_id: int | None,
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

    if cloned_repository is not None:
        try:
            cleanup_repository(cloned_repository)
        except OSError as exc:
            cleanup_errors.append(
                f"Failed to delete cloned repository '{cloned_repository.path}': {exc}"
            )

    if cleanup_errors:
        return "; ".join(cleanup_errors)

    return None
