from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RAGFeedbackRecord, RAGTraceRecord, UserRecord
from app.services.evaluation_service import load_evaluation_dataset
from app.services.feedback_evaluation_service import FeedbackEvaluationService


def _build_feedback_evaluation_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        FeedbackEvaluationService(
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
    question: str,
) -> int:
    with session_factory() as session:
        trace = RAGTraceRecord(
            request_id=request_id,
            user_id=user_id,
            question=question,
            retrieval_mode=retrieval_mode,
            retrieval_time_ms=10.0,
            reranker_time_ms=5.0,
            generation_time_ms=20.0,
            total_time_ms=35.0,
            model_name="llama3.1:8b",
            retrieved_count=1,
            status=status,
            retrieved_sources=[
                {
                    "filename": "company_policy.md",
                    "score": 0.91,
                }
            ],
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
    comment: str | None = None,
) -> None:
    with session_factory() as session:
        session.add(
            RAGFeedbackRecord(
                trace_id=trace_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
                created_at=created_at,
            )
        )
        session.commit()


def test_calculate_feedback_metrics_handles_zero_feedback() -> None:
    service, _session_factory = _build_feedback_evaluation_service()

    metrics = service.calculate_feedback_metrics()

    assert metrics.feedback_count == 0
    assert metrics.average_user_rating is None
    assert metrics.bad_answer_rate is None
    assert metrics.good_answer_rate is None


def test_calculate_feedback_metrics_counts_average_bad_and_good_rates() -> None:
    service, session_factory = _build_feedback_evaluation_service()
    _insert_user(session_factory, 1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    trace_id = _insert_trace(
        session_factory,
        request_id="req-1",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time,
        question="What is the remote work policy?",
    )
    _insert_feedback(session_factory, trace_id, user_id=1, rating=1, created_at=base_time)
    _insert_feedback(
        session_factory,
        trace_id,
        user_id=1,
        rating=3,
        created_at=base_time + timedelta(minutes=1),
    )
    _insert_feedback(
        session_factory,
        trace_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=2),
    )

    metrics = service.calculate_feedback_metrics()

    assert metrics.feedback_count == 3
    assert metrics.average_user_rating == 3.0
    assert metrics.bad_answer_rate == 1 / 3
    assert metrics.good_answer_rate == 1 / 3


def test_calculate_feedback_metrics_applies_filters() -> None:
    service, session_factory = _build_feedback_evaluation_service()
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
        question="How many remote work days are allowed?",
    )
    other_trace_id = _insert_trace(
        session_factory,
        request_id="req-2",
        user_id=2,
        retrieval_mode="vector",
        status="ERROR",
        created_at=base_time,
        question="What is the expense policy?",
    )
    _insert_feedback(
        session_factory,
        matching_trace_id,
        user_id=1,
        rating=2,
        created_at=base_time + timedelta(minutes=5),
    )
    _insert_feedback(
        session_factory,
        other_trace_id,
        user_id=2,
        rating=5,
        created_at=base_time + timedelta(minutes=10),
    )

    metrics = service.calculate_feedback_metrics(
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_from=base_time + timedelta(minutes=1),
        created_to=base_time + timedelta(minutes=6),
    )

    assert metrics.feedback_count == 1
    assert metrics.average_user_rating == 2.0
    assert metrics.bad_answer_rate == 1.0
    assert metrics.good_answer_rate == 0.0


def test_export_failed_query_dataset_uses_existing_evaluation_schema(tmp_path) -> None:
    service, session_factory = _build_feedback_evaluation_service()
    _insert_user(session_factory, 1)
    base_time = datetime(2026, 8, 9, tzinfo=timezone.utc)
    failed_trace_id = _insert_trace(
        session_factory,
        request_id="req-failed",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time,
        question="What is the remote work policy?",
    )
    good_trace_id = _insert_trace(
        session_factory,
        request_id="req-good",
        user_id=1,
        retrieval_mode="hybrid",
        status="SUCCESS",
        created_at=base_time + timedelta(minutes=1),
        question="What is the leave policy?",
    )
    _insert_feedback(
        session_factory,
        failed_trace_id,
        user_id=1,
        rating=2,
        created_at=base_time + timedelta(minutes=2),
        comment="Wrong document cited.",
    )
    _insert_feedback(
        session_factory,
        good_trace_id,
        user_id=1,
        rating=5,
        created_at=base_time + timedelta(minutes=3),
    )

    dataset = service.export_failed_query_dataset(max_rating=2)
    dataset_path = tmp_path / "failed_queries.json"
    dataset_path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    loaded_dataset = load_evaluation_dataset(dataset_path)

    assert len(loaded_dataset.cases) == 1
    case = loaded_dataset.cases[0]
    assert case.question == "What is the remote work policy?"
    assert case.expected_sources == []
    assert case.expected_answer_contains == []
    assert case.metadata["request_id"] == "req-failed"
    assert case.metadata["trace_id"] == failed_trace_id
    assert case.metadata["rating"] == 2
    assert case.metadata["comment"] == "Wrong document cited."
    assert case.metadata["retrieved_sources"][0]["filename"] == "company_policy.md"
