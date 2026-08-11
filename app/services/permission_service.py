from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    CodeChunkRecord,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    DocumentChunkRecord,
    DocumentPermissionRecord,
    DocumentRecord,
    DocumentStatus,
    UserRecord,
)


class PermissionServiceError(RuntimeError):
    """Raised when document permission handling fails."""


class PermissionPersistenceError(PermissionServiceError):
    """Raised when document permissions cannot be read or written."""


class PermissionTargetNotFoundError(PermissionServiceError):
    """Raised when a permission references a missing user or document."""


class DocumentAccessDeniedError(PermissionServiceError):
    """Raised when a user does not have document access."""


class CodeRepositoryAccessDeniedError(PermissionServiceError):
    """Raised when a user does not have code repository access."""


@dataclass(frozen=True)
class StoredDocumentPermission:
    id: int
    document_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredCodeRepositoryPermission:
    id: int
    repository_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class PermissionService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def grant_document_access(
        self,
        document_id: int,
        user_id: int,
    ) -> StoredDocumentPermission:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_document_record(session=session, document_id=document_id)
                _get_user_record(session=session, user_id=user_id)

                existing_permission = _get_permission_record(
                    session=session,
                    document_id=document_id,
                    user_id=user_id,
                )
                if existing_permission is not None:
                    return _to_stored_permission(existing_permission)

                permission = DocumentPermissionRecord(
                    document_id=document_id,
                    user_id=user_id,
                )
                session.add(permission)
                session.flush()
                stored_permission = _to_stored_permission(permission)
                session.commit()
                return stored_permission
        except PermissionTargetNotFoundError:
            raise
        except IntegrityError as exc:
            raise PermissionPersistenceError(
                f"Failed to grant document access: {exc}"
            ) from exc
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to grant document access: {exc}"
            ) from exc

    def revoke_document_access(self, document_id: int, user_id: int) -> bool:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_document_record(session=session, document_id=document_id)
                _get_user_record(session=session, user_id=user_id)

                permission = _get_permission_record(
                    session=session,
                    document_id=document_id,
                    user_id=user_id,
                )
                if permission is None:
                    return False

                session.delete(permission)
                session.commit()
                return True
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to revoke document access: {exc}"
            ) from exc

    def grant_code_repository_access(
        self,
        repository_id: int,
        user_id: int,
    ) -> StoredCodeRepositoryPermission:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_code_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                _get_user_record(session=session, user_id=user_id)

                existing_permission = _get_code_repository_permission_record(
                    session=session,
                    repository_id=repository_id,
                    user_id=user_id,
                )
                if existing_permission is not None:
                    return _to_stored_code_repository_permission(
                        existing_permission
                    )

                permission = CodeRepositoryPermissionRecord(
                    repository_id=repository_id,
                    user_id=user_id,
                )
                session.add(permission)
                session.flush()
                stored_permission = _to_stored_code_repository_permission(permission)
                session.commit()
                return stored_permission
        except PermissionTargetNotFoundError:
            raise
        except IntegrityError as exc:
            raise PermissionPersistenceError(
                f"Failed to grant code repository access: {exc}"
            ) from exc
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to grant code repository access: {exc}"
            ) from exc

    def revoke_code_repository_access(self, repository_id: int, user_id: int) -> bool:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_code_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                _get_user_record(session=session, user_id=user_id)

                permission = _get_code_repository_permission_record(
                    session=session,
                    repository_id=repository_id,
                    user_id=user_id,
                )
                if permission is None:
                    return False

                session.delete(permission)
                session.commit()
                return True
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to revoke code repository access: {exc}"
            ) from exc

    def ensure_user_can_access_document(self, user_id: int, document_id: int) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_document_record(session=session, document_id=document_id)
                _get_user_record(session=session, user_id=user_id)
                permission = _get_permission_record(
                    session=session,
                    document_id=document_id,
                    user_id=user_id,
                )
                if permission is None:
                    raise DocumentAccessDeniedError(
                        f"User {user_id} cannot access document {document_id}."
                    )
        except (DocumentAccessDeniedError, PermissionTargetNotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to check document access: {exc}"
            ) from exc

    def ensure_user_can_access_code_repository(
        self,
        user_id: int,
        repository_id: int,
    ) -> None:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_code_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                _get_user_record(session=session, user_id=user_id)
                permission = _get_code_repository_permission_record(
                    session=session,
                    repository_id=repository_id,
                    user_id=user_id,
                )
                if permission is None:
                    raise CodeRepositoryAccessDeniedError(
                        f"User {user_id} cannot access code repository {repository_id}."
                    )
        except (CodeRepositoryAccessDeniedError, PermissionTargetNotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to check code repository access: {exc}"
            ) from exc

    def user_has_document_access(self, user_id: int, document_id: int) -> bool:
        try:
            self.ensure_user_can_access_document(
                user_id=user_id,
                document_id=document_id,
            )
            return True
        except (DocumentAccessDeniedError, PermissionTargetNotFoundError):
            return False

    def user_has_code_repository_access(
        self,
        user_id: int,
        repository_id: int,
    ) -> bool:
        try:
            self.ensure_user_can_access_code_repository(
                user_id=user_id,
                repository_id=repository_id,
            )
            return True
        except (CodeRepositoryAccessDeniedError, PermissionTargetNotFoundError):
            return False

    def list_accessible_document_ids(self, user_id: int) -> list[int]:
        try:
            self.init_database()
            with self.session_factory() as session:
                return list(
                    session.scalars(
                        select(DocumentPermissionRecord.document_id)
                        .join(
                            DocumentRecord,
                            DocumentRecord.id
                            == DocumentPermissionRecord.document_id,
                        )
                        .where(DocumentPermissionRecord.user_id == user_id)
                        .order_by(
                            DocumentRecord.created_at.desc(),
                            DocumentRecord.id.desc(),
                        )
                    ).all()
                )
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list accessible documents: {exc}"
            ) from exc

    def list_accessible_code_repository_ids(self, user_id: int) -> list[int]:
        try:
            self.init_database()
            with self.session_factory() as session:
                return list(
                    session.scalars(
                        select(CodeRepositoryPermissionRecord.repository_id)
                        .join(
                            CodeRepositoryRecord,
                            CodeRepositoryRecord.id
                            == CodeRepositoryPermissionRecord.repository_id,
                        )
                        .where(CodeRepositoryPermissionRecord.user_id == user_id)
                        .order_by(
                            CodeRepositoryRecord.created_at.desc(),
                            CodeRepositoryRecord.id.desc(),
                        )
                    ).all()
                )
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list accessible code repositories: {exc}"
            ) from exc

    def list_accessible_qdrant_point_ids(self, user_id: int) -> list[str]:
        try:
            self.init_database()
            with self.session_factory() as session:
                document_point_ids = list(
                    session.scalars(
                        select(DocumentChunkRecord.qdrant_point_id)
                        .join(
                            DocumentRecord,
                            DocumentRecord.id == DocumentChunkRecord.document_id,
                        )
                        .join(
                            DocumentPermissionRecord,
                            DocumentPermissionRecord.document_id
                            == DocumentRecord.id,
                        )
                        .where(
                            DocumentPermissionRecord.user_id == user_id,
                            DocumentRecord.status == DocumentStatus.INDEXED.value,
                        )
                        .order_by(
                            DocumentRecord.id.asc(),
                            DocumentChunkRecord.chunk_index.asc(),
                        )
                    ).all()
                )
                code_point_ids = list(
                    session.scalars(
                        select(CodeChunkRecord.qdrant_point_id)
                        .join(
                            CodeRepositoryRecord,
                            CodeRepositoryRecord.id
                            == CodeChunkRecord.repository_id,
                        )
                        .join(
                            CodeRepositoryPermissionRecord,
                            CodeRepositoryPermissionRecord.repository_id
                            == CodeRepositoryRecord.id,
                        )
                        .where(
                            CodeRepositoryPermissionRecord.user_id == user_id,
                            CodeRepositoryRecord.status
                            == DocumentStatus.INDEXED.value,
                        )
                        .order_by(
                            CodeRepositoryRecord.id.asc(),
                            CodeChunkRecord.chunk_index.asc(),
                        )
                    ).all()
                )
                return [*document_point_ids, *code_point_ids]
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list accessible Qdrant point IDs: {exc}"
            ) from exc

    def list_document_permissions(
        self,
        document_id: int,
    ) -> list[StoredDocumentPermission]:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_document_record(session=session, document_id=document_id)
                records = session.scalars(
                    select(DocumentPermissionRecord)
                    .where(DocumentPermissionRecord.document_id == document_id)
                    .order_by(
                        DocumentPermissionRecord.created_at.asc(),
                        DocumentPermissionRecord.id.asc(),
                    )
                ).all()
                return [_to_stored_permission(record) for record in records]
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list document permissions: {exc}"
            ) from exc

    def list_document_permissions_for_user(
        self,
        user_id: int,
    ) -> list[StoredDocumentPermission]:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_user_record(session=session, user_id=user_id)
                records = session.scalars(
                    select(DocumentPermissionRecord)
                    .join(
                        DocumentRecord,
                        DocumentRecord.id == DocumentPermissionRecord.document_id,
                    )
                    .where(DocumentPermissionRecord.user_id == user_id)
                    .order_by(
                        DocumentRecord.created_at.desc(),
                        DocumentRecord.id.desc(),
                    )
                ).all()
                return [_to_stored_permission(record) for record in records]
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list user document permissions: {exc}"
            ) from exc

    def list_code_repository_permissions(
        self,
        repository_id: int,
    ) -> list[StoredCodeRepositoryPermission]:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_code_repository_record(
                    session=session,
                    repository_id=repository_id,
                )
                records = session.scalars(
                    select(CodeRepositoryPermissionRecord)
                    .where(
                        CodeRepositoryPermissionRecord.repository_id
                        == repository_id
                    )
                    .order_by(
                        CodeRepositoryPermissionRecord.created_at.asc(),
                        CodeRepositoryPermissionRecord.id.asc(),
                    )
                ).all()
                return [
                    _to_stored_code_repository_permission(record)
                    for record in records
                ]
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list code repository permissions: {exc}"
            ) from exc

    def list_code_repository_permissions_for_user(
        self,
        user_id: int,
    ) -> list[StoredCodeRepositoryPermission]:
        try:
            self.init_database()
            with self.session_factory() as session:
                _get_user_record(session=session, user_id=user_id)
                records = session.scalars(
                    select(CodeRepositoryPermissionRecord)
                    .join(
                        CodeRepositoryRecord,
                        CodeRepositoryRecord.id
                        == CodeRepositoryPermissionRecord.repository_id,
                    )
                    .where(CodeRepositoryPermissionRecord.user_id == user_id)
                    .order_by(
                        CodeRepositoryRecord.created_at.desc(),
                        CodeRepositoryRecord.id.desc(),
                    )
                ).all()
                return [
                    _to_stored_code_repository_permission(record)
                    for record in records
                ]
        except PermissionTargetNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise PermissionPersistenceError(
                f"Failed to list user code repository permissions: {exc}"
            ) from exc


