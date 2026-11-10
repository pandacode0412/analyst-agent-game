# Instructions for changes under agent/

## Module boundaries

- browser.py has three paths. capture_page saves one screenshot. monitor_browser writes marker observations only. monitor_dom_browser reads configured DOM text through DOMStateReader and drives SourceCoordinator, so it can write confirmed rounds when --trusted-round-ids is set. browser.py does not measure page-content freshness: the reader stamps captured_at_utc itself, so a frozen page captured at regular intervals is not detected. No path concludes a round from an image.
- session.py is the optional login lifecycle for monitor-dom: saved storage state, logged-out detection, re-login only without CAPTCHA, and LOGGED_OUT/CAPTCHA_REQUIRED/LOGIN_FAILED gaps. Never add CAPTCHA solving, never print credentials, and keep credentials only in secrets/site.env (docs/17-source-integration.md).
- vision.py produces ROI and marker observations, not completed Banker/Player/Tie rounds.
- round_validator.py is an FSM for already extracted TableEvidence. Keep one instance per table. accept() currently returns VerifiedResult or None; gap() only resets memory. emitted_ids lives in RAM and is not restart protection.
- site_adapter.py is a protocol. adapters/structured.py (StructuredExportAdapter) implements it for explicit export states. adapters/dom.py is a reader, not a SiteAdapter: DOMStateReader turns configured selectors into a CapturedFrame payload that StructuredExportAdapter then parses. The shipped selectors are placeholders. shoe_id is not in the required selector list although ids_reset_per_shoe defaults to true; a missing shoe_id makes every frame an adapter error (fail closed). A table whose visible label differs from its configured ID is omitted and becomes TABLE_MISSING.
- adapters/lobby_counters.py (reader: lobby_counters) reads multi-table lobby cards with published per-shoe counters and maps them to the structured contract (evidence level B2, docs/05). A round requires total +1 with exactly one Banker/Player/Tie +1; any other change is UNKNOWN with a reason. Its local shoe namespace must never repeat. It stores text manifests only; do not add screenshots without a retention and size budget. With `tables: auto` it discovers tables from card names; SourceCoordinator then grows its expected-table set (auto_tables=True) and still records one TABLE_MISSING gap per absence.
- run_settings.py resolves the optional `run:` block and command-line overrides into concrete start/stop instants (Asia/Ho_Chi_Minh) and report options; keep it pure and tested.
- pipeline.py emits ConfirmedCandidate values. coordinator.py and live_store.py always persist processed frames, checkpoints, and source gaps. The --trusted-round-ids gate controls only whether candidates, and therefore confirmed rounds, evidence rows, and conflicts, can be produced.
- storage.py is the PostgreSQL source of truth for confirmed rounds. Its unique key is (table_id, round_id); live_store.py stores a length-prefixed source key in round_id. mark_gap() (manual ingest-gaps) is not deduplicated; source gaps are. record_observations() stamps observed_at_utc with write time, not capture time. New write paths need evidence, transactions, conflicts, and restart-safe idempotency.
- analytics.py/report.py use confirmed rounds for rates and strict streaks within one local day. They report recorded gaps but not UNKNOWN states or coverage, and they do not filter by source: rows sharing a table_id are combined. Unknown and coverage reporting is target work.
- streak_window.py/streak_report.py implement the requested metric in docs/07-statistics-and-excel.md: Banker and Player runs reaching 13 in an operator-chosen local window under reached_13_strict_v1 and reached_13_tie_transparent_v1, with an all-table headline. Colors are labels only. They do not detect shoe boundaries.
- red_window.py/red_report.py are the older one-side, strict-only, fixed 07:00–21:00 report kept for compatibility. Their 13-row lookback is valid only for the strict policy. Never infer a complete census while coverage is UNKNOWN.

## Source integration work

1. Add agent/adapters/<source_name>.py implementing SiteAdapter for an authorized source and validated layout. Carry parser version, source ID, UTC timestamp, evidence reference, and quality reason. TableEvidence and ExtractedEvidence currently have no parser_version or quality_reason field and the schema has no column for them; make that planned contract change (docs/13-integration-contracts.md) first.
2. Validate source-specific layout, page freshness, phase/result values, and evidence against held-out captures. The generic coordinator already handles gap and conflict persistence, checkpoint rebaseline, and transactional writes. It checks only frame identity, timestamp order, and maximum frame gap; table/layout identity and page-content freshness are the adapter's responsibility.
3. Add a new versioned PostgreSQL migration for full source namespace, measured coverage, and retention. Migration 003 already adds evidence, conflicts, unique source gaps, and checkpoints. Never edit an applied migration.
4. Harden the DOM worker with measured backoff, heartbeat, permitted session lifecycle, and graceful shutdown after the adapter passes acceptance tests.

Do not label a placeholder adapter as live. Its parsing rules and round_id_trusted flag require an independently labeled corpus for that exact website and layout. Without an authorized source, keep browser monitoring observation-only.

## Time and identity

captured_at_utc, finished_at_utc, and recorded_at_utc have different meanings. For rows written by the source pipeline, confirmed_rounds.finished_at_utc is the capture time of the second RESULT frame (time_policy SECOND_RESULT_FRAME_OBSERVED_AT, stored in source_round_evidence), not a source finish time. Store timezone-aware UTC timestamps; the current report day uses Asia/Ho_Chi_Minh. If source IDs reset per shoe, include a source/shoe namespace before deduplication. After a gap or restart, do not invent local sequence IDs unless continuity can be proven.

## Before completion

Run relevant tests and, when dependencies are available, the full suite. Verify that 100 identical frames produce no confirmed round, conflicts do not overwrite, Tie/GAP breaks strict streaks, and no marker count reaches insert_verified_round(). tests/test_candidate_pipeline.py replays 100 identical frames and checks that marker paths do not reference round writers; extend both checks when adding a new capture or adapter path.
