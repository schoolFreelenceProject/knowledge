from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryRecord,
    CodeSourceType,
    DocumentStatus,
)
from app.schemas.documents import DocumentChunk
from app.services.code_parser import ParsedCodeFile
from app.services.vector_store import StoredVectorBatch


class CodeMetadataPersistenceError(RuntimeError):
    """Raised when code metadata cannot be saved to the database."""


class CodeRepositoryConflictError(CodeMetadataPersistenceError):
    """Raised when a repository revision has already been indexed."""


class CodeRepositoryMetadataNotFoundError(CodeMetadataPersistenceError):
    """Raised when a requested code repository metadata row does not exist."""


@dataclass(frozen=True)
class PersistedCodeRepositoryMetadata:
    repository_id: int
    saved_files: int
    saved_chunks: int
    status: str


@dataclass(frozen=True)
class StoredCodeFileMetadata:
    id: int
    file_path: str
    language: str
    file_hash: str
    size_bytes: int
    created_at: datetime
    chunk_count: int


@dataclass(frozen=True)
class StoredCodeChunkMetadata:
    id: int
    code_file_id: int
    qdrant_point_id: str
    chunk_index: int
    symbol_name: str | None
    symbol_kind: str | None
    start_line: int
    end_line: int
    start_char: int
    end_char: int
    created_at: datetime


@dataclass(frozen=True)
class StoredCodeRepositoryMetadata:
    id: int
    source_type: str
    repo_url: str | None
    repo_name: str
    branch: str | None
    commit_sha: str | None
    source_fingerprint: str | None
    storage_path: str
    status: str
    created_at: datetime
    updated_at: datetime
    files: list[StoredCodeFileMetadata]
    chunks: list[StoredCodeChunkMetadata]


