from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsFilters(BaseModel):
    user_id: int | None = None
    status: str | None = None
    retrieval_mode: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None

    model_config = {"extra": "allow"}


class RatingDistributionItem(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    count: int = Field(..., ge=0)
    rate: float | None = None

    model_config = {"extra": "allow"}


class RetrievalModeDistributionItem(BaseModel):
    retrieval_mode: str
    count: int = Field(..., ge=0)
    rate: float | None = None
    average_latency_ms: float | None = None

    model_config = {"extra": "allow"}


class TopFailedDocument(BaseModel):
    filename: str
    failure_count: int = Field(..., ge=0)
    average_retrieval_score: float | None = None
    source_path: str | None = None

    model_config = {"extra": "allow"}


class AnalyticsSummaryResponse(BaseModel):
    total_questions: int = Field(..., ge=0)
    average_latency_ms: float | None = None
    feedback_count: int = Field(..., ge=0)
    average_user_rating: float | None = None
    bad_answer_rate: float | None = None
    good_answer_rate: float | None = None
    filters: AnalyticsFilters

    model_config = {"extra": "allow"}


class AnalyticsFeedbackResponse(BaseModel):
    feedback_count: int = Field(..., ge=0)
    average_user_rating: float | None = None
    bad_answer_rate: float | None = None
    good_answer_rate: float | None = None
    rating_distribution: list[RatingDistributionItem] = Field(default_factory=list)
    filters: AnalyticsFilters

    model_config = {"extra": "allow"}


class AnalyticsRetrievalResponse(BaseModel):
    total_questions: int = Field(..., ge=0)
    retrieval_mode_distribution: list[RetrievalModeDistributionItem] = Field(
        default_factory=list
    )
    top_failed_documents: list[TopFailedDocument] = Field(default_factory=list)
    filters: AnalyticsFilters

    model_config = {"extra": "allow"}
