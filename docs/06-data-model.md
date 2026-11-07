# 06 — PostgreSQL data model and legacy migration

## Why PostgreSQL now?

The runtime uses PostgreSQL 17 as its default store, with a persistent named Docker volume and a health check. It supports concurrent connections, server-side transactions, and a clear path toward several workers and readers. This database change does **not** make the page parser or live round validator production-ready.

The Python driver is Psycopg 3. Connection parameters come from DATABASE_URL or the standard PGHOST, PGPORT, PGDATABASE, PGUSER, and PGPASSWORD environment variables. Compose sets PG* values internally, so credentials are not assembled into a URL in command output. The Compose port is bound only to the local host.

## Versioned schema

migrations/001_initial.sql creates the original tables. migrations/002_red_window_lookup.sql adds descending (table_id, timestamp, id) indexes for historical per-table red-window lookups. migrations/003_verified_source_pipeline.sql adds the structured source pipeline's audit and recovery tables. Numbered migrations are applied once under an advisory lock; schema_migrations records each version and SHA-256 checksum. Applied files are checked for unexpected edits. Do not edit an already deployed migration. Future changes need new numbered migrations and rollback/restore tests.

| Table | Current fields and constraints |
|---|---|
| observations | identity id, table_id, observed_at_utc TIMESTAMPTZ, nonnegative red/blue counts, OBSERVED_NOT_CONFIRMED status, evidence_path |
| confirmed_rounds | identity id, table_id, round_id, finished_at_utc TIMESTAMPTZ, Banker/Player/Tie result, method, source, reviewer, recorded_at_utc TIMESTAMPTZ; unique (table_id, round_id) |
| observation_gaps | identity id, table_id, detected_at_utc TIMESTAMPTZ, reason |
| schema_migrations | Applied schema version, file checksum, and UTC time |
| source_round_evidence | Source/table/source-round key, stored round key, two frame IDs and evidence references, finish-time policy |
| source_conflicts | Existing and incoming JSON payloads, unique conflict event key, OPEN review state |
| source_gaps | Source/table/event key, time, reason; idempotent source gap events |
| processed_source_frames | Unique source/table/frame ID and capture time for replay prevention |
| worker_checkpoints | Last processed frame ID and capture time per source/table |

Time/table indexes support daily reports, and table/time indexes support bounded lookback for the 07:00–21:00 red-window report. PostgreSQL stores true timestamp values; analytics converts them to UTC ISO-8601 strings for the workbook. Both reports read their data in one read-only repeatable-read snapshot.

The legacy key (table_id, round_id) is retained for compatibility with old data. The structured source writer stores a length-prefixed source key as `round_id`, and the structured adapter includes shoe identity when IDs reset per shoe. The red report still rejects a table ID shared across sources because legacy gaps are not source-scoped. Before combining such providers in one database, introduce an explicit source/shoe namespace in a **new** migration and update reports and adapters accordingly. Manual gap import still lacks deduplication; do not import the same gaps twice. Structured source gaps use unique event keys.

## CSV import and transactions

Required columns: table_id, round_id, finished_at_utc, result, method, source, reviewer, verified. verified must be YES. Timestamps need an offset. Each CSV batch is now one PostgreSQL transaction: a bad row rolls back every row in that batch. A concurrent duplicate is resolved by INSERT ... ON CONFLICT DO NOTHING; the existing payload is then compared and a conflict raises an error without overwriting it.

    docker compose run --rm import-demo
    docker compose run --rm import-demo python -m agent.cli ingest-csv \
      --input samples/my_reviewed_rounds.csv

The second demo import inserts zero confirmed rows. MANUAL_VERIFIED requires actual reviewed evidence for real data. DEMO_FIXTURE is synthetic and must never be presented as a website observation.

## One-time import from SQLite

The old data/agent.sqlite3 is **not** opened by the new runtime. To migrate it:

1. Stop old SQLite writers and make a backup of the file and any WAL/SHM state. Back up the new PostgreSQL database if it already exists.
2. Start a **fresh, empty** PostgreSQL database with the new Compose stack. Keep the old file under data/ on the host; Compose mounts data/ read-only to the migration job.
3. Run docker compose run --rm migrate-sqlite. The tool creates a consistent SQLite backup snapshot in memory, locks the three PostgreSQL target tables, checks that they are empty, copies rows in batches, and verifies counts before committing.
4. Query counts in PostgreSQL and generate a report for a known old date. Compare confirmed outcomes, gaps, and report totals with the old export.
5. Retain the original SQLite backup until the PostgreSQL restore and report checks pass.

The migration refuses a nonempty target and a second run. An error rolls back the PostgreSQL import. It does not overwrite existing data or merge demo and real datasets.

## Structured source writes

`SourceCoordinator` records frame identity, validates ordering against a checkpoint, resets its FSM on restart or capture gaps, and writes a candidate plus two evidence references in one transaction through `live_store.py`. Exact frame replay is a no-op. A conflicting round payload is retained in `source_conflicts` and does not overwrite the first confirmed row. A gap is inserted into both `source_gaps` and the legacy `observation_gaps` streak-break table only once per source event key. The source ID, ID/reset rule, final result semantics, and DOM selectors still require independent validation; see docs/17-source-integration.md.

## Inspect and back up

Use psql inside the db container, substituting your user/database names:

    docker compose exec db psql -U baccarat -d baccarat \
      -c "SELECT table_id, result, COUNT(*) FROM confirmed_rounds GROUP BY table_id, result"

A logical backup example:

    docker compose exec -T db pg_dump -U baccarat -d baccarat -Fc > baccarat.backup

Restore into a **separate** database first, then compare row counts and a sample report. Protect backup files because they may contain source metadata and evidence paths. Retain screenshots only as long as required by the source policy. The named volume survives docker compose down; down -v deletes it.

## Time and identity

Store event timestamps as TIMESTAMPTZ in UTC. The daily report selects the Asia/Ho_Chi_Minh day using the half-open interval [start, end), so a boundary instant appears in one report only. Its strict streaks reset at the report-day boundary. The separate red-window report uses local [07:00, 21:00), reads up to 13 prior per-table events to determine continuity at 07:00, and treats Tie or GAP as a break. Captured frame time, source finish time, and database recording time are distinct.

## References

- [Psycopg connection and transaction documentation](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [PostgreSQL INSERT and ON CONFLICT](https://www.postgresql.org/docs/17/sql-insert.html)
- [Docker PostgreSQL guide](https://docs.docker.com/guides/postgresql/)
- [PostgreSQL backup and restore](https://www.postgresql.org/docs/17/backup.html)
