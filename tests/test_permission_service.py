import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryRecord,
    DocumentChunkRecord,
    DocumentRecord,
    DocumentStatus,
    UserRecord,
)
from app.services.permission_service import (
    CodeRepositoryAccessDeniedError,
    DocumentAccessDeniedError,
    PermissionService,
    PermissionTargetNotFoundError,
)


def _build_permission_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        PermissionService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _create_user_and_document(session_factory) -> tuple[int, int]:
    with session_factory() as session:
        user = UserRecord(
            email="admin@example.com",
            password_hash="$argon2id$hash",
        )
        document = DocumentRecord(
            filename="security.md",
            file_type="markdown",
            storage_path="security.md",
            file_hash="a" * 64,
            status=DocumentStatus.INDEXED.value,
        )
        document.chunks.append(
            DocumentChunkRecord(
                qdrant_point_id="point-1",
                chunk_index=1,
                page_number=None,
                start_char=0,
                end_char=120,
            )
        )
        session.add_all([user, document])
        session.commit()
        return user.id, document.id


def _create_code_repository(session_factory) -> int:
    with session_factory() as session:
        repository = CodeRepositoryRecord(
            repo_url="file:///repo",
            repo_name="repo",
            branch="main",
            commit_sha="a" * 40,
            storage_path="repo/main/aaaaaaaa",
            status=DocumentStatus.INDEXED.value,
        )
        code_file = CodeFileRecord(
            repository=repository,
            file_path="app.py",
            language="python",
            file_hash="b" * 64,
            size_bytes=100,
        )
        code_file.chunks.append(
            CodeChunkRecord(
                repository=repository,
                qdrant_point_id="code-point-1",
                chunk_index=1,
                symbol_name="hello",
                symbol_kind="function",
                start_line=1,
                end_line=3,
                start_char=0,
                end_char=80,
            )
        )
        session.add(repository)
        session.commit()
        return repository.id


def test_grant_document_access_is_idempotent() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)

    first_permission = permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )
    second_permission = permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    assert first_permission.id == second_permission.id
    assert permission_service.user_has_document_access(
        user_id=user_id,
        document_id=document_id,
    )


def test_revoke_document_access() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)
    permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    revoked = permission_service.revoke_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    assert revoked is True
    with pytest.raises(DocumentAccessDeniedError):
        permission_service.ensure_user_can_access_document(
            user_id=user_id,
            document_id=document_id,
        )


def test_list_document_permissions_for_user() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)
    permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    permissions = permission_service.list_document_permissions_for_user(user_id)

    assert len(permissions) == 1
    assert permissions[0].document_id == document_id
    assert permissions[0].user_id == user_id


def test_accessible_document_and_point_ids_are_user_scoped() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)
    permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    assert permission_service.list_accessible_document_ids(user_id) == [document_id]
    assert permission_service.list_accessible_qdrant_point_ids(user_id) == ["point-1"]
    assert permission_service.list_accessible_document_ids(user_id + 1) == []
    assert permission_service.list_accessible_qdrant_point_ids(user_id + 1) == []


def test_accessible_qdrant_point_ids_include_code_repository_permissions() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)
    permission_service.grant_document_access(
        document_id=document_id,
        user_id=user_id,
    )

    repository_id = _create_code_repository(session_factory)
    permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=user_id,
    )

    assert permission_service.list_accessible_qdrant_point_ids(user_id) == [
        "point-1",
        "code-point-1",
    ]


def test_code_repository_permissions_are_listed_and_revoked() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, _document_id = _create_user_and_document(session_factory)
    repository_id = _create_code_repository(session_factory)

    first_permission = permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=user_id,
    )
    second_permission = permission_service.grant_code_repository_access(
        repository_id=repository_id,
        user_id=user_id,
    )

    assert first_permission.id == second_permission.id
    assert permission_service.list_accessible_code_repository_ids(user_id) == [
        repository_id
    ]
    assert permission_service.user_has_code_repository_access(
        user_id=user_id,
        repository_id=repository_id,
    )
    assert [
        permission.repository_id
        for permission in permission_service.list_code_repository_permissions_for_user(
            user_id
        )
    ] == [repository_id]
    assert [
        permission.user_id
        for permission in permission_service.list_code_repository_permissions(
            repository_id
        )
    ] == [user_id]

    revoked = permission_service.revoke_code_repository_access(
        repository_id=repository_id,
        user_id=user_id,
    )

    assert revoked is True
    assert permission_service.list_accessible_code_repository_ids(user_id) == []
    assert permission_service.list_accessible_qdrant_point_ids(user_id) == []
    with pytest.raises(CodeRepositoryAccessDeniedError):
        permission_service.ensure_user_can_access_code_repository(
            user_id=user_id,
            repository_id=repository_id,
        )


def test_grant_rejects_missing_user_or_document() -> None:
    permission_service, session_factory = _build_permission_service()
    user_id, document_id = _create_user_and_document(session_factory)

    with pytest.raises(PermissionTargetNotFoundError):
        permission_service.grant_document_access(
            document_id=document_id,
            user_id=user_id + 999,
        )

    with pytest.raises(PermissionTargetNotFoundError):
        permission_service.grant_document_access(
            document_id=document_id + 999,
            user_id=user_id,
        )
