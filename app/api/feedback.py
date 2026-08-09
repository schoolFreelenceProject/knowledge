from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_rag_feedback_service
from app.schemas.feedback import (
    FeedbackListResponse,
    FeedbackRecord,
    FeedbackRequest,
)
from app.services.auth_service import AuthenticatedUser
from app.services.rag_feedback_service import (
    RAGFeedbackPersistenceError,
    RAGFeedbackService,
    RAGFeedbackServiceError,
    RAGFeedbackTargetNotFoundError,
    StoredRAGFeedback,
)


router = APIRouter(prefix="/api", tags=["feedback"])


@router.post(
    "/traces/{request_id}/feedback",
    response_model=FeedbackRecord,
    status_code=status.HTTP_201_CREATED,
)
def submit_trace_feedback(
    feedback_request: FeedbackRequest,
    request_id: str = Path(..., min_length=1),
    current_user: AuthenticatedUser = Depends(get_current_user),
    feedback_service: RAGFeedbackService = Depends(get_rag_feedback_service),
) -> FeedbackRecord:
    try:
        return _to_feedback_record(
            feedback_service.submit_feedback(
                request_id=request_id,
                user_id=current_user.id,
                rating=feedback_request.rating,
                comment=feedback_request.comment,
            )
        )
    except RAGFeedbackTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RAGFeedbackPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Feedback save failed: {exc}",
        ) from exc
    except RAGFeedbackServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/feedback", response_model=FeedbackListResponse)
def list_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None, ge=1),
    rating: int | None = Query(default=None, ge=1, le=5),
    request_id: str | None = Query(default=None, min_length=1),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    feedback_service: RAGFeedbackService = Depends(get_rag_feedback_service),
) -> FeedbackListResponse:
    _ = current_user
    if (
        created_from is not None
        and created_to is not None
        and created_from > created_to
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_from must be before or equal to created_to.",
        )

    try:
        feedback_list = feedback_service.list_feedback(
            limit=limit,
            offset=offset,
            user_id=user_id,
            rating=rating,
            request_id=request_id,
            created_from=created_from,
            created_to=created_to,
        )
        return FeedbackListResponse(
            items=[
                _to_feedback_record(feedback)
                for feedback in feedback_list.items
            ],
            total=feedback_list.total,
            limit=feedback_list.limit,
            offset=feedback_list.offset,
        )
    except RAGFeedbackPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Feedback lookup failed: {exc}",
        ) from exc


def _to_feedback_record(feedback: StoredRAGFeedback) -> FeedbackRecord:
    return FeedbackRecord(**feedback.__dict__)
