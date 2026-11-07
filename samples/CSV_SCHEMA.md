# Confirmed-round CSV input schema

Required columns: table_id, round_id, finished_at_utc, result, method, source, reviewer, verified.

- verified must be YES, and reviewer must identify a real reviewer or approved review process.
- source=DEMO_FIXTURE means synthetic data; never present it as a website observation.
- method=MANUAL_VERIFIED requires a person to review the source evidence.
- method=TRUSTED_ROUND_ID requires an approved, reliable round ID and final outcome.
- round_id must remain unique per table in the current schema. Prefix it with a shoe/session identifier when the source resets IDs.
- finished_at_utc must be ISO-8601 with Z or an offset, such as 2026-10-19T00:00:00Z.
- UNKNOWN, unreadable, stale, and partial rounds must not be imported as CONFIRMED.
- observation_gaps explicitly break strict streaks. Current gap import is not idempotent.
- Keep synthetic and real CSV files in separate databases. The PostgreSQL importer treats each CSV file as one transaction: a malformed row rolls back the entire batch.
