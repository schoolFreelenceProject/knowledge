import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.schemas.documents import RetrievalResult
from app.schemas.evaluation import (
    AnswerScore,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationReport,
    EvaluationSummary,
    ExpectedSource,
    FeedbackMetrics,
    RetrievedDocument,
    RetrievalScore,
)
from app.services.generation_service import RAGGenerationService
from app.services.retrieval_service import RetrievalService


class EvaluationServiceError(RuntimeError):
    """Raised when RAG evaluation cannot be completed."""


class EvaluationDatasetError(EvaluationServiceError):
    """Raised when an evaluation dataset cannot be loaded."""


class EvaluationService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        generation_service: RAGGenerationService,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service

    def evaluate_cases(
        self,
        cases: Iterable[EvaluationCase],
        default_top_k: int = 5,
        metadata: dict[str, Any] | None = None,
        feedback_metrics: FeedbackMetrics | None = None,
    ) -> EvaluationReport:
        case_results = [
            self.evaluate_case(case=case, default_top_k=default_top_k)
            for case in cases
        ]
        return EvaluationReport(
            generated_at=datetime.now(timezone.utc),
            summary=_build_summary(
                case_results=case_results,
                feedback_metrics=feedback_metrics,
            ),
            cases=case_results,
            metadata=metadata or {},
        )

    def evaluate_case(
        self,
        case: EvaluationCase,
        default_top_k: int = 5,
    ) -> EvaluationCaseResult:
        top_k = case.top_k or default_top_k
        retrieval_results = self.retrieval_service.retrieve(
            query=case.question,
            top_k=top_k,
        )
        generated_answer = self.generation_service.generate_answer(
            question=case.question,
            retrieval_results=retrieval_results,
        )

        return EvaluationCaseResult(
            id=case.id,
            question=case.question,
            expected_sources=case.expected_sources,
            retrieved_documents=_build_retrieved_documents(retrieval_results),
            retrieval_score=_score_retrieval(
                expected_sources=case.expected_sources,
                retrieval_results=retrieval_results,
            ),
            answer_output=generated_answer.answer,
            answer_score=_score_answer_keywords(
                answer=generated_answer.answer,
                expected_keywords=case.expected_answer_contains,
            ),
        )


def load_evaluation_dataset(dataset_path: str | Path) -> EvaluationDataset:
    path = Path(dataset_path)
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationDatasetError(
            f"Failed to read evaluation dataset '{path}': {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EvaluationDatasetError(
            f"Evaluation dataset '{path}' is not valid JSON: {exc}"
        ) from exc

    try:
        if isinstance(raw_payload, list):
            cases = TypeAdapter(list[EvaluationCase]).validate_python(raw_payload)
            return EvaluationDataset(cases=cases)

        return EvaluationDataset.model_validate(raw_payload)
    except ValidationError as exc:
        raise EvaluationDatasetError(
            f"Evaluation dataset '{path}' has an invalid format: {exc}"
        ) from exc


