import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import CodeChunkRecord, DocumentChunkRecord
from app.db.session import get_session_factory, init_db
from app.services.vector_store import QdrantVectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Qdrant vectors against PostgreSQL chunk metadata."
    )
    parser.add_argument(
        "--delete-stale",
        action="store_true",
        help="Delete Qdrant points that are not referenced by PostgreSQL.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        settings = get_settings()
        postgres_point_ids = _load_postgres_point_ids()
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection_name,
        )
        qdrant_point_ids = _load_qdrant_point_ids(vector_store)
        stale_point_ids = sorted(qdrant_point_ids - postgres_point_ids)
        missing_point_ids = sorted(postgres_point_ids - qdrant_point_ids)

        deleted_stale = 0
        if args.delete_stale and stale_point_ids:
            vector_store.delete_points(stale_point_ids)
            deleted_stale = len(stale_point_ids)

        report = {
            "collection_name": settings.qdrant_collection_name,
            "postgres_points": len(postgres_point_ids),
            "qdrant_points": len(qdrant_point_ids),
            "stale_qdrant_points": stale_point_ids,
            "missing_qdrant_points": missing_point_ids,
            "deleted_stale_points": deleted_stale,
        }
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Vector consistency report written to: {args.output}")
    else:
        print(payload)

    return 0


def _load_postgres_point_ids() -> set[str]:
    init_db()
    with get_session_factory()() as session:
        document_point_ids = set(
            session.scalars(select(DocumentChunkRecord.qdrant_point_id)).all()
        )
        code_point_ids = set(
            session.scalars(select(CodeChunkRecord.qdrant_point_id)).all()
        )
        return document_point_ids | code_point_ids


def _load_qdrant_point_ids(vector_store: QdrantVectorStore) -> set[str]:
    if not vector_store.collection_exists():
        return set()

    point_ids: set[str] = set()
    next_page_offset = None
    while True:
        records, next_page_offset = vector_store.client.scroll(
            collection_name=vector_store.collection_name,
            limit=256,
            offset=next_page_offset,
            with_payload=False,
            with_vectors=False,
        )
        point_ids.update(str(record.id) for record in records)
        if next_page_offset is None:
            break

    return point_ids


if __name__ == "__main__":
    raise SystemExit(main())
