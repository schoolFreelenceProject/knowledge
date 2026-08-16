from pathlib import Path

from app.schemas.documents import ChunkMetadata, GeneratedAnswer, RetrievalResult
from app.schemas.evaluation import EvaluationCase, ExpectedSource, FeedbackMetrics
from app.services.evaluation_service import (
    EvaluationService,
    load_evaluation_dataset,
    save_evaluation_report,
)


class FakeRetrievalService:
    def __init__(self, results_by_question):
        self.results_by_question = results_by_question
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query, top_k):
        self.calls.append((query, top_k))
        return self.results_by_question.get(query, [])


class FakeGenerationService:
    def generate_answer(self, question, retrieval_results):
        if retrieval_results:
            return GeneratedAnswer(
                answer=(
                    "Employees may work remotely three days per week with "
                    "manager approval."
                ),
                sources=[],
            )

        return GeneratedAnswer(answer="No matching policy was found.", sources=[])


def _build_result(
    filename: str,
    score: float,
    chunk_index: int = 1,
    content_type: str = "document",
    file_type: str = "markdown",
    language: str | None = None,
    symbol_name: str | None = None,
    symbol_kind: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> RetrievalResult:
    source_path = filename
    return RetrievalResult(
        text="Policy text",
        filename=filename,
        page_number=None,
        score=score,
        content_type=content_type,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=source_path,
            file_type=file_type,
            content_type=content_type,
            page_number=None,
            chunk_index=chunk_index,
            start_char=0,
            end_char=20,
            language=language,
            symbol_name=symbol_name,
            symbol_kind=symbol_kind,
            start_line=start_line,
            end_line=end_line,
        ),
    )


