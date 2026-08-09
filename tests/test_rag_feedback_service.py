from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RAGFeedbackRecord, RAGTraceRecord, UserRecord
from app.services.rag_feedback_service import (
    RAGFeedbackService,
    RAGFeedbackServiceError,
    RAGFeedbackTargetNotFoundError,
)


def _build_feedback_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        RAGFeedbackService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _insert_user(session_factory, user_id: int = 1) -> None:
    with session_factory() as session:
        session.add(
            UserRecord(
                id=user_id,
                email=f"user-{user_id}@example.com",
                password_hash="$argon2id$hash",
            )
        )
        session.commit()


def _insert_trace(
    session_factory,
    request_id: str,
    user_id: int,
    created_at: datetime,
    question: str = "What is the remote work policy?",
) -> int:
    with session_factory() as session:
        trace = RAGTraceRecord(
            request_id=request_id,
            user_id=user_id,
            question=question,
            retrieval_mode="hybrid",
            retrieval_time_ms=10.0,
            reranker_time_ms=5.0,
            generation_time_ms=20.0,
            total_time_ms=35.0,
            model_name="llama3.1:8b",
            retrieved_count=1,
            status="SUCCESS",
            retrieved_sources=[],
            created_at=created_at,
        )
        session.add(trace)
        session.commit()
        return trace.id


def _insert_feedback(
    session_factory,
    trace_id: int,
    user_id: int,
    rating: int,
    created_at: datetime,
) -> None:
    with session_factory() as session:
        session.add(
            RAGFeedbackRecord(
                trace_id=trace_id,
                user_id=user_id,
                rating=rating,
                comment=f"rating {rating}",
                created_at=created_at,
            )
        )
        session.commit()


def test_submit_feedback_links_to_newest_duplicate_trace() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    older_trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=base_time,
        question="Older trace",
    )
    newest_trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=base_time + timedelta(minutes=1),
        question="Newest trace",
    )

    feedback = feedback_service.submit_feedback(
        request_id="req-1",
        user_id=1,
        rating=5,
        comment=" Accurate answer. ",
    )

    assert feedback.trace_id == newest_trace_id
    assert feedback.trace_id != older_trace_id
    assert feedback.request_id == "req-1"
    assert feedback.rating == 5
    assert feedback.comment == "Accurate answer."


def test_submit_feedback_is_append_only() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)
    _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    feedback_service.submit_feedback("req-1", user_id=1, rating=4)
    feedback_service.submit_feedback("req-1", user_id=1, rating=5)

    with session_factory() as session:
        feedback_rows = session.scalars(select(RAGFeedbackRecord)).all()
        assert [feedback.rating for feedback in feedback_rows] == [4, 5]


def test_submit_feedback_requires_existing_trace() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)

    with pytest.raises(RAGFeedbackTargetNotFoundError):
        feedback_service.submit_feedback(
            request_id="missing",
            user_id=1,
            rating=5,
        )


def test_submit_feedback_validates_rating_range() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)
    _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    with pytest.raises(RAGFeedbackServiceError):
        feedback_service.submit_feedback("req-1", user_id=1, rating=6)


def test_list_feedback_paginates_and_filters() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)
    _insert_user(session_factory, user_id=2)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    req_one_trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=base_time,
    )
    req_two_trace_id = _insert_trace(
        session_factory,
        request_id="req-2",
        user_id=2,
        created_at=base_time + timedelta(minutes=1),
    )
    _insert_feedback(
        session_factory,
        trace_id=req_one_trace_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=2),
    )
    _insert_feedback(
        session_factory,
        trace_id=req_two_trace_id,
        user_id=2,
        rating=2,
        created_at=base_time + timedelta(minutes=3),
    )
    _insert_feedback(
        session_factory,
        trace_id=req_one_trace_id,
        user_id=1,
        rating=3,
        created_at=base_time + timedelta(minutes=4),
    )

    feedback_list = feedback_service.list_feedback(
        limit=10,
        offset=0,
        user_id=1,
        rating=5,
        request_id="req-1",
        created_from=base_time + timedelta(minutes=1),
        created_to=base_time + timedelta(minutes=3),
    )

    assert feedback_list.total == 1
    assert feedback_list.items[0].request_id == "req-1"
    assert feedback_list.items[0].user_id == 1
    assert feedback_list.items[0].rating == 5


def test_list_feedback_orders_newest_first() -> None:
    feedback_service, session_factory = _build_feedback_service()
    _insert_user(session_factory, user_id=1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        created_at=base_time,
    )
    _insert_feedback(
        session_factory,
        trace_id=trace_id,
        user_id=1,
        rating=3,
        created_at=base_time + timedelta(minutes=1),
    )
    _insert_feedback(
        session_factory,
        trace_id=trace_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=2),
    )

    feedback_list = feedback_service.list_feedback(limit=1, offset=0)

    assert feedback_list.total == 2
    assert feedback_list.limit == 1
    assert feedback_list.items[0].rating == 5
