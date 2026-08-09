import argparse
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import get_session_factory, init_db
from app.services.evaluation_service import (
    EvaluationDatasetError,
    load_evaluation_dataset,
)
from app.services.feedback_evaluation_service import (
    FeedbackEvaluationService,
    FeedbackEvaluationServiceError,
)


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "evaluation" / "failed_queries.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export low-rated human feedback queries as an evaluation dataset."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the failed query evaluation dataset JSON.",
    )
    parser.add_argument(
        "--max-rating",
        type=int,
        default=2,
        help="Export feedback rows with rating less than or equal to this value.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum feedback rows to export.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Feedback row offset for pagination.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        help="Optional filter by feedback user id.",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("vector", "bm25", "hybrid"),
        help="Optional filter by trace retrieval mode.",
    )
    parser.add_argument(
        "--status",
        choices=("PROCESSING", "SUCCESS", "ERROR"),
        help="Optional filter by trace status.",
    )
    parser.add_argument(
        "--created-from",
        type=_parse_datetime,
        help="Optional feedback created_at lower datetime bound.",
    )
    parser.add_argument(
        "--created-to",
        type=_parse_datetime,
        help="Optional feedback created_at upper datetime bound.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        _validate_args(args)
        dataset = FeedbackEvaluationService(
            session_factory=get_session_factory(),
            init_database=init_db,
        ).export_failed_query_dataset(
            max_rating=args.max_rating,
            limit=args.limit,
            offset=args.offset,
            user_id=args.user_id,
            retrieval_mode=args.retrieval_mode,
            status=args.status,
            created_from=args.created_from,
            created_to=args.created_to,
        )
        _write_dataset(dataset=dataset, output_path=args.output)

        # Keep the export honest: ensure evaluate_rag.py can load the file.
        load_evaluation_dataset(args.output)
    except (
        EvaluationDatasetError,
        FeedbackEvaluationServiceError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {len(dataset.cases)} failed query cases to: {args.output}")
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if args.max_rating < 1 or args.max_rating > 5:
        raise ValueError("--max-rating must be between 1 and 5.")

    if args.limit < 1:
        raise ValueError("--limit must be greater than 0.")

    if args.offset < 0:
        raise ValueError("--offset cannot be negative.")

    if (
        args.created_from is not None
        and args.created_to is not None
        and args.created_from > args.created_to
    ):
        raise ValueError("--created-from must be before or equal to --created-to.")


def _write_dataset(dataset, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        dataset.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime value: {value}"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
