from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import UserRecord


class AuthServiceError(RuntimeError):
    """Raised when an authentication operation fails."""


class DuplicateUserError(AuthServiceError):
    """Raised when a registration email is already in use."""


class InvalidCredentialsError(AuthServiceError):
    """Raised when login credentials are invalid."""


class InvalidTokenError(AuthServiceError):
    """Raised when a bearer token cannot be validated."""


class UserNotFoundError(AuthServiceError):
    """Raised when a managed user cannot be found."""


class AuthPersistenceError(AuthServiceError):
    """Raised when user metadata cannot be read or written."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AuthService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        init_database: Callable[[], None],
        jwt_secret_key: str,
        jwt_algorithm: str,
        access_token_expire_minutes: int,
        password_hash: PasswordHash | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.init_database = init_database
        self.jwt_secret_key = jwt_secret_key
        self.jwt_algorithm = jwt_algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.password_hash = password_hash or PasswordHash.recommended()

    def register_user(self, email: str, password: str) -> AuthenticatedUser:
        return self.create_user(email=email, password=password, is_active=True)

    def create_user(
        self,
        email: str,
        password: str,
        is_active: bool = True,
    ) -> AuthenticatedUser:
        normalized_email = _normalize_email(email)
        password_hash = self.password_hash.hash(password)

        try:
            self.init_database()
            with self.session_factory() as session:
                existing_user = _get_user_by_email(
                    session=session,
                    email=normalized_email,
                )
                if existing_user is not None:
                    raise DuplicateUserError("Email is already registered.")

                user = UserRecord(
                    email=normalized_email,
                    password_hash=password_hash,
                    is_active=is_active,
                )
                session.add(user)
                session.flush()
                authenticated_user = _to_authenticated_user(user)
                session.commit()
                return authenticated_user
        except DuplicateUserError:
            raise
        except IntegrityError as exc:
            raise DuplicateUserError("Email is already registered.") from exc
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(f"Failed to create user: {exc}") from exc

    def list_users(self) -> list[AuthenticatedUser]:
        try:
            self.init_database()
            with self.session_factory() as session:
                users = session.scalars(
                    select(UserRecord).order_by(
                        UserRecord.created_at.desc(),
                        UserRecord.id.desc(),
                    )
                ).all()
                return [_to_authenticated_user(user) for user in users]
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(f"Failed to list users: {exc}") from exc

    def update_user_activation(
        self,
        user_id: int,
        is_active: bool,
    ) -> AuthenticatedUser:
        try:
            self.init_database()
            with self.session_factory() as session:
                user = session.get(UserRecord, user_id)
                if user is None:
                    raise UserNotFoundError(f"User {user_id} was not found.")

                user.is_active = is_active
                session.flush()
                authenticated_user = _to_authenticated_user(user)
                session.commit()
                return authenticated_user
        except UserNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(
                f"Failed to update user activation: {exc}"
            ) from exc

    def authenticate_user(self, email: str, password: str) -> AuthenticatedUser:
        normalized_email = _normalize_email(email)

        try:
            self.init_database()
            with self.session_factory() as session:
                user = _get_user_by_email(session=session, email=normalized_email)
                if user is None or not user.is_active:
                    raise InvalidCredentialsError("Invalid email or password.")

                try:
                    password_is_valid = self.password_hash.verify(
                        password,
                        user.password_hash,
                    )
                except Exception as exc:
                    raise InvalidCredentialsError("Invalid email or password.") from exc

                if not password_is_valid:
                    raise InvalidCredentialsError("Invalid email or password.")

                return _to_authenticated_user(user)
        except InvalidCredentialsError:
            raise
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(f"Failed to authenticate user: {exc}") from exc

    def create_access_token(self, user: AuthenticatedUser) -> str:
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": issued_at,
            "exp": expires_at,
        }
        return jwt.encode(
            payload,
            self.jwt_secret_key,
            algorithm=self.jwt_algorithm,
        )

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret_key,
                algorithms=[self.jwt_algorithm],
            )
            subject = payload.get("sub")
            if subject is None:
                raise InvalidTokenError("Token subject is missing.")

            user_id = int(subject)
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise InvalidTokenError("Invalid bearer token.") from exc

        try:
            self.init_database()
            with self.session_factory() as session:
                user = session.get(UserRecord, user_id)
                if user is None or not user.is_active:
                    raise InvalidTokenError("Invalid bearer token.")

                return _to_authenticated_user(user)
        except InvalidTokenError:
            raise
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(f"Failed to load authenticated user: {exc}") from exc

    def get_active_user_by_email(self, email: str) -> AuthenticatedUser:
        normalized_email = _normalize_email(email)

        try:
            self.init_database()
            with self.session_factory() as session:
                user = _get_user_by_email(session=session, email=normalized_email)
                if user is None or not user.is_active:
                    raise InvalidTokenError("Configured service account is invalid.")

                return _to_authenticated_user(user)
        except InvalidTokenError:
            raise
        except SQLAlchemyError as exc:
            raise AuthPersistenceError(
                f"Failed to load service account user: {exc}"
            ) from exc


def _get_user_by_email(session: Session, email: str) -> UserRecord | None:
    return session.scalars(
        select(UserRecord).where(UserRecord.email == email)
    ).one_or_none()


def _normalize_email(email: str) -> str:
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise InvalidCredentialsError("Email is invalid.")

    return normalized_email


def _to_authenticated_user(user: UserRecord) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
