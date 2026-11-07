# 17 — Structured source integration and live DOM trial

## Current boundary

The source-independent path is implemented: structured capture → `StructuredExportAdapter` → per-table `SourceCoordinator` → conservative phase validator → transactional PostgreSQL round/evidence writer → reports. A configurable DOM reader can populate the same path when an authorized page exposes explicit text fields. The repository still has **no validated adapter for a named Baccarat website**. `config/real_dom.example.yaml` contains placeholder selectors and must not be treated as a working site configuration.

The older `monitor-browser` and `monitor-image` commands remain marker-observation only. `monitor-dom` uses the structured path. Without `--trusted-round-ids`, it cannot confirm a round. With that flag, the operator asserts that the exact page, selectors, ID/reset semantics, phase and result labels, and evidence policy passed the source review in docs/15-source-survey.md and the held-out tests in docs/14-acceptance.md. The flag is a technical gate, not proof of accuracy.

## Try the synthetic structured export

The file `samples/structured_export_demo.jsonl` contains four synthetic captures for one round. It has BETTING, DEALING, and two stable RESULT frames, a shoe ID, a round ID, a final BANKER result, and a changed roadmap revision. Use a disposable database or a separate Compose project:

    docker compose run --rm replay-export-demo

Expected first result: three `OBSERVED` states and one `INSERTED`. Replaying the same file returns duplicate-frame statuses and no new round. This fixture does not establish any website's accuracy. The command-line equivalent is:

    docker compose run --rm replay-export-demo python -m agent.cli replay-export \
      --input samples/structured_export_demo.jsonl \
      --source-id DEMO_STRUCTURED --tables S01 --trusted-round-ids

For a real authorized structured export, leave `--trusted-round-ids` off until the source identity and round semantics are independently validated. Each JSONL line follows the field contract in `samples/STRUCTURED_EXPORT_SCHEMA.md`. Each frame is committed separately, so a later invalid line does not roll back prior valid frames. Use a fresh database for a new source or layout during evaluation.

## Configure an authorized DOM page

1. Complete docs/15-source-survey.md and obtain permission to observe the source at the intended capture rate.
2. Copy `config/real_dom.example.yaml` to a private configuration. Set the real URL, fixed viewport, stable table selectors, visible table label, phase, round ID, shoe ID if IDs reset, final result, and roadmap revision. `root` must uniquely select the intended table. The visible `label` must equal the configured table ID. Set phase/result maps for the source's exact text.
3. Run a short observation-only trial and inspect the cropped table evidence under `output/dom_evidence/`:

    docker compose run --rm monitor-dom python -m agent.cli monitor-dom \
      --config config/my_source_dom.yaml --iterations 30 --interval 5

4. Compare every extracted field against an independently labeled capture corpus. Include Tie, shoe reset, login/error states, table reordering, missing selectors, and page delays. Store the corpus and review decision outside the repository if it contains private data.
5. Only after the source passes the acceptance gate, run with `--trusted-round-ids`. Use `--iterations 0` for an open-ended worker. The worker records missing-table, adapter, stale-frame, restart, and capture-gap events and fails closed when it cannot establish continuity.

The DOM reader only handles fields exposed as accessible text in one page context. Canvas-only content, cross-origin iframes, login/session workflows, and source-specific result behavior need a separate reviewed adapter. There is no generic safe way to infer these from a screenshot or marker count.

## Persistence and reporting

Migration 003 adds source-round evidence, idempotent source gaps, processed frame keys, checkpoints, and quarantined conflicts. The writer stores a source-prefixed key in the existing `confirmed_rounds` table so a second source's raw round ID cannot overwrite it. A shoe ID must be included when the source reuses round IDs by shoe. On restart the coordinator records a GAP and requires a new BETTING → DEALING → RESULT cycle. It does not infer rounds missed while stopped.

`source_round_evidence` keeps the two frame IDs and evidence references for confirmed rounds. The 07:00–21:00 red report includes these references when available. Existing reviewed CSV rows may lack them. Observation coverage remains `UNKNOWN` because the project has no independently verified source ledger or measured coverage ratio. The current `observation_gaps` table is keyed only by table, so a database with multiple sources reusing the same table ID is not supported by the red report; it rejects that case. Keep real and synthetic sources in separate databases.

Review the source-specific red-to-outcome mapping before running:

    docker compose run --rm report python -m agent.cli report-red-window \
      --date 2026-10-19 --source DEMO_STRUCTURED --red-outcome BANKER

This fixture has only one round, so its reached-13 count is zero.
