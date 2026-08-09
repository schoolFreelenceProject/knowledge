from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RAGFeedbackRecord, RAGTraceRecord, UserRecord
from app.services.rag_analytics_service import RAGAnalyticsService


def _build_analytics_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        RAGAnalyticsService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _insert_user(session_factory, user_id: int) -> None:
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
    retrieval_mode: str,
    status: str,
    created_at: datetime,
    total_time_ms: float | None,
    retrieved_sources: list[dict] | None = None,
) -> int:
    with session_factory() as session:
        trace = RAGTraceRecord(
            request_id=request_id,
            user_id=user_id,
            question=f"Question for {request_id}",
            retrieval_mode=retrieval_mode,
            retrieval_time_ms=10.0,
            reranker_time_ms=5.0,
            generation_time_ms=20.0,
            total_time_ms=total_time_ms,
            model_name="llama3.1:8b",
            retrieved_count=len(retrieved_sources or []),
            status=status,
            retrieved_sources=retrieved_sources or [],
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


def test_summary_handles_empty_tables() -> None:
    analytics_service, _session_factory = _build_analytics_service()

    summary = analytics_service.get_summary()

    assert summary.total_questions == 0
    assert summary.average_latency_ms is None
    assert summary.feedback_count == 0
    assert summary.average_user_rating is None
    assert summary.bad_answer_rate is None
    assert summary.good_answer_rate is None


def test_summary_calculates_question_latency_and_feedback_metrics() -> None:
    analytics_service, session_factory = _build_analytics_service()
    _insert_user(session_factory, 1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    trace_one_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        retrieval_mode="vector",
        status="SUCCESS",
        created_at=base_time,
        total_time_ms=100.0,
    )
    trace_two_id = _insert_trace(
        session_factory,
        request_id="req-2",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=1),
        total_time_ms=200.0,
    )
    _insert_feedback(
        session_factory,
        trace_id=trace_one_id,
        user_id=1,
        rating=1,
        created_at=base_time + timedelta(minutes=2),
    )
    _insert_feedback(
        session_factory,
        trace_id=trace_two_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=3),
    )

    summary = analytics_service.get_summary()

    assert summary.total_questions == 2
    assert summary.average_latency_ms == 150.0
    assert summary.feedback_count == 2
    assert summary.average_user_rating == 3.0
    assert summary.bad_answer_rate == 0.5
    assert summary.good_answer_rate == 0.5


def test_feedback_analytics_returns_rating_distribution_and_filters() -> None:
    analytics_service, session_factory = _build_analytics_service()
    _insert_user(session_factory, 1)
    _insert_user(session_factory, 2)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    matching_trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time,
        total_time_ms=80.0,
    )
    other_trace_id = _insert_trace(
        session_factory,
        request_id="req-2",
        user_id=2,
        retrieval_mode="vector",
        status="ERROR",
        created_at=base_time,
        total_time_ms=90.0,
    )
    _insert_feedback(
        session_factory,
        trace_id=matching_trace_id,
        user_id=1,
        rating=2,
        created_at=base_time + timedelta(minutes=1),
    )
    _insert_feedback(
        session_factory,
        trace_id=matching_trace_id,
        user_id=1,
        rating=4,
        created_at=base_time + timedelta(minutes=2),
    )
    _insert_feedback(
        session_factory,
        trace_id=other_trace_id,
        user_id=2,
        rating=5,
        created_at=base_time + timedelta(minutes=3),
    )

    feedback = analytics_service.get_feedback_analytics(
        user_id=1,
        status="SUCCESS",
        retrieval_mode="hybrid",
        created_from=base_time + timedelta(seconds=30),
        created_to=base_time + timedelta(minutes=3),
    )

    assert feedback.feedback_count == 2
    assert feedback.average_user_rating == 3.0
    assert feedback.bad_answer_rate == 0.5
    assert feedback.good_answer_rate == 0.5
    assert [item.count for item in feedback.rating_distribution] == [0, 1, 0, 1, 0]


def test_retrieval_analytics_groups_modes_and_top_failed_documents() -> None:
    analytics_service, session_factory = _build_analytics_service()
    _insert_user(session_factory, 1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    failed_trace_one_id = _insert_trace(
        session_factory,
        request_id="req-fail-1",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time,
        total_time_ms=120.0,
        retrieved_sources=[
            {"filename": "company_policy.md", "score": 0.9},
            {"filename": "company_policy.md", "score": 0.7},
            {"filename": "expense_policy.md", "score": 0.3},
        ],
    )
    failed_trace_two_id = _insert_trace(
        session_factory,
        request_id="req-fail-2",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=1),
        total_time_ms=180.0,
        retrieved_sources=[
            {"filename": "company_policy.md", "score": 0.5},
            {
                "source_path": "data/documents/it_security_policy.md",
                "score": None,
            },
        ],
    )
    good_trace_id = _insert_trace(
        session_factory,
        request_id="req-good",
        user_id=1,
        retrieval_mode="vector",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=2),
        total_time_ms=90.0,
        retrieved_sources=[{"filename": "hr_policy.md", "score": 0.95}],
    )
    _insert_feedback(
        session_factory,
        trace_id=failed_trace_one_id,
        user_id=1,
        rating=1,
        created_at=base_time + timedelta(minutes=3),
    )
    _insert_feedback(
        session_factory,
        trace_id=failed_trace_two_id,
        user_id=1,
        rating=2,
        created_at=base_time + timedelta(minutes=4),
    )
    _insert_feedback(
        session_factory,
        trace_id=good_trace_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=5),
    )

    retrieval = analytics_service.get_retrieval_analytics(top_failed_limit=2)

    assert retrieval.total_questions == 3
    assert [
        (item.retrieval_mode, item.count, item.rate)
        for item in retrieval.retrieval_mode_distribution
    ] == [
        ("hybrid", 2, pytest.approx(2 / 3)),
        ("vector", 1, pytest.approx(1 / 3)),
    ]
    assert retrieval.retrieval_mode_distribution[0].average_latency_ms == 150.0
    assert retrieval.top_failed_documents[0].filename == "company_policy.md"
    assert retrieval.top_failed_documents[0].failure_count == 2
    assert retrieval.top_failed_documents[0].average_retrieval_score == pytest.approx(
        0.65
    )
    assert retrieval.top_failed_documents[1].filename == "expense_policy.md"
    assert retrieval.top_failed_documents[1].failure_count == 1


def test_retrieval_analytics_applies_trace_filters() -> None:
    analytics_service, session_factory = _build_analytics_service()
    _insert_user(session_factory, 1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    _insert_trace(
        session_factory,
        request_id="req-match",
        user_id=1,
        retrieval_mode="bm25",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=2),
        total_time_ms=40.0,
    )
    _insert_trace(
        session_factory,
        request_id="req-other-mode",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=2),
        total_time_ms=50.0,
    )
    _insert_trace(
        session_factory,
        request_id="req-other-status",
        user_id=1,
        retrieval_mode="bm25",
        status="ERROR",
        created_at=base_time + timedelta(minutes=2),
        total_time_ms=60.0,
    )

    retrieval = analytics_service.get_retrieval_analytics(
        user_id=1,
        status="SUCCESS",
        retrieval_mode="bm25",
        created_from=base_time + timedelta(minutes=1),
        created_to=base_time + timedelta(minutes=3),
    )

    assert retrieval.total_questions == 1
    assert len(retrieval.retrieval_mode_distribution) == 1
    assert retrieval.retrieval_mode_distribution[0].retrieval_mode == "bm25"
    assert retrieval.retrieval_mode_distribution[0].count == 1
