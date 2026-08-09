from datetime import datetime

from pydantic import BaseModel, Field


class GrantDocumentPermissionRequest(BaseModel):
    user_id: int = Field(..., ge=1)


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