def save_evaluation_report(
    report: EvaluationReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise EvaluationServiceError(
            f"Failed to write evaluation report '{path}': {exc}"
        ) from exc


def _build_retrieved_documents(
    retrieval_results: list[RetrievalResult],
) -> list[RetrievedDocument]:
    return [
        RetrievedDocument(
            rank=rank,
            content_type=result.metadata.content_type,
            filename=result.filename,
            source_path=result.metadata.source_path,
            file_type=result.metadata.file_type,
            page_number=result.page_number,
            section_heading=result.metadata.section_heading,
            heading_path=result.metadata.heading_path,
            workbook=result.metadata.workbook,
            sheet_name=result.metadata.sheet_name,
            cell_range=result.metadata.cell_range,
            row_start=result.metadata.row_start,
            row_end=result.metadata.row_end,
            slide_number=result.metadata.slide_number,
            slide_title=result.metadata.slide_title,
            chunk_index=result.metadata.chunk_index,
            language=result.metadata.language,
            symbol_name=result.metadata.symbol_name,
            symbol_kind=result.metadata.symbol_kind,
            start_line=result.metadata.start_line,
            end_line=result.metadata.end_line,
            score=result.score,
            vector_score=result.vector_score,
            bm25_score=result.bm25_score,
            fusion_score=result.fusion_score,
            reranker_score=result.reranker_score,
        )
        for rank, result in enumerate(retrieval_results, start=1)
    ]


def _score_retrieval(
    expected_sources: list[ExpectedSource],
    retrieval_results: list[RetrievalResult],
) -> RetrievalScore:
    matching_results = [
        (rank, result)
        for rank, result in enumerate(retrieval_results, start=1)
        if _matches_any_expected_source(
            expected_sources=expected_sources,
            retrieval_result=result,
        )
    ]
    if not matching_results:
        return RetrievalScore(hit=False)

    return RetrievalScore(
        hit=True,
        expected_source_rank=min(rank for rank, _result in matching_results),
        best_expected_source_score=max(
            result.score for _rank, result in matching_results
        ),
    )


def _matches_any_expected_source(
    expected_sources: list[ExpectedSource],
    retrieval_result: RetrievalResult,
) -> bool:
    return any(
        _matches_expected_source(
            expected_source=expected_source,
            retrieval_result=retrieval_result,
        )
        for expected_source in expected_sources
    )


def _matches_expected_source(
    expected_source: ExpectedSource,
    retrieval_result: RetrievalResult,
) -> bool:
    metadata = retrieval_result.metadata
    if expected_source.source_path is not None:
        source_matches = metadata.source_path == expected_source.source_path
    else:
        source_matches = retrieval_result.filename == expected_source.filename

    if not source_matches:
        return False

    if (
        expected_source.content_type is not None
        and metadata.content_type != expected_source.content_type
    ):
        return False

    if (
        expected_source.symbol_name is not None
        and metadata.symbol_name != expected_source.symbol_name
    ):
        return False

    if (
        expected_source.section_heading is not None
        and metadata.section_heading != expected_source.section_heading
    ):
        return False

    if (
        expected_source.sheet_name is not None
        and metadata.sheet_name != expected_source.sheet_name
    ):
        return False

    if (
        expected_source.cell_range is not None
        and metadata.cell_range != expected_source.cell_range
    ):
        return False

    if (
        expected_source.slide_number is not None
        and metadata.slide_number != expected_source.slide_number
    ):
        return False

    if expected_source.page_number is not None:
        return retrieval_result.page_number == expected_source.page_number

    return True


def _score_answer_keywords(
    answer: str,
    expected_keywords: list[str],
) -> AnswerScore:
    normalized_answer = answer.casefold()
    normalized_keywords = [
        keyword.strip()
        for keyword in expected_keywords
        if keyword.strip()
    ]
    found_keywords = [
        keyword
        for keyword in normalized_keywords
        if keyword.casefold() in normalized_answer
    ]
    missing_keywords = [
        keyword
        for keyword in normalized_keywords
        if keyword.casefold() not in normalized_answer
    ]
    total = len(normalized_keywords)
    coverage = len(found_keywords) / total if total else None

    return AnswerScore(
        expected_keywords_found=len(found_keywords),
        expected_keywords_total=total,
        coverage=coverage,
        found_keywords=found_keywords,
        missing_keywords=missing_keywords,
    )


def _build_summary(
    case_results: list[EvaluationCaseResult],
    feedback_metrics: FeedbackMetrics | None = None,
) -> EvaluationSummary:
    total_cases = len(case_results)
    if total_cases == 0:
        return _apply_feedback_metrics(
            EvaluationSummary(
                total_cases=0,
                retrieval_hit_rate=0.0,
                average_expected_source_rank=None,
                average_best_source_score=None,
                answer_keyword_coverage_rate=None,
            ),
            feedback_metrics=feedback_metrics,
        )

    hit_results = [
        result
        for result in case_results
        if result.retrieval_score.hit
    ]
    rank_values = [
        result.retrieval_score.expected_source_rank
        for result in hit_results
        if result.retrieval_score.expected_source_rank is not None
    ]
    score_values = [
        result.retrieval_score.best_expected_source_score
        for result in hit_results
        if result.retrieval_score.best_expected_source_score is not None
    ]
    coverage_values = [
        result.answer_score.coverage
        for result in case_results
        if result.answer_score.coverage is not None
    ]

    return _apply_feedback_metrics(
        EvaluationSummary(
            total_cases=total_cases,
            retrieval_hit_rate=len(hit_results) / total_cases,
            average_expected_source_rank=_average(rank_values),
            average_best_source_score=_average(score_values),
            answer_keyword_coverage_rate=_average(coverage_values),
        ),
        feedback_metrics=feedback_metrics,
    )


def _apply_feedback_metrics(
    summary: EvaluationSummary,
    feedback_metrics: FeedbackMetrics | None,
) -> EvaluationSummary:
    if feedback_metrics is None:
        return summary

    return summary.model_copy(
        update=feedback_metrics.model_dump(),
    )


def _average(values: list[float | int]) -> float | None:
    if not values:
        return None

    return sum(float(value) for value in values) / len(values)
