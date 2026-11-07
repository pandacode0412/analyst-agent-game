# Instructions for changes under agent/

## Module boundaries

- browser.py captures frames and measures freshness; it does not conclude a round from an image.
- vision.py produces ROI and marker observations, not completed Banker/Player/Tie rounds.
- round_validator.py is an FSM for already extracted TableEvidence. Keep one instance per table. accept() currently returns VerifiedResult or None; gap() only resets memory.
- site_adapter.py is a protocol. adapters/structured.py parses explicit export states; adapters/dom.py uses configured DOM selectors but has no validated named-site layout.
- pipeline.py emits ConfirmedCandidate values. coordinator.py and live_store.py now provide durable writes, gaps, checkpoints, and conflict quarantine after an explicit trust gate.
- storage.py is the PostgreSQL source of truth for confirmed rounds. New write paths need evidence, transactions, conflicts, and restart-safe idempotency.
- analytics.py/report.py use confirmed rounds for rates and streaks; report gaps, unknowns, and coverage separately.
- red_window.py/red_report.py count verified 13-red events in the 07:00–21:00 local window from confirmed rounds, with an explicit source-validated mapping. Never infer a complete census while coverage is UNKNOWN.

## Source integration work

1. Add agent/adapters/<source_name>.py implementing SiteAdapter for an authorized source and validated layout. Carry parser version, source ID, UTC timestamp, evidence reference, and quality reason.
2. Validate source-specific layout, page freshness, phase/result values, and evidence against held-out captures. The generic coordinator already handles gap and conflict persistence, checkpoint rebaseline, and transactional writes.
3. Add a new versioned PostgreSQL migration for full source namespace, measured coverage, and retention. Migration 003 already adds evidence, conflicts, unique source gaps, and checkpoints. Never edit an applied migration.
4. Harden the DOM worker with measured backoff, heartbeat, permitted session lifecycle, and graceful shutdown after the adapter passes acceptance tests.

Do not label a placeholder adapter as live. Its parsing rules and round_id_trusted flag require an independently labeled corpus for that exact website and layout. Without an authorized source, keep browser monitoring observation-only.

## Time and identity

captured_at_utc, finished_at_utc, and recorded_at_utc have different meanings. Store timezone-aware UTC timestamps; the current report day uses Asia/Ho_Chi_Minh. If source IDs reset per shoe, include a source/shoe namespace before deduplication. After a gap or restart, do not invent local sequence IDs unless continuity can be proven.

## Before completion

Run relevant tests and, when dependencies are available, the full suite. Verify that 100 identical frames produce no confirmed round, conflicts do not overwrite, Tie/GAP breaks strict streaks, and no marker count reaches insert_verified_round().
