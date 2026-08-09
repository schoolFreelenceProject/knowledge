import sys

from app.schemas.evaluation import EvaluationCase, EvaluationDataset
from app.services.evaluation_service import load_evaluation_dataset
from scripts import export_failed_queries


class FakeFeedbackEvaluationService:
    export_call: dict | None = None

    def __init__(self, session_factory, init_database) -> None:
        self.session_factory = session_factory
        self.init_database = init_database

    def export_failed_query_dataset(
        self,
        max_rating,
        limit,
        offset,
        user_id=None,
        retrieval_mode=None,
        status=None,
        created_from=None,
        created_to=None,
    ):
        FakeFeedbackEvaluationService.export_call = {
            "max_rating": max_rating,
            "limit": limit,
            "offset": offset,
            "user_id": user_id,
            "retrieval_mode": retrieval_mode,
            "status": status,
            "created_from": created_from,
            "created_to": created_to,
        }
        return EvaluationDataset(
            version=1,
            name="Feedback failed queries",
            cases=[
                EvaluationCase(
                    id="feedback-1-trace-10",
                    question="What is the remote work policy?",
                    metadata={"request_id": "req-1", "rating": 2},
                )
            ],
            metadata={"source": "rag_feedback"},
        )


def test_export_failed_queries_writes_compatible_dataset(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "failed_queries.json"
    monkeypatch.setattr(
        export_failed_queries,
        "FeedbackEvaluationService",
        FakeFeedbackEvaluationService,
    )
    monkeypatch.setattr(export_failed_queries, "get_session_factory", lambda: None)
    monkeypatch.setattr(export_failed_queries, "init_db", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_failed_queries.py",
            "--output",
            str(output_path),
            "--max-rating",
            "2",
            "--limit",
            "25",
            "--offset",
            "5",
            "--user-id",
            "1",
            "--retrieval-mode",
            "hybrid",
            "--status",
            "SUCCESS",
        ],
    )

    exit_code = export_failed_queries.main()
    dataset = load_evaluation_dataset(output_path)

    assert exit_code == 0
    assert dataset.cases[0].question == "What is the remote work policy?"
    assert FakeFeedbackEvaluationService.export_call == {
        "max_rating": 2,
        "limit": 25,
        "offset": 5,
        "user_id": 1,
        "retrieval_mode": "hybrid",
        "status": "SUCCESS",
        "created_from": None,
        "created_to": None,
    }


def test_export_failed_queries_rejects_invalid_max_rating(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_failed_queries.py",
            "--max-rating",
            "6",
        ],
    )

    assert export_failed_queries.main() == 1
