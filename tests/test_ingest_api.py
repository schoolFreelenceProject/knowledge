import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.ingest import ingest_document, ingest_document_folder
from app.schemas.ingest import FolderIngestFileResult, FolderIngestResponse
from app.services.auth_service import AuthenticatedUser
from app.services.metadata_service import MetadataPersistenceError


class FakeUploadFile:
    filename = "policy.pdf"

    def __init__(self, content: bytes = b"%PDF fake content") -> None:
        self.content = content
        self._offset = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self.content):
            return b""

        if size is None or size < 0:
            size = len(self.content) - self._offset

        chunk = self.content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


class FakeFolderUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content
        self._offset = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self.content):
            return b""

        if size is None or size < 0:
            size = len(self.content) - self._offset

        chunk = self.content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


class FakeIngestionService:
    def ingest_uploaded_document(self, filename, content, uploader_user_id):
        raise MetadataPersistenceError(
            "psycopg.errors.UniqueViolation: duplicate key value violates "
            'unique constraint "uq_document_chunks_position"; SQL: INSERT INTO '
            "document_chunks ... params: {'document_id': 3}"
        )


class FakeFolderIngestionService:
    def ingest_folder_documents(self, folder_name, files, uploader_user_id):
        return FolderIngestResponse(
            folder_name=folder_name,
            files_discovered=len(files),
            indexed=1,
            skipped=1,
            failed=0,
            skip_reasons={"unsupported_extension": 1},
            results=[
                FolderIngestFileResult(
                    relative_path="HR/leave.md",
                    status="indexed",
                    document_id=3,
                    filename="HR/leave.md",
                    file_type="markdown",
                    chunks=1,
                    stored_vectors=1,
                ),
                FolderIngestFileResult(
                    relative_path="IT/logo.png",
                    status="skipped",
                    reason="unsupported_extension",
                    message="Skipped unsupported file type.",
                ),
            ],
        )


class FailingFolderIngestionService:
    def ingest_folder_documents(self, folder_name, files, uploader_user_id):
        raise MetadataPersistenceError(
            "psycopg.errors.UniqueViolation: duplicate key value violates "
            'unique constraint "uq_document_chunks_position"; SQL: INSERT INTO '
            "document_chunks ... params: {'document_id': 3}"
        )


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=7,
        email="uploader@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _set_upload_limits(
    monkeypatch: pytest.MonkeyPatch,
    *,
    file_size: int,
    bulk_size: int,
    file_count: int,
) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", str(file_size))
    monkeypatch.setenv("MAX_UPLOAD_FILE_SIZE", str(file_size))
    monkeypatch.setenv("MAX_BULK_UPLOAD_SIZE", str(bulk_size))
    monkeypatch.setenv("MAX_BULK_FILE_COUNT", str(file_count))


def test_ingest_document_hides_internal_metadata_errors() -> None:
    upload = FakeUploadFile()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document(
                file=upload,
                current_user=_build_user(),
                ingestion_service=FakeIngestionService(),
            )
        )

    assert upload.closed is True
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to save document metadata."
    assert "psycopg" not in exc_info.value.detail
    assert "INSERT" not in exc_info.value.detail
    assert "document_chunks" not in exc_info.value.detail


def test_ingest_document_rejects_single_oversized_file(monkeypatch) -> None:
    _set_upload_limits(monkeypatch, file_size=4, bulk_size=20, file_count=10)
    upload = FakeUploadFile(content=b"x" * 5)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document(
                file=upload,
                current_user=_build_user(),
                ingestion_service=FakeIngestionService(),
            )
        )

    assert upload.closed is True
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == (
        "Uploaded file is too large. Maximum allowed file size is 4 bytes."
    )


def test_ingest_document_folder_under_limit_returns_results_and_closes_uploads(
    monkeypatch,
) -> None:
    _set_upload_limits(monkeypatch, file_size=20, bulk_size=40, file_count=2)
    uploads = [
        FakeFolderUploadFile("leave.md", b"# Leave"),
        FakeFolderUploadFile("logo.png", b"binary"),
    ]

    response = asyncio.run(
        ingest_document_folder(
            folder_name="CompanyDocs",
            relative_paths=["HR/leave.md", "IT/logo.png"],
            files=uploads,
            current_user=_build_user(),
            ingestion_service=FakeFolderIngestionService(),
        )
    )

    assert [upload.closed for upload in uploads] == [True, True]
    assert response.files_discovered == 2
    assert response.indexed == 1
    assert response.skipped == 1
    assert response.results[0].relative_path == "HR/leave.md"


def test_ingest_document_folder_rejects_total_payload_over_limit(monkeypatch) -> None:
    _set_upload_limits(monkeypatch, file_size=4, bulk_size=5, file_count=10)
    uploads = [
        FakeFolderUploadFile("one.md", b"123"),
        FakeFolderUploadFile("two.md", b"456"),
    ]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document_folder(
                folder_name="CompanyDocs",
                relative_paths=["one.md", "two.md"],
                files=uploads,
                current_user=_build_user(),
                ingestion_service=FakeFolderIngestionService(),
            )
        )

    assert [upload.closed for upload in uploads] == [True, True]
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == (
        "Folder upload is too large. Maximum allowed total size is 5 bytes."
    )


def test_ingest_document_folder_rejects_single_oversized_file(monkeypatch) -> None:
    _set_upload_limits(monkeypatch, file_size=4, bulk_size=20, file_count=10)
    uploads = [FakeFolderUploadFile("large.md", b"12345")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document_folder(
                folder_name="CompanyDocs",
                relative_paths=["large.md"],
                files=uploads,
                current_user=_build_user(),
                ingestion_service=FakeFolderIngestionService(),
            )
        )

    assert uploads[0].closed is True
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == (
        "Uploaded file is too large. Maximum allowed file size is 4 bytes."
    )


def test_ingest_document_folder_rejects_file_count_limit(monkeypatch) -> None:
    _set_upload_limits(monkeypatch, file_size=20, bulk_size=40, file_count=1)
    uploads = [
        FakeFolderUploadFile("leave.md", b"# Leave"),
        FakeFolderUploadFile("security.md", b"# Security"),
    ]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document_folder(
                folder_name="CompanyDocs",
                relative_paths=["leave.md", "security.md"],
                files=uploads,
                current_user=_build_user(),
                ingestion_service=FakeFolderIngestionService(),
            )
        )

    assert [upload.closed for upload in uploads] == [True, True]
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == (
        "Folder upload has too many files. Maximum allowed file count is 1."
    )


def test_ingest_document_folder_rejects_mismatched_files_and_paths() -> None:
    uploads = [FakeFolderUploadFile("leave.md", b"# Leave")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document_folder(
                folder_name="CompanyDocs",
                relative_paths=["HR/leave.md", "IT/security.md"],
                files=uploads,
                current_user=_build_user(),
                ingestion_service=FakeFolderIngestionService(),
            )
        )

    assert uploads[0].closed is True
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Folder upload files and relative paths do not match."


def test_ingest_document_folder_hides_internal_metadata_errors() -> None:
    uploads = [FakeFolderUploadFile("leave.md", b"# Leave")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document_folder(
                folder_name="CompanyDocs",
                relative_paths=["HR/leave.md"],
                files=uploads,
                current_user=_build_user(),
                ingestion_service=FailingFolderIngestionService(),
            )
        )

    assert uploads[0].closed is True
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to save folder document metadata."
    assert "psycopg" not in exc_info.value.detail
    assert "INSERT" not in exc_info.value.detail
    assert "document_chunks" not in exc_info.value.detail
