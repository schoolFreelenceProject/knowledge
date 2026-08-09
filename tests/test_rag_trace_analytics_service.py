from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RAGTraceRecord
from app.services.rag_trace_service import RAGTraceNotFoundError, RAGTraceService


def _build_trace_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        RAGTraceService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _insert_trace(
    session_factory,
    request_id: str,
    user_id: int,
    status: str,
    retrieval_mode: str,
    created_at: datetime,
    question: str = "What is the remote work policy?",
) -> None:
    with session_factory() as session:
        session.add(
            RAGTraceRecord(
                request_id=request_id,
                user_id=user_id,
                question=question,
                retrieval_mode=retrieval_mode,
                retrieval_time_ms=10.0,
                reranker_time_ms=None,
                generation_time_ms=20.0,
                total_time_ms=30.0,
                model_name="llama3.1:8b",
                retrieved_count=1,
                status=status,
                error_message=None,
                prompt_tokens=None,
                completion_tokens=None,
                retrieved_sources=[
                    {
                        "filename": "company_policy.md",
                        "score": 0.91,
                    }
                ],
                created_at=created_at,
            )
        )
        session.commit()


def test_list_traces_paginates_and_orders_newest_first() -> None:
    trace_service, session_factory = _build_trace_service()
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    _insert_trace(session_factory, "req-old", 1, "SUCCESS", "vector", base_time)
    _insert_trace(
        session_factory,
        "req-middle",
        1,
        "SUCCESS",
        "hybrid",
        base_time + timedelta(minutes=1),
    )
    _insert_trace(
        session_factory,
        "req-new",
        2,
        "ERROR",
        "bm25",
        base_time + timedelta(minutes=2),
    )

    trace_list = trace_service.list_traces(limit=2, offset=0)

    assert trace_list.total == 3
    assert trace_list.limit == 2
    assert trace_list.offset == 0
    assert [trace.request_id for trace in trace_list.items] == [
        "req-new",
        "req-middle",
    ]


def test_list_traces_filters_by_user_status_mode_and_date_range() -> None:
    trace_service, session_factory = _build_trace_service()
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    _insert_trace(session_factory, "req-1", 1, "SUCCESS", "vector", base_time)
    _insert_trace(
        session_factory,
        "req-2",
        1,
        "ERROR",
        "hybrid",
        base_time + timedelta(hours=1),
    )
    _insert_trace(
        session_factory,
        "req-3",
        2,
        "SUCCESS",
        "hybrid",
        base_time + timedelta(hours=2),
    )

    trace_list = trace_service.list_traces(
        limit=10,
        offset=0,
        user_id=1,
        status="ERROR",
        retrieval_mode="hybrid",
        created_from=base_time + timedelta(minutes=30),
        created_to=base_time + timedelta(hours=90),
    )

    assert trace_list.total == 1
    assert [trace.request_id for trace in trace_list.items] == ["req-2"]


def test_get_trace_by_request_id_returns_newest_duplicate() -> None:
    trace_service, session_factory = _build_trace_service()
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    _insert_trace(
        session_factory,
        "duplicate-req",
        1,
        "SUCCESS",
        "vector",
        base_time,
        question="Older question",
    )
    _insert_trace(
        session_factory,
        "duplicate-req",
        1,
        "ERROR",
        "hybrid",
        base_time + timedelta(minutes=1),
        question="Newest question",
    )

    trace = trace_service.get_trace_by_request_id("duplicate-req")

    assert trace.question == "Newest question"
    assert trace.status == "ERROR"
    assert trace.retrieval_mode == "hybrid"


def test_get_trace_by_request_id_raises_for_missing_trace() -> None:
    trace_service, _session_factory = _build_trace_service()

    with pytest.raises(RAGTraceNotFoundError):
        trace_service.get_trace_by_request_id("missing-request")
