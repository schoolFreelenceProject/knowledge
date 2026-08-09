from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_rag_trace_service
from app.schemas.traces import TraceListResponse, TraceRecord
from app.services.auth_service import AuthenticatedUser
from app.services.rag_trace_service import (
    RAGTraceNotFoundError,
    RAGTracePersistenceError,
    RAGTraceService,
    StoredRAGTrace,
)


router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("", response_model=TraceListResponse)
def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None, ge=1),
    status_filter: Literal["PROCESSING", "SUCCESS", "ERROR"] | None = Query(
        default=None,
        alias="status",
    ),
    retrieval_mode: Literal["vector", "bm25", "hybrid"] | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    trace_service: RAGTraceService = Depends(get_rag_trace_service),
) -> TraceListResponse:
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
        trace_list = trace_service.list_traces(
            limit=limit,
            offset=offset,
            user_id=user_id,
            status=status_filter,
            retrieval_mode=retrieval_mode,
            created_from=created_from,
            created_to=created_to,
        )
        return TraceListResponse(
            items=[_to_trace_record(item) for item in trace_list.items],
            total=trace_list.total,
            limit=trace_list.limit,
            offset=trace_list.offset,
        )
    except RAGTracePersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Trace lookup failed: {exc}",
        ) from exc


@router.get("/{request_id}", response_model=TraceRecord)
def get_trace(
    request_id: str = Path(..., min_length=1),
    current_user: AuthenticatedUser = Depends(get_current_user),
    trace_service: RAGTraceService = Depends(get_rag_trace_service),
) -> TraceRecord:
    _ = current_user
    try:
        return _to_trace_record(trace_service.get_trace_by_request_id(request_id))
    except RAGTraceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RAGTracePersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Trace lookup failed: {exc}",
        ) from exc


def _to_trace_record(trace: StoredRAGTrace) -> TraceRecord:
    return TraceRecord(**trace.__dict__)