@dataclass(frozen=True)
class StoredCodeChunkSource:
    repository: StoredCodeRepositoryMetadata
    file: StoredCodeFileMetadata
    chunk: StoredCodeChunkMetadata


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
                        CodeRepositoryRecord.source_type
                        == CodeSourceType.GIT_REPOSITORY.value,
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

    def get_repository_revision(
        self,
        repo_url: str,
        branch: str,
        commit_sha: str,
    ) -> StoredCodeRepositoryMetadata | None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = session.scalars(
                    select(CodeRepositoryRecord)
                    .options(
                        selectinload(CodeRepositoryRecord.files).selectinload(
                            CodeFileRecord.chunks
                        ),
                        selectinload(CodeRepositoryRecord.chunks),
                    )
                    .where(
                        CodeRepositoryRecord.source_type
                        == CodeSourceType.GIT_REPOSITORY.value,
                        CodeRepositoryRecord.repo_url == repo_url,
                        CodeRepositoryRecord.branch == branch,
                        CodeRepositoryRecord.commit_sha == commit_sha,
                    )
                ).one_or_none()
                if record is None:
                    return None

                return _to_stored_repository_metadata(record)
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to read code repository revision metadata: {exc}"
            ) from exc

    def get_local_folder_source(
        self,
        repo_name: str,
        source_fingerprint: str,
    ) -> StoredCodeRepositoryMetadata | None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = session.scalars(
                    select(CodeRepositoryRecord)
                    .options(
                        selectinload(CodeRepositoryRecord.files).selectinload(
                            CodeFileRecord.chunks
                        ),
                        selectinload(CodeRepositoryRecord.chunks),
                    )
                    .where(
                        CodeRepositoryRecord.source_type
                        == CodeSourceType.LOCAL_FOLDER.value,
                        CodeRepositoryRecord.repo_name == repo_name,
                        CodeRepositoryRecord.source_fingerprint
                        == source_fingerprint,
                    )
                ).one_or_none()
                if record is None:
                    return None

                return _to_stored_repository_metadata(record)
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to read local code folder metadata: {exc}"
            ) from exc

    def save_repository_metadata(
        self,
        parsed_files: list[ParsedCodeFile],
        chunks: list[DocumentChunk],
        stored_batch: StoredVectorBatch,
        repo_url: str | None,
        repo_name: str,
        branch: str | None,
        commit_sha: str | None,
        storage_path: str,
        source_type: str = CodeSourceType.GIT_REPOSITORY.value,
        source_fingerprint: str | None = None,
    ) -> PersistedCodeRepositoryMetadata:
        if len(chunks) != len(stored_batch.point_ids):
            raise CodeMetadataPersistenceError(
                "Stored Qdrant point ID count does not match generated code chunk count."
            )

        try:
            self.init_database()
            with self.session_factory() as session:
                repository = CodeRepositoryRecord(
                    source_type=source_type,
                    repo_url=repo_url,
                    repo_name=repo_name,
                    branch=branch,
                    commit_sha=commit_sha,
                    source_fingerprint=source_fingerprint,
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

    def list_repositories(
        self,
        repository_ids: list[int] | None = None,
    ) -> list[StoredCodeRepositoryMetadata]:
        if repository_ids is not None and not repository_ids:
            return []

        try:
            self.init_database()
            with self.session_factory() as session:
                statement = (
                    select(CodeRepositoryRecord)
                    .options(
                        selectinload(CodeRepositoryRecord.files).selectinload(
                            CodeFileRecord.chunks
                        ),
                        selectinload(CodeRepositoryRecord.chunks),
                    )
                    .order_by(
                        CodeRepositoryRecord.created_at.desc(),
                        CodeRepositoryRecord.id.desc(),
                    )
                )
                if repository_ids is not None:
                    statement = statement.where(
                        CodeRepositoryRecord.id.in_(repository_ids)
                    )

                records = session.scalars(statement).all()
                return [_to_stored_repository_metadata(record) for record in records]
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to list code repository metadata: {exc}"
            ) from exc

    def get_repository(self, repository_id: int) -> StoredCodeRepositoryMetadata:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                return _to_stored_repository_metadata(record)
        except CodeRepositoryMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to read code repository metadata: {exc}"
            ) from exc

    def get_code_chunk_source(
        self,
        qdrant_point_id: str,
    ) -> StoredCodeChunkSource:
        try:
            self.init_database()
            with self.session_factory() as session:
                chunk = session.scalars(
                    select(CodeChunkRecord)
                    .options(
                        selectinload(CodeChunkRecord.repository)
                        .selectinload(CodeRepositoryRecord.files)
                        .selectinload(CodeFileRecord.chunks),
                        selectinload(CodeChunkRecord.repository).selectinload(
                            CodeRepositoryRecord.chunks
                        ),
                        selectinload(CodeChunkRecord.code_file),
                    )
                    .where(CodeChunkRecord.qdrant_point_id == qdrant_point_id)
                ).one_or_none()
                if chunk is None:
                    raise CodeRepositoryMetadataNotFoundError(
                        f"Code chunk not found for point: {qdrant_point_id}"
                    )

                repository = _to_stored_repository_metadata(chunk.repository)
                stored_chunk = next(
                    (
                        item
                        for item in repository.chunks
                        if item.qdrant_point_id == qdrant_point_id
                    ),
                    None,
                )
                if stored_chunk is None:
                    raise CodeRepositoryMetadataNotFoundError(
                        f"Code chunk not found for point: {qdrant_point_id}"
                    )
                stored_file = next(
                    (
                        item
                        for item in repository.files
                        if item.id == stored_chunk.code_file_id
                    ),
                    None,
                )
                if stored_file is None:
                    raise CodeRepositoryMetadataNotFoundError(
                        f"Code file not found for point: {qdrant_point_id}"
                    )
                return StoredCodeChunkSource(
                    repository=repository,
                    file=stored_file,
                    chunk=stored_chunk,
                )
        except CodeRepositoryMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to read code chunk metadata: {exc}"
            ) from exc

    def list_chunk_point_ids(
        self,
        repository_ids: list[int] | None = None,
    ) -> list[str]:
        if repository_ids is not None and not repository_ids:
            return []

        try:
            self.init_database()
            with self.session_factory() as session:
                statement = (
                    select(CodeChunkRecord.qdrant_point_id)
                    .join(
                        CodeRepositoryRecord,
                        CodeRepositoryRecord.id == CodeChunkRecord.repository_id,
                    )
                    .where(
                        CodeRepositoryRecord.status == DocumentStatus.INDEXED.value
                    )
                    .order_by(
                        CodeRepositoryRecord.id.asc(),
                        CodeChunkRecord.chunk_index.asc(),
                    )
                )
                if repository_ids is not None:
                    statement = statement.where(
                        CodeRepositoryRecord.id.in_(repository_ids)
                    )

                return list(session.scalars(statement).all())
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to list code chunk point IDs: {exc}"
            ) from exc

    def delete_repository(self, repository_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                session.delete(record)
                session.commit()
        except CodeRepositoryMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to delete code repository metadata: {exc}"
            ) from exc

    def replace_repository_contents(
        self,
        repository_id: int,
        parsed_files: list[ParsedCodeFile],
        chunks: list[DocumentChunk],
        stored_batch: StoredVectorBatch,
        source_fingerprint: str | None = None,
    ) -> PersistedCodeRepositoryMetadata:
        if len(chunks) != len(stored_batch.point_ids):
            raise CodeMetadataPersistenceError(
                "Stored Qdrant point ID count does not match generated code chunk count."
            )

        try:
            self.init_database()
            with self.session_factory() as session:
                repository = _get_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                repository.status = DocumentStatus.PROCESSING.value
                if source_fingerprint is not None:
                    repository.source_fingerprint = source_fingerprint
                session.flush()

                session.execute(
                    delete(CodeChunkRecord).where(
                        CodeChunkRecord.repository_id == repository_id
                    )
                )
                session.execute(
                    delete(CodeFileRecord).where(
                        CodeFileRecord.repository_id == repository_id
                    )
                )
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
        except CodeRepositoryMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to replace code repository metadata: {exc}"
            ) from exc

    def mark_repository_failed(self, repository_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                record = _get_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                record.status = DocumentStatus.FAILED.value
                session.commit()
        except CodeRepositoryMetadataNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise CodeMetadataPersistenceError(
                f"Failed to mark code repository metadata as failed: {exc}"
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


def _get_repository_record(
    session: Session,
    repository_id: int,
) -> CodeRepositoryRecord:
    record = session.scalars(
        select(CodeRepositoryRecord)
        .options(
            selectinload(CodeRepositoryRecord.files).selectinload(
                CodeFileRecord.chunks
            ),
            selectinload(CodeRepositoryRecord.chunks),
        )
        .where(CodeRepositoryRecord.id == repository_id)
    ).one_or_none()
    if record is None:
        raise CodeRepositoryMetadataNotFoundError(
            f"Code repository not found: {repository_id}"
        )

    return record


def _to_stored_repository_metadata(
    record: CodeRepositoryRecord,
) -> StoredCodeRepositoryMetadata:
    chunks_by_file_id: dict[int, list[CodeChunkRecord]] = {}
    for chunk in record.chunks:
        chunks_by_file_id.setdefault(chunk.code_file_id, []).append(chunk)

    files = sorted(record.files, key=lambda file: file.file_path)
    chunks = sorted(record.chunks, key=lambda chunk: chunk.chunk_index)
    return StoredCodeRepositoryMetadata(
        id=record.id,
        source_type=record.source_type,
        repo_url=record.repo_url,
        repo_name=record.repo_name,
        branch=record.branch,
        commit_sha=record.commit_sha,
        source_fingerprint=record.source_fingerprint,
        storage_path=record.storage_path,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        files=[
            StoredCodeFileMetadata(
                id=file.id,
                file_path=file.file_path,
                language=file.language,
                file_hash=file.file_hash,
                size_bytes=file.size_bytes,
                created_at=file.created_at,
                chunk_count=len(chunks_by_file_id.get(file.id, [])),
            )
            for file in files
        ],
        chunks=[
            StoredCodeChunkMetadata(
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
            for chunk in chunks
        ],
    )
