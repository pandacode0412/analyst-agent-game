# Instructions for AI coding agents

## Objective

Build a multi-table Baccarat observation and historical reporting agent with traceable evidence and explicit data gaps. Do not implement wagering, game controls, or claims of reliable next-round prediction.

## Read before changing code

1. README.md for available commands and the prototype boundary.
2. docs/12-agent-specification.md for requirements F01–F10.
3. docs/13-integration-contracts.md for the Frame → TableEvidence → VerifiedResult → storage boundary.
4. docs/14-acceptance.md for ground truth, tests, and release gates.
5. docs/15-source-survey.md before writing an adapter for a specific website.
6. docs/07-statistics-and-excel.md for the requested 07:00–21:00, 13-red event definition.
7. agent/AGENTS.md when editing Python modules and tests/AGENTS.md when editing tests.
8. docs/16-dependencies-and-version-policy.md before changing Python, packages, or container images.
9. docs/17-source-integration.md before changing the structured source path or DOM reader.

README.md, AGENTS.md, docs/*.md, and samples/*.md are the maintained sources. After documentation changes, run python3 tools/build_full_guide.py.

## Accurate current state

- agent/browser.py: monitor-browser captures frames and writes marker observations only. monitor-dom (monitor_dom_browser) reads configured DOM text and drives SourceCoordinator, the FSM, and the durable writer; it can write confirmed rounds only with --trusted-round-ids. Neither path measures page-content freshness.
- agent/vision.py counts red and blue markers; a marker is not a completed round.
- agent/round_validator.py is an in-memory teaching FSM for already extracted TableEvidence. It does not parse a real UI or recover its state after restart.
- agent/site_adapter.py defines a source adapter protocol. adapters/structured.py implements it for explicit states; adapters/dom.py is a reader that builds a structured payload from configured text selectors, which StructuredExportAdapter then parses. The shipped DOM selectors are placeholders, not a validated named-source adapter.
- agent/pipeline.py produces ConfirmedCandidate objects. agent/coordinator.py and agent/live_store.py now persist candidates, evidence, source gaps, conflicts, frame keys, and checkpoints; they do not prove that an adapter is trustworthy.
- agent/storage.py uses PostgreSQL with transactional writes and versioned migrations 001–003. Its current unique key is (table_id, round_id). Manual gaps (ingest-gaps) are not deduplicated; source gaps from the coordinator are.
- agent/analytics.py and agent/report.py report confirmed rounds with strict streaks that break on Tie or GAP and reset at the local day boundary. They show recorded gaps but no UNKNOWN or coverage figures, and they combine sources that share a table_id.
- agent/red_window.py and agent/red_report.py produce a separate 07:00–21:00 count of stored verified red-result runs reaching 13. They require an explicit BANKER/PLAYER mapping and report UNKNOWN coverage; they do not validate a live source. agent/streak_window.py and agent/streak_report.py (`report-streaks`) implement the full requested metric defined in docs/07-statistics-and-excel.md: both sides, two Tie policies, an operator-chosen window, and an all-table headline. Neither report validates a live source or detects shoe boundaries.
- agent/session.py manages an optional login session for monitor-dom: it loads a saved storage state, detects logged-out pages, re-logs in only when no CAPTCHA appears, and records LOGGED_OUT, CAPTCHA_REQUIRED, or LOGIN_FAILED gaps. A human performs the first login and every CAPTCHA (docs/17-source-integration.md). Never automate CAPTCHA solving.
- agent/adapters/lobby_counters.py reads a multi-table lobby from published per-shoe counters (docs/17-source-integration.md). It has passed only synthetic tests; a held-out comparison on the real source is still required before trusted IDs. tools/export_chrome_session.py exports a human-logged-in Chrome session.
- agent/run_settings.py resolves an optional `run:` block (start/stop times, interval, report on exit, login reminders) with command-line overrides; lobby_counters supports `tables: auto` discovery.
- monitor-dom can loop continuously for a configured accessible page. There is no validated named-site adapter, measured coverage, managed session lifecycle, or automatic report delivery.

## Implementation order

1. Run existing tests. Report missing dependencies as environment failures, not as passed or failed business tests.
2. Select one authorized source and one table using docs/15-source-survey.md. Without a real source, work only on source-independent contracts, migrations, and labeled offline fixtures.
3. Build a source adapter that extracts table identity, phase, source round ID, final outcome, and roadmap revision with provenance, timestamp, and quality status. Do not set round_id_trusted merely because OCR confidence is high.
4. Extend the pipeline to validate freshness and layout, run one FSM per table, handle UNKNOWN/GAP, and preserve evidence.
5. Extend the existing PostgreSQL migration sequence with a full source namespace and coverage ledger. Migration 003 already adds evidence, conflicts, idempotent source gaps, and checkpoints; preserve its transactional guarantees.
6. Add coverage, unknown, and conflict reporting. Keep synthetic data in a separate database.
7. Validate the source's red mapping and round verification before using the existing 07:00–21:00 reached-13 report on real data. Add a coverage ledger and evidence references. Run the A01–A16 matrix and held-out/soak tests in docs/14-acceptance.md before enabling automatic writes for that source.

Each step should leave reviewable code, tests or labeled corpus evidence, updated documentation, and reproduction commands. If source information is unavailable, finish independent work and record exact missing inputs in docs/15-source-survey.md.

## Business invariants

- Never turn red_markers, blue_markers, an image hash, or a timestamp alone into a round result.
- Do not assume red means Banker or Player until the exact source/layout mapping has been independently verified.
- Never write a confirmed round without trustworthy identity, final outcome, valid phase sequence, and stable evidence.
- UNKNOWN, stale images, logout, table/layout mismatch, and interruptions must fail closed. Record quality or GAP; do not infer missed rounds.
- Quarantine conflicting payloads for the same round key; do not silently overwrite.
- Measure precision, recall, coverage, and duplicates per table and source on held-out data before claiming automation.
- Do not commit credentials, cookies, tokens, balances, or personal screenshots. Use authorized sources only.

## Basic checks

    python3 -m unittest discover -s tests -v
    python3 tools/build_full_guide.py
    docker compose config

The seventeen PostgreSQL integration tests run when RUN_PG_TESTS=1 and PG* connection variables point to a test server. docker compose run --rm test sets that flag and creates isolated temporary schemas.

Host Python needs dependencies from requirements.txt; Docker is an alternative if its daemon is available. Do not edit tests to hide a missing dependency.

Dependency changes target CPython 3.12.x. The current requirements contain version ranges and do not lock indirect dependencies; follow docs/16-dependencies-and-version-policy.md before calling a build reproducible.
