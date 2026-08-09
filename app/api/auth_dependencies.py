from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.auth_service import (
    AuthPersistenceError,
    AuthService,
    AuthenticatedUser,
    InvalidTokenError,
)


BEARER_AUTH_SCHEME = HTTPBearer(auto_error=False)


@lru_cache
def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(
        session_factory=get_session_factory(),
        init_database=init_db,
        jwt_secret_key=settings.jwt_secret_key,
        jwt_algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_AUTH_SCHEME),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return auth_service.get_user_from_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Authentication lookup failed: {exc}",
        ) from exc
