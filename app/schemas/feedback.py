from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None

    model_config = {"extra": "allow"}


class FeedbackRecord(BaseModel):
    id: int
    trace_id: int
    request_id: str
    user_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: str | None
    created_at: datetime

    model_config = {"extra": "allow"}


class FeedbackListResponse(BaseModel):
    items: list[FeedbackRecord]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

    model_config = {"extra": "allow"}
