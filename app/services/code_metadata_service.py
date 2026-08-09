from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryRecord,
    DocumentStatus,
)
from app.schemas.documents import DocumentChunk
from app.services.code_parser import ParsedCodeFile
from app.services.vector_store import StoredVectorBatch


class CodeMetadataPersistenceError(RuntimeError):
    """Raised when code metadata cannot be saved to the database."""


class CodeRepositoryConflictError(CodeMetadataPersistenceError):
    """Raised when a repository revision has already been indexed."""


@dataclass(frozen=True)
class PersistedCodeRepositoryMetadata:
    repository_id: int
    saved_files: int
    saved_chunks: int
    status: str


class CodeMetadataService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def repository_revision_exists(
        self,
        repo_url: str,
        branch: str,
        commit_sha: str,
    ) -> bool:
        try:
            self.init_database()
            with self.session_factory() as session:
                repository_id = session.scalar(
                    select(CodeRepositoryRecord.id).where(
                        CodeRepositoryRecord.repo_url == repo_url,
                        CodeRepositoryRecord.branch == branch,
                        CodeRepositoryRecord.commit_sha == commit_sha,
                    )
                )
                return repository_id is not None
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to check code repository metadata: {exc}"
            ) from exc

    def save_repository_metadata(
        self,
        parsed_files: list[ParsedCodeFile],
        chunks: list[DocumentChunk],
        stored_batch: StoredVectorBatch,
        repo_url: str,
        repo_name: str,
        branch: str,
        commit_sha: str,
        storage_path: str,
    ) -> PersistedCodeRepositoryMetadata:
        if len(chunks) != len(stored_batch.point_ids):
            raise CodeMetadataPersistenceError(
                "Stored Qdrant point ID count does not match generated code chunk count."
            )

        try:
            self.init_database()
            with self.session_factory() as session:
                repository = CodeRepositoryRecord(
                    repo_url=repo_url,
                    repo_name=repo_name,
                    branch=branch,
                    commit_sha=commit_sha,
                    storage_path=storage_path,
                    status=DocumentStatus.PROCESSING.value,
                )
                session.add(repository)
                session.flush()

                file_records = [
                    CodeFileRecord(
                        repository_id=repository.id,
                        file_path=parsed_file.file_path,
                        language=parsed_file.language,
                        file_hash=parsed_file.file_hash,
                        size_bytes=parsed_file.size_bytes,
                    )
                    for parsed_file in parsed_files
                ]
                session.add_all(file_records)
                session.flush()
                file_id_by_path = {
                    file_record.file_path: file_record.id
                    for file_record in file_records
                }

                session.add_all(
                    _build_chunk_records(
                        repository_id=repository.id,
                        file_id_by_path=file_id_by_path,
                        chunks=chunks,
                        point_ids=stored_batch.point_ids,
                    )
                )
                repository.status = DocumentStatus.INDEXED.value
                session.commit()
                return PersistedCodeRepositoryMetadata(
                    repository_id=repository.id,
                    saved_files=len(file_records),
                    saved_chunks=len(chunks),
                    status=repository.status,
                )
        except IntegrityError as exc:
            raise CodeRepositoryConflictError(
                "Code repository revision is already indexed."
            ) from exc
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to save code repository metadata: {exc}"
            ) from exc

    def delete_repository(self, repository_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                session.execute(
                    delete(CodeRepositoryRecord).where(
                        CodeRepositoryRecord.id == repository_id
                    )
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to delete code repository metadata: {exc}"
            ) from exc


def _build_chunk_records(
    repository_id: int,
    file_id_by_path: dict[str, int],
    chunks: list[DocumentChunk],
    point_ids: list[str],
) -> list[CodeChunkRecord]:
    records: list[CodeChunkRecord] = []
    for chunk, point_id in zip(chunks, point_ids, strict=True):
        file_path = chunk.metadata.repository_file_path
        if file_path is None or file_path not in file_id_by_path:
            raise CodeMetadataPersistenceError(
                "Code chunk metadata does not reference an indexed code file."
            )

        records.append(
            CodeChunkRecord(
                repository_id=repository_id,
                code_file_id=file_id_by_path[file_path],
                qdrant_point_id=point_id,
                chunk_index=chunk.metadata.chunk_index,
                symbol_name=chunk.metadata.symbol_name,
                symbol_kind=chunk.metadata.symbol_kind,
                start_line=chunk.metadata.start_line or 1,
                end_line=chunk.metadata.end_line or chunk.metadata.start_line or 1,
                start_char=chunk.metadata.start_char,
                end_char=chunk.metadata.end_char,
            )
        )

    return records
