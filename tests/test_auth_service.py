import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, UserRecord
from app.services.auth_service import (
    AuthService,
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)


def _build_auth_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        AuthService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
            jwt_secret_key="test-secret-with-at-least-32-bytes",
            jwt_algorithm="HS256",
            access_token_expire_minutes=30,
        ),
        session_factory,
    )


def test_register_user_creates_hashed_active_user() -> None:
    auth_service, session_factory = _build_auth_service()

    registered_user = auth_service.register_user(
        email="Admin@Example.com",
        password="correct-password",
    )

    with session_factory() as session:
        stored_user = session.scalars(select(UserRecord)).one()
        assert registered_user.id == stored_user.id
        assert stored_user.email == "admin@example.com"
        assert stored_user.password_hash != "correct-password"
        assert stored_user.password_hash.startswith("$argon2")
        assert stored_user.is_active is True


def test_register_user_rejects_duplicate_email() -> None:
    auth_service, _ = _build_auth_service()
    auth_service.register_user(
        email="admin@example.com",
        password="correct-password",
    )

    with pytest.raises(DuplicateUserError):
        auth_service.register_user(
            email="ADMIN@example.com",
            password="correct-password",
        )


def test_create_user_can_create_inactive_hashed_user() -> None:
    auth_service, session_factory = _build_auth_service()

    created_user = auth_service.create_user(
        email="Analyst@Example.com",
        password="correct-password",
        is_active=False,
    )

    with session_factory() as session:
        stored_user = session.get(UserRecord, created_user.id)
        assert stored_user is not None
        assert stored_user.email == "analyst@example.com"
        assert stored_user.password_hash != "correct-password"
        assert stored_user.password_hash.startswith("$argon2")
        assert stored_user.is_active is False


def test_list_users_returns_existing_users() -> None:
    auth_service, _ = _build_auth_service()
    first_user = auth_service.register_user(
        email="first@example.com",
        password="correct-password",
    )
    second_user = auth_service.register_user(
        email="second@example.com",
        password="correct-password",
    )

    listed_users = auth_service.list_users()

    assert {user.id for user in listed_users} == {first_user.id, second_user.id}
    assert {user.email for user in listed_users} == {
        "first@example.com",
        "second@example.com",
    }


def test_update_user_activation_toggles_login_access() -> None:
    auth_service, _ = _build_auth_service()
    registered_user = auth_service.register_user(
        email="admin@example.com",
        password="correct-password",
    )

    inactive_user = auth_service.update_user_activation(
        user_id=registered_user.id,
        is_active=False,
    )

    assert inactive_user.is_active is False
    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate_user(
            email="admin@example.com",
            password="correct-password",
        )

    active_user = auth_service.update_user_activation(
        user_id=registered_user.id,
        is_active=True,
    )

    assert active_user.is_active is True
    authenticated_user = auth_service.authenticate_user(
        email="admin@example.com",
        password="correct-password",
    )
    assert authenticated_user.id == registered_user.id


def test_update_user_activation_rejects_missing_user() -> None:
    auth_service, _ = _build_auth_service()

    with pytest.raises(UserNotFoundError):
        auth_service.update_user_activation(user_id=999, is_active=True)


def test_authenticate_user_verifies_password() -> None:
    auth_service, _ = _build_auth_service()
    auth_service.register_user(
        email="admin@example.com",
        password="correct-password",
    )

    authenticated_user = auth_service.authenticate_user(
        email="admin@example.com",
        password="correct-password",
    )

    assert authenticated_user.email == "admin@example.com"


def test_authenticate_user_rejects_invalid_password() -> None:
    auth_service, _ = _build_auth_service()
    auth_service.register_user(
        email="admin@example.com",
        password="correct-password",
    )

    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate_user(
            email="admin@example.com",
            password="wrong-password",
        )


def test_access_token_round_trip_loads_active_user() -> None:
    auth_service, _ = _build_auth_service()
    registered_user = auth_service.register_user(
        email="admin@example.com",
        password="correct-password",
    )

    token = auth_service.create_access_token(registered_user)
    token_user = auth_service.get_user_from_token(token)

    assert token_user.id == registered_user.id
    assert token_user.email == "admin@example.com"


def test_invalid_access_token_is_rejected() -> None:
    auth_service, _ = _build_auth_service()

    with pytest.raises(InvalidTokenError):
        auth_service.get_user_from_token("not-a-token")
