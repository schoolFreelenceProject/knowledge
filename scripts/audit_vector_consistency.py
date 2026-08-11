import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.vector_store import QdrantVectorStore


@dataclass(frozen=True)
class PostgresVectorAudit:
    document_point_ids: list[str]
    code_point_ids: list[str]
    duplicate_references: list[dict[str, Any]]
    invalid_references: dict[str, list[dict[str, Any]]]

    @property
    def all_point_ids(self) -> list[str]:
        return self.document_point_ids + self.code_point_ids

    @property
    def unique_point_ids(self) -> set[str]:
        return set(self.all_point_ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Qdrant vectors against PostgreSQL document/code chunk "
            "metadata. PostgreSQL is treated as the source of truth."
        )
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help=(
            "Delete Qdrant points that are not referenced by PostgreSQL. "
            "This never deletes PostgreSQL metadata."
        ),
    )
    parser.add_argument(
        "--delete-stale",
        action="store_true",
        help="Backward-compatible alias for --delete-orphans.",
    )
    parser.add_argument(
        "--fail-on-inconsistency",
        action="store_true",
        help="Exit with status 2 if the final audit is not fully consistent.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        settings = get_settings()
        delete_orphans = bool(args.delete_orphans or args.delete_stale)
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection_name,
        )

        postgres_audit = _load_postgres_audit()
        initial_qdrant_point_ids = _load_qdrant_point_ids(vector_store)
        initial_orphan_ids = sorted(
            initial_qdrant_point_ids - postgres_audit.unique_point_ids
        )
        deleted_orphan_ids: list[str] = []
        if delete_orphans and initial_orphan_ids:
            vector_store.delete_points(initial_orphan_ids)
            deleted_orphan_ids = initial_orphan_ids

        final_qdrant_point_ids = (
            _load_qdrant_point_ids(vector_store)
            if deleted_orphan_ids
            else initial_qdrant_point_ids
        )
        report = _build_report(
            collection_name=settings.qdrant_collection_name,
            postgres_audit=postgres_audit,
            qdrant_point_ids=final_qdrant_point_ids,
            initial_orphan_ids=initial_orphan_ids,
            deleted_orphan_ids=deleted_orphan_ids,
        )
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

    if args.fail_on_inconsistency and not report["consistent"]:
        return 2

    return 0


def _load_postgres_audit() -> PostgresVectorAudit:
    init_db()
    with get_session_factory()() as session:
        document_rows = session.execute(
            text(
                """
                SELECT id, document_id, qdrant_point_id
                FROM document_chunks
                ORDER BY qdrant_point_id, id
                """
            )
        ).mappings().all()
        code_rows = session.execute(
            text(
                """
                SELECT id, repository_id, code_file_id, qdrant_point_id
                FROM code_chunks
                ORDER BY qdrant_point_id, id
                """
            )
        ).mappings().all()
        invalid_references = {
            "document_chunks_missing_document": _mapping_rows(
                session.execute(
                    text(
                        """
                        SELECT dc.id, dc.document_id, dc.qdrant_point_id
                        FROM document_chunks dc
                        LEFT JOIN documents d ON d.id = dc.document_id
                        WHERE d.id IS NULL
                        ORDER BY dc.id
                        """
                    )
                ).mappings().all()
            ),
            "code_files_missing_repository": _mapping_rows(
                session.execute(
                    text(
                        """
                        SELECT cf.id, cf.repository_id, cf.file_path
                        FROM code_files cf
                        LEFT JOIN code_repositories cr
                            ON cr.id = cf.repository_id
                        WHERE cr.id IS NULL
                        ORDER BY cf.id
                        """
                    )
                ).mappings().all()
            ),
            "code_chunks_missing_repository": _mapping_rows(
                session.execute(
                    text(
                        """
                        SELECT cc.id, cc.repository_id, cc.qdrant_point_id
                        FROM code_chunks cc
                        LEFT JOIN code_repositories cr
                            ON cr.id = cc.repository_id
                        WHERE cr.id IS NULL
                        ORDER BY cc.id
                        """
                    )
                ).mappings().all()
            ),
            "code_chunks_missing_file": _mapping_rows(
                session.execute(
                    text(
                        """
                        SELECT cc.id, cc.code_file_id, cc.qdrant_point_id
                        FROM code_chunks cc
                        LEFT JOIN code_files cf ON cf.id = cc.code_file_id
                        WHERE cf.id IS NULL
                        ORDER BY cc.id
                        """
                    )
                ).mappings().all()
            ),
            "code_chunks_file_repository_mismatch": _mapping_rows(
                session.execute(
                    text(
                        """
                        SELECT
                            cc.id,
                            cc.repository_id,
                            cc.code_file_id,
                            cf.repository_id AS file_repository_id,
                            cc.qdrant_point_id
                        FROM code_chunks cc
                        JOIN code_files cf ON cf.id = cc.code_file_id
                        WHERE cc.repository_id != cf.repository_id
                        ORDER BY cc.id
                        """
                    )
                ).mappings().all()
            ),
        }

    document_point_ids = [str(row["qdrant_point_id"]) for row in document_rows]
    code_point_ids = [str(row["qdrant_point_id"]) for row in code_rows]
    duplicate_references = _find_duplicate_references(
        document_rows=document_rows,
        code_rows=code_rows,
    )
    return PostgresVectorAudit(
        document_point_ids=document_point_ids,
        code_point_ids=code_point_ids,
        duplicate_references=duplicate_references,
        invalid_references=invalid_references,
    )


