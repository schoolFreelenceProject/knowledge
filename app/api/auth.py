from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_auth_service
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    AuthPersistenceError,
    AuthService,
    DuplicateUserError,
    InvalidCredentialsError,
)
from app.services.audit_log import audit_log


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = auth_service.register_user(
            email=request.email,
            password=request.password,
        )
        audit_log("auth.register", user_id=user.id, email=user.email)
        return UserResponse(**user.__dict__)
    except DuplicateUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except AuthPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User registration failed: {exc}",
        ) from exc


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        user = auth_service.authenticate_user(
            email=request.email,
            password=request.password,
        )
        audit_log("auth.login", user_id=user.id, email=user.email)
        return TokenResponse(access_token=auth_service.create_access_token(user))
    except InvalidCredentialsError as exc:
        audit_log(
            "auth.login",
            status="DENIED",
            email=request.email,
            reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User login failed: {exc}",
        ) from exc
