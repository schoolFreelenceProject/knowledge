# Data Lifecycle Management

This milestone does not change the existing document or chat API contracts. It
defines the production lifecycle rules around metadata, vectors, and stored
files.

## Document Versioning

Current behavior keeps one active uploaded file per stored filename. Production
versioning should add a future `document_versions` table rather than mutating
the current `documents` table contract.

Proposed version fields:

- `document_id`
- `version_number`
- `file_hash`
- `storage_path`
- `status`
- `created_at`

Retrieval should only expose chunks for active indexed versions.

## Code Repository Reindexing

Code RAG indexes repository revisions by `repo_url`, `branch`, and
`commit_sha`. The current reindex endpoint reparses the stored repository clone
for the same branch/commit, upserts fresh Qdrant points, replaces file/chunk
metadata on the existing `code_repositories` row, preserves
`code_repository_permissions`, then deletes old Qdrant points that are no longer
referenced.

Future branch-forward reindexing should:

1. Clone the new commit.
2. Parse, chunk, embed, and upsert new Qdrant points.
3. Store new code repository metadata.
4. Grant repository ACL to existing allowed users.
5. Mark the old repository revision stale.
6. Delete old Qdrant points only after the new revision is fully indexed.

This preserves the zero-downtime replacement pattern already used for document
reindexing.

## Stale Vector Cleanup

PostgreSQL is the source of truth for document and code chunk metadata. Qdrant
points that are not referenced by `document_chunks` or `code_chunks` are stale.

Dry run:

```bash
docker compose exec -T api python scripts/audit_vector_consistency.py
```

Delete stale Qdrant points:

```bash
docker compose exec -T api python scripts/audit_vector_consistency.py --delete-orphans --fail-on-inconsistency
```

## Deleted Document Cleanup

Document deletion order remains:

1. Delete Qdrant vectors.
2. Delete PostgreSQL metadata.
3. Delete stored file.

If file deletion fails after metadata deletion, the API returns cleanup warning
details. Operations should investigate and remove orphaned files manually.

## Deleted Code Repository Cleanup

Repository deletion order mirrors document deletion:

1. Delete Qdrant vectors for `code_chunks`.
2. Delete PostgreSQL repository metadata, files, chunks, and permission rows.
3. Delete the stored clone under `data/repositories`.

If stored clone deletion fails after metadata deletion, the API returns cleanup
warning details. Qdrant deletion failure stops the operation before metadata or
file cleanup.

## Retention

Recommended production defaults:

- Keep PostgreSQL backups for at least 14 daily restore points.
- Keep Qdrant snapshots aligned with PostgreSQL backup timestamps.
- Keep stored file backups for the same retention window as metadata.
- Export evaluation and benchmark reports to append-only storage.
