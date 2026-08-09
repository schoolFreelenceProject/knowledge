from pydantic import BaseModel

from app.schemas.auth import RegisterRequest


class CreateUserRequest(RegisterRequest):
    is_active: bool = True


class UpdateUserActivationRequest(BaseModel):
    is_active: bool