def test_load_evaluation_dataset_supports_extensible_object_format(tmp_path) -> None:
    dataset_path = tmp_path / "rag_eval.json"
    dataset_path.write_text(
        """
        {
          "version": 1,
          "name": "baseline",
          "metadata": {"owner": "qa"},
          "cases": [
            {
              "id": "case-1",
              "question": "What is the remote work policy?",
              "expected_sources": [{"filename": "company_policy.md"}],
              "expected_answer_contains": ["remote"],
              "future_metric": {"enabled": true}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    dataset = load_evaluation_dataset(dataset_path)

    assert dataset.name == "baseline"
    assert dataset.metadata["owner"] == "qa"
    assert len(dataset.cases) == 1
    assert dataset.cases[0].id == "case-1"


def test_evaluation_report_scores_retrieval_and_answer_quality() -> None:
    case = EvaluationCase(
        id="remote-work",
        question="How many remote work days are allowed?",
        expected_sources=[
            ExpectedSource(filename="company_policy.md"),
        ],
        expected_answer_contains=[
            "three days per week",
            "manager approval",
        ],
        top_k=3,
    )
    retrieval_service = FakeRetrievalService(
        {
            case.question: [
                _build_result("hr_policy.md", score=0.72),
                _build_result("company_policy.md", score=0.91),
            ]
        }
    )
    evaluation_service = EvaluationService(
        retrieval_service=retrieval_service,
        generation_service=FakeGenerationService(),
    )

    report = evaluation_service.evaluate_cases(
        cases=[case],
        default_top_k=5,
    )
    result = report.cases[0]

    assert retrieval_service.calls == [(case.question, 3)]
    assert result.retrieval_score.hit is True
    assert result.retrieval_score.expected_source_rank == 2
    assert result.retrieval_score.best_expected_source_score == 0.91
    assert result.answer_score.coverage == 1.0
    assert report.summary.total_cases == 1
    assert report.summary.retrieval_hit_rate == 1.0
    assert report.summary.average_expected_source_rank == 2.0
    assert report.summary.average_best_source_score == 0.91
    assert report.summary.answer_keyword_coverage_rate == 1.0


def test_evaluation_summary_handles_misses_and_keyword_coverage() -> None:
    hit_case = EvaluationCase(
        id="hit",
        question="Remote work?",
        expected_sources=[ExpectedSource(filename="company_policy.md")],
        expected_answer_contains=["three days per week", "not present"],
    )
    miss_case = EvaluationCase(
        id="miss",
        question="Unknown?",
        expected_sources=[ExpectedSource(filename="missing.md")],
        expected_answer_contains=[],
    )
    retrieval_service = FakeRetrievalService(
        {
            hit_case.question: [
                _build_result("company_policy.md", score=0.8),
            ],
            miss_case.question: [
                _build_result("hr_policy.md", score=0.6),
            ],
        }
    )
    evaluation_service = EvaluationService(
        retrieval_service=retrieval_service,
        generation_service=FakeGenerationService(),
    )

    report = evaluation_service.evaluate_cases(
        cases=[hit_case, miss_case],
        default_top_k=5,
    )

    assert report.summary.total_cases == 2
    assert report.summary.retrieval_hit_rate == 0.5
    assert report.summary.average_expected_source_rank == 1.0
    assert report.summary.average_best_source_score == 0.8
    assert report.summary.answer_keyword_coverage_rate == 0.5


def test_evaluation_report_matches_code_sources_by_content_type_and_symbol() -> None:
    case = EvaluationCase(
        id="code-auth",
        question="Where is user authentication implemented?",
        expected_sources=[
            ExpectedSource(
                filename="app/services/auth_service.py",
                content_type="code",
                symbol_name="AuthService",
            ),
        ],
        top_k=2,
    )
    retrieval_service = FakeRetrievalService(
        {
            case.question: [
                _build_result(
                    "app/services/auth_service.py",
                    score=0.88,
                    content_type="document",
                    file_type="markdown",
                ),
                _build_result(
                    "app/services/auth_service.py",
                    score=0.81,
                    content_type="code",
                    file_type="code",
                    language="python",
                    symbol_name="AuthService",
                    symbol_kind="class",
                    start_line=12,
                    end_line=78,
                ),
            ]
        }
    )
    evaluation_service = EvaluationService(
        retrieval_service=retrieval_service,
        generation_service=FakeGenerationService(),
    )

    report = evaluation_service.evaluate_cases(cases=[case], default_top_k=5)
    result = report.cases[0]

    assert result.retrieval_score.hit is True
    assert result.retrieval_score.expected_source_rank == 2
    assert result.retrieved_documents[1].content_type == "code"
    assert result.retrieved_documents[1].symbol_name == "AuthService"
    assert result.retrieved_documents[1].start_line == 12


def test_evaluation_report_matches_japanese_office_source_metadata() -> None:
    case = EvaluationCase(
        id="jp-xlsx-expense",
        question="経費精算の手順は?",
        expected_sources=[
            ExpectedSource(
                filename="勤務表.xlsx",
                source_path="勤務表.xlsx",
                sheet_name="用語",
                cell_range="A1:B2",
            ),
        ],
        top_k=1,
    )
    retrieval_result = _build_result("勤務表.xlsx", score=0.77, file_type="xlsx")
    retrieval_result = retrieval_result.model_copy(
        update={
            "text": "Workbook: 勤務表.xlsx\nSheet: 用語\nRow 2: A=経費精算",
            "metadata": retrieval_result.metadata.model_copy(
                update={
                    "workbook": "勤務表.xlsx",
                    "sheet_name": "用語",
                    "cell_range": "A1:B2",
                    "row_start": 1,
                    "row_end": 2,
                }
            ),
        }
    )
    evaluation_service = EvaluationService(
        retrieval_service=FakeRetrievalService({case.question: [retrieval_result]}),
        generation_service=FakeGenerationService(),
    )

    report = evaluation_service.evaluate_cases(cases=[case], default_top_k=5)
    result = report.cases[0]

    assert result.retrieval_score.hit is True
    assert result.retrieved_documents[0].sheet_name == "用語"
    assert result.retrieved_documents[0].cell_range == "A1:B2"


def test_evaluation_report_supports_optional_feedback_metrics() -> None:
    case = EvaluationCase(
        id="remote-work",
        question="How many remote work days are allowed?",
        expected_sources=[ExpectedSource(filename="company_policy.md")],
    )
    evaluation_service = EvaluationService(
        retrieval_service=FakeRetrievalService({case.question: []}),
        generation_service=FakeGenerationService(),
    )

    report = evaluation_service.evaluate_cases(
        cases=[case],
        feedback_metrics=FeedbackMetrics(
            feedback_count=3,
            average_user_rating=3.5,
            bad_answer_rate=0.25,
            good_answer_rate=0.5,
        ),
    )

    assert report.summary.total_cases == 1
    assert report.summary.feedback_count == 3
    assert report.summary.average_user_rating == 3.5
    assert report.summary.bad_answer_rate == 0.25
    assert report.summary.good_answer_rate == 0.5


def test_save_evaluation_report_writes_json(tmp_path) -> None:
    case = EvaluationCase(
        id="remote-work",
        question="How many remote work days are allowed?",
        expected_sources=[ExpectedSource(filename="company_policy.md")],
    )
    evaluation_service = EvaluationService(
        retrieval_service=FakeRetrievalService({case.question: []}),
        generation_service=FakeGenerationService(),
    )
    report = evaluation_service.evaluate_cases(cases=[case])
    output_path = tmp_path / "reports" / "rag_eval.json"

    save_evaluation_report(report=report, output_path=output_path)

    assert output_path.exists()
    assert '"total_cases": 1' in output_path.read_text(encoding="utf-8")