def _get_document_record(session: Session, document_id: int) -> DocumentRecord:
    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise PermissionTargetNotFoundError(f"Document not found: {document_id}")

    return document


def _get_user_record(session: Session, user_id: int) -> UserRecord:
    user = session.get(UserRecord, user_id)
    if user is None:
        raise PermissionTargetNotFoundError(f"User not found: {user_id}")

    return user


def _get_code_repository_record(
    session: Session,
    repository_id: int,
) -> CodeRepositoryRecord:
    repository = session.get(CodeRepositoryRecord, repository_id)
    if repository is None:
        raise PermissionTargetNotFoundError(
            f"Code repository not found: {repository_id}"
        )

    return repository


def _get_permission_record(
    session: Session,
    document_id: int,
    user_id: int,
) -> DocumentPermissionRecord | None:
    return session.scalars(
        select(DocumentPermissionRecord).where(
            DocumentPermissionRecord.document_id == document_id,
            DocumentPermissionRecord.user_id == user_id,
        )
    ).one_or_none()


def _get_code_repository_permission_record(
    session: Session,
    repository_id: int,
    user_id: int,
) -> CodeRepositoryPermissionRecord | None:
    return session.scalars(
        select(CodeRepositoryPermissionRecord).where(
            CodeRepositoryPermissionRecord.repository_id == repository_id,
            CodeRepositoryPermissionRecord.user_id == user_id,
        )
    ).one_or_none()


def _to_stored_permission(
    permission: DocumentPermissionRecord,
) -> StoredDocumentPermission:
    return StoredDocumentPermission(
        id=permission.id,
        document_id=permission.document_id,
        user_id=permission.user_id,
        created_at=permission.created_at,
        updated_at=permission.updated_at,
    )


def _to_stored_code_repository_permission(
    permission: CodeRepositoryPermissionRecord,
) -> StoredCodeRepositoryPermission:
    return StoredCodeRepositoryPermission(
        id=permission.id,
        repository_id=permission.repository_id,
        user_id=permission.user_id,
        created_at=permission.created_at,
        updated_at=permission.updated_at,
    )
