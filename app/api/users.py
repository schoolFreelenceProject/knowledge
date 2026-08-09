from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_auth_service, get_current_user
from app.schemas.auth import UserResponse
from app.schemas.users import CreateUserRequest, UpdateUserActivationRequest
from app.services.audit_log import audit_log
from app.services.auth_service import (
    AuthPersistenceError,
    AuthService,
    AuthenticatedUser,
    DuplicateUserError,
    InvalidCredentialsError,
    UserNotFoundError,
)


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    current_user: AuthenticatedUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> list[UserResponse]:
    try:
        return [
            UserResponse(**user.__dict__)
            for user in auth_service.list_users()
        ]
    except AuthPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User list failed: {exc}",
        ) from exc


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    request: CreateUserRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = auth_service.create_user(
            email=request.email,
            password=request.password,
            is_active=request.is_active,
        )
        audit_log(
            "user.create",
            user_id=current_user.id,
            target_user_id=user.id,
            target_email=user.email,
            is_active=user.is_active,
        )
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
            detail=f"User creation failed: {exc}",
        ) from exc


@router.patch("/{user_id}/activation", response_model=UserResponse)
def update_user_activation(
    user_id: int,
    request: UpdateUserActivationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = auth_service.update_user_activation(
            user_id=user_id,
            is_active=request.is_active,
        )
        audit_log(
            "user.activation.update",
            user_id=current_user.id,
            target_user_id=user.id,
            target_email=user.email,
            is_active=user.is_active,
        )
        return UserResponse(**user.__dict__)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AuthPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User activation update failed: {exc}",
        ) from exc
