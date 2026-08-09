# Backup And Restore

Back up all three state stores together:

- PostgreSQL metadata
- Qdrant vector snapshots
- stored files in `data/documents` and `data/repositories`

Use one timestamp for the three backup artifacts so they can be restored as a
consistent recovery point.

## PostgreSQL Backup

```bash
DATABASE_URL=postgresql+psycopg://... scripts/backup_postgres.sh
```

Restore:

```bash
DATABASE_URL=postgresql+psycopg://... scripts/restore_postgres.sh backups/postgres/company_rag_YYYYMMDDTHHMMSSZ.dump
```

The restore script runs `pg_restore --clean --if-exists`. Use it on a recovery
database or during a planned maintenance window.

## Qdrant Snapshot

Create a server-side snapshot:

```bash
python scripts/qdrant_snapshot.py create
```

List snapshots:

```bash
python scripts/qdrant_snapshot.py list
```

Download a snapshot artifact:

```bash
python scripts/qdrant_snapshot.py download --snapshot-name company_documents-123.snapshot
```

Recover from a snapshot location visible to Qdrant:

```bash
python scripts/qdrant_snapshot.py recover --location file:///qdrant/snapshots/company_documents-123.snapshot
```

For Docker production, `./backups/qdrant` is mounted at `/qdrant/snapshots`.

## Stored Files Backup

```bash
scripts/backup_stored_files.sh
```

Restore:

```bash
scripts/restore_stored_files.sh backups/files/stored_files_YYYYMMDDTHHMMSSZ.tar.gz
```

## Recovery Order

1. Stop API writes.
2. Restore PostgreSQL.
3. Restore stored files into `data/`.
4. Recover Qdrant snapshot.
5. Run `alembic upgrade head`.
6. Start API.
7. Run vector consistency audit:

```bash
python scripts/audit_vector_consistency.py --output reports/vector_audit.json
```

If stale Qdrant points are expected after a partial recovery:

```bash
python scripts/audit_vector_consistency.py --delete-stale
```