def _find_duplicate_references(
    document_rows: list[Any],
    code_rows: list[Any],
) -> list[dict[str, Any]]:
    references_by_point_id: dict[str, dict[str, Any]] = {}
    for row in document_rows:
        point_id = str(row["qdrant_point_id"])
        references_by_point_id.setdefault(
            point_id,
            {
                "qdrant_point_id": point_id,
                "document_chunk_ids": [],
                "code_chunk_ids": [],
            },
        )["document_chunk_ids"].append(int(row["id"]))

    for row in code_rows:
        point_id = str(row["qdrant_point_id"])
        references_by_point_id.setdefault(
            point_id,
            {
                "qdrant_point_id": point_id,
                "document_chunk_ids": [],
                "code_chunk_ids": [],
            },
        )["code_chunk_ids"].append(int(row["id"]))

    counter = Counter(
        [str(row["qdrant_point_id"]) for row in document_rows]
        + [str(row["qdrant_point_id"]) for row in code_rows]
    )
    duplicates = []
    for point_id, reference_count in sorted(counter.items()):
        if reference_count <= 1:
            continue

        duplicate = references_by_point_id[point_id]
        duplicate["reference_count"] = reference_count
        duplicates.append(duplicate)

    return duplicates


def _load_qdrant_point_ids(vector_store: QdrantVectorStore) -> set[str]:
    if not vector_store.collection_exists():
        return set()

    point_ids: set[str] = set()
    next_page_offset = None
    while True:
        records, next_page_offset = vector_store.client.scroll(
            collection_name=vector_store.collection_name,
            limit=1000,
            offset=next_page_offset,
            with_payload=False,
            with_vectors=False,
        )
        point_ids.update(str(record.id) for record in records)
        if next_page_offset is None:
            break

    return point_ids


def _build_report(
    collection_name: str,
    postgres_audit: PostgresVectorAudit,
    qdrant_point_ids: set[str],
    initial_orphan_ids: list[str],
    deleted_orphan_ids: list[str],
) -> dict[str, Any]:
    missing_point_ids = sorted(postgres_audit.unique_point_ids - qdrant_point_ids)
    final_orphan_ids = sorted(qdrant_point_ids - postgres_audit.unique_point_ids)
    invalid_reference_counts = {
        name: len(rows)
        for name, rows in postgres_audit.invalid_references.items()
    }
    consistent = (
        not final_orphan_ids
        and not missing_point_ids
        and not postgres_audit.duplicate_references
        and not any(invalid_reference_counts.values())
    )

    return {
        "collection_name": collection_name,
        "consistent": consistent,
        "counts": {
            "postgres_document_points": len(postgres_audit.document_point_ids),
            "postgres_code_points": len(postgres_audit.code_point_ids),
            "postgres_unique_points": len(postgres_audit.unique_point_ids),
            "qdrant_points": len(qdrant_point_ids),
            "initial_orphan_qdrant_points": len(initial_orphan_ids),
            "orphan_qdrant_points": len(final_orphan_ids),
            "missing_qdrant_points": len(missing_point_ids),
            "duplicate_point_references": len(
                postgres_audit.duplicate_references
            ),
            "deleted_orphan_qdrant_points": len(deleted_orphan_ids),
            "invalid_references": invalid_reference_counts,
        },
        "initial_orphan_qdrant_point_ids": initial_orphan_ids,
        "orphan_qdrant_point_ids": final_orphan_ids,
        "missing_qdrant_point_ids": missing_point_ids,
        "duplicate_point_references": postgres_audit.duplicate_references,
        "invalid_references": postgres_audit.invalid_references,
        "deleted_orphan_qdrant_point_ids": deleted_orphan_ids,
    }


def _mapping_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


if __name__ == "__main__":
    raise SystemExit(main())
