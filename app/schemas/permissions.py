from datetime import datetime

from pydantic import BaseModel, Field


class GrantDocumentPermissionRequest(BaseModel):
    user_id: int = Field(..., ge=1)


class GrantDocumentToUserRequest(BaseModel):
    document_id: int = Field(..., ge=1)


class DocumentPermissionResponse(BaseModel):
    id: int
    document_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class RevokeDocumentPermissionResponse(BaseModel):
    document_id: int
    user_id: int
    revoked: bool


class GrantCodeRepositoryPermissionRequest(BaseModel):
    user_id: int = Field(..., ge=1)


class GrantCodeRepositoryToUserRequest(BaseModel):
    repository_id: int = Field(..., ge=1)


class CodeRepositoryPermissionResponse(BaseModel):
    id: int
    repository_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class RevokeCodeRepositoryPermissionResponse(BaseModel):
    repository_id: int
    user_id: int
    revoked: bool
