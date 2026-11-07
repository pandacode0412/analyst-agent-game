# 13 — Data contracts and integration points

## Current versus target interfaces

agent/round_validator.py takes TableEvidence(table_id, frame_id, phase, source_round_id, final_result, roadmap_revision, round_id_trusted) and returns VerifiedResult(table_id, source_round_id, result, evidence_frames) or None. agent/site_adapter.py defines CapturedFrame, ExtractedEvidence, and a SiteAdapter protocol. agent/pipeline.py runs the FSM and emits ConfirmedCandidate with two evidence references. The coordinator and durable writer persist approved structured candidates.

The legacy `monitor-browser` path calls vision.analyze_frame() and storage.record_observations() only. The newer `monitor-dom` and `replay-export` paths call StructuredExportAdapter, CandidatePipeline through SourceCoordinator, and live_store.save_candidate(). The CLI CSV importer remains the manual reviewed path. The configurable DOM selectors are placeholders, so this is a running generic pipeline but not a validated named-source API.

## Frame envelope

A target capture record should include:

    {
      "schema_version": 1,
      "source_id": "approved-provider-01",
      "capture_id": "uuid-or-monotonic-id",
      "captured_at_utc": "2026-10-19T05:00:00.000Z",
      "received_at_utc": "2026-10-19T05:00:00.120Z",
      "viewport": {"width": 1536, "height": 864, "scale": 1},
      "layout_version": "lobby-v1",
      "page_state": "ACTIVE",
      "evidence_ref": "private://capture/123",
      "image_sha256": "64-hex-characters"
    }

capture_id is unique within the source. captured_at_utc is frame time, not automatically finished_at_utc. A hash may detect repetition but does not prove a new round. evidence_ref should point to a minimal protected capture, not an account screenshot or token-bearing URL. LOGIN, ERROR, STALE, or UNKNOWN page state blocks confirmation.

## Per-table evidence

| Field | Rule |
|---|---|
| source_id and table_id | Verify against the visible table label; never infer from card order alone |
| frame_id | Stable frame identity; the two RESULT frames must differ |
| phase | BETTING, DEALING, RESULT, or UNKNOWN before entering the FSM |
| source_round_id | Normalize and include shoe namespace if the source resets IDs |
| round_id_trusted | True only after source/parser validation; OCR confidence alone is insufficient |
| final_result | BANKER, PLAYER, TIE, or null; only the published final outcome |
| roadmap_revision | Versioned roadmap fingerprint, not merely total marker count |
| captured_at_utc and evidence_ref | Carried by the envelope because the original TableEvidence dataclass lacks them |

An adapter should preserve unreadable fields as UNKNOWN with a reason, never manufacture a round ID from timestamp or marker position. If published result and roadmap disagree, route to review. Document Tie behavior for the exact road being parsed.

## Target confirmation flow

    for each fresh frame and each verified table mapping:
        adapter.extract(frame) → evidence or UNKNOWN
        if source/layout/session is unhealthy:
            validator.gap(); persist GAP; continue
        candidate = validator.accept(evidence)
        if candidate is absent:
            persist observation/quality only; continue
        require both evidence frames, ordered, same source/table/round/result
        apply a documented finish-time policy
        transaction: evidence metadata + confirmed round + checkpoint
        exact duplicate → no-op; conflict → quarantine and alert

ConservativeRoundValidator.gap() resets memory only. The coordinator must persist the gap separately. emitted_ids in RAM is not restart protection; a durable unique key is the final guard. If a checkpoint cannot restore safe context, start UNKNOWN and wait for a new full cycle.

CandidatePipeline still stops at a candidate. SourceCoordinator and live_store now provide the separate durable writer, evidence links, checkpoint, duplicate-frame guard, idempotent source gaps, and conflict quarantine. Its observed_result_at_utc is the second result frame time with an explicit policy label, not a guaranteed source finish time.

## Target time-window streak result

The read-only `red_window_data()` report now requires an exact stored source and a `red_outcome` mapping supplied by the caller and orders stored verified rounds per table. It returns the report date, source, time zone, 07:00–21:00 window, per-table counts, total count, first/13th round keys and finish times, and available evidence references for each event. The count is assigned to the window containing the 13th result, even when the run began before 07:00. A run that reaches 13 once cannot create another event by continuing. Recorded gaps break the run. The current schema has no source namespace in its legacy unique key and no coverage ledger. The structured writer stores source-prefixed round keys and evidence references, but the report still rejects a table ID shared by multiple sources and marks coverage UNKNOWN; source/layout mapping and complete coverage remain target requirements. See docs/07-statistics-and-excel.md and acceptance cases A13–A16.

## Storage migration plan

| Target table | Required additions | Purpose |
|---|---|---|
| captures | capture ID, source, UTC, layout, hash, evidence reference, deletion deadline | Frame trace and stale detection |
| table_evidence | capture/table, phase, round ID, result, revision, parser version, quality reason | Audit each decision |
| confirmed_rounds | source ID, shoe ID if needed, first/last evidence, validator version, finish-time policy | Prevent cross-source collisions and reproduce decisions |
| observation_gaps | start/end, reason code, source, unique event key | Downtime measurement and idempotent import |
| conflicts | round key, old/new payload, evidence, review state | Preserve disagreements |
| worker_checkpoints | source/table, last capture and round, phase, revision, UTC | Controlled recovery |

PostgreSQL version 1 is defined in migrations/001_initial.sql. Migration 003 adds source evidence, unique source gaps, conflicts, processed frames, and checkpoints. The legacy confirmed unique key is still (table_id, round_id); the new writer encodes source in its stored round key. Manual gap imports are still not deduplicated. Before changing the key, back up the database, map existing rows to an explicit source namespace, add a new numbered migration, and test rollback/restore. Do not edit an applied migration or a production database ad hoc.

## Time and ordering

captured_at_utc is when a frame was taken; finished_at_utc is the source's round-end time if available, otherwise a labeled estimate. Verify frame order with a monotonic sequence as well as wall-clock time. Late or reordered frames must not move the FSM backward. If there is no source finish time, report the timing uncertainty, especially around local midnight. The current daily_data() reports one Ho Chi Minh City day and does not calculate a cross-midnight streak.

## Import and report idempotency

The current CSV importer requires verified=YES, reviewer, source, method, an offset-aware time, and valid outcome. The whole file now runs in one PostgreSQL transaction, so an error rolls back every row. Future work should add staging, import_batch_id, and per-row status. Gap import still needs a unique event key.

A report rerun currently overwrites the same workbook. Automated publishing needs report_runs(date, timezone, watermark, version, checksum, status) to prevent duplicate sends and reproduce a snapshot. Show each table's source and coverage; missing tables are not zero-round tables.
