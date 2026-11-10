# 03 — Codebase walkthrough

## agent/cli.py

argparse provides preview, monitor-image, capture-browser, monitor-browser, monitor-dom, replay-export, ingest-csv, ingest-gaps, report, report-red-window, and report-streaks. Docker Compose reuses the same image with different commands. The CLI never logs in or places bets.

| Command | Input | Output | Writes confirmed rounds? |
|---|---|---|---|
| preview | Image and ROI YAML | Annotated image and JSON marker counts | No |
| monitor-image | Static image and iteration count | PostgreSQL observations | No |
| capture-browser | URL and viewport | Screenshot | No |
| monitor-browser | URL, ROI, iterations | Annotated frames and observations | No |
| monitor-dom | Reviewed DOM selector configuration, interval, optional trusted-ID gate | Cropped table evidence, source gaps, and candidates when trusted | Conditionally, after explicit trust gate |
| replay-export | Structured JSONL source states and explicit source trust gate | Source events, evidence, gaps, checkpoints | Conditionally, after explicit trust gate |
| ingest-csv | Reviewed CSV | PostgreSQL confirmed_rounds | Yes |
| ingest-gaps | Gap CSV | PostgreSQL observation_gaps | No |
| report | Date and PostgreSQL database | Five-sheet Excel workbook | No |
| report-red-window | Date, source, explicit RED mapping, and PostgreSQL database | Three-sheet 07:00–21:00 reached-13 Excel workbook | No |
| report-streaks | Date, source, optional window and color label, PostgreSQL database | Printed headline and four-sheet Banker/Player reached-13 workbook for both Tie policies | No |

Use python -m agent.cli <command> --help for CLI options.

## agent/config.py and agent/vision.py

config.py parses a tables list of table IDs and pixel rectangles. Its validation catches negative or out-of-frame ROIs, but an ROI can still point at the wrong table while remaining inside the screenshot. Always inspect the annotated preview.

vision.py loads images as BGR, converts crops to HSV, thresholds red/blue, filters contours by area and circularity, and returns markers and per-table counts. Its thresholds were chosen for the synthetic image. Marker count must never be written as Banker/Player round count.

## agent/browser.py

capture_page opens an internal Playwright Chromium page, waits for DOM content and a fixed delay, then saves one screenshot. monitor_browser opens one page and captures N frames; each is decoded, analyzed by ROI, and written as marker observations. monitor_dom_browser uses a configurable DOM reader, cropped table evidence, and the source coordinator. It can loop when iterations is zero, records errors as gaps, and retries navigation. When the DOM config has a `session` block, agent/session.py loads `secrets/session_state.json`, detects logged-out pages, re-logs in only when no CAPTCHA appears, and records LOGGED_OUT, CAPTCHA_REQUIRED, or LOGIN_FAILED gaps (docs/17-source-integration.md). It has no validated named Baccarat layout.

## agent/round_validator.py

TableEvidence contains table_id, frame_id, phase, source_round_id, final_result, roadmap_revision, and round_id_trusted. ConservativeRoundValidator is a per-table teaching FSM. It requires BETTING → DEALING → two independent matching RESULT frames, a trusted round ID, and a changed roadmap revision. It returns VerifiedResult or None. It does not read screenshots, persist state, or write the database.

## agent/site_adapter.py and agent/pipeline.py

site_adapter.py defines CapturedFrame, ExtractedEvidence, and the SiteAdapter protocol. adapters/structured.py reads explicit source states and defaults IDs to untrusted. adapters/dom.py reads configured DOM text fields and table-cropped screenshots; the shipped selectors are placeholders. pipeline.py runs the FSM for one explicitly selected source and returns ConfirmedCandidate with two evidence references and a time policy. coordinator.py validates source/table identity, frame order, restart and gap behavior, then passes candidates to live_store.py. The coordinator does not certify that a source adapter is accurate; a reviewed corpus and trust gate are still required.

## agent/storage.py

connect opens PostgreSQL through Psycopg and applies numbered migrations under an advisory lock. Migration 001 creates the original schema; migration 002 adds per-table time indexes; migration 003 adds source evidence, idempotent source gaps, conflicts, processed frames, and checkpoints. record_observations writes only OBSERVED_NOT_CONFIRMED rows. insert_verified_round uses a transaction and ON CONFLICT to deduplicate safely across concurrent writers; a conflicting payload raises an error. live_store.py retains conflicting source payloads for review. The old manual mark_gap path still does not deduplicate repeats. See docs/06-data-model.md for schema, backups, and legacy migration.

## agent/analytics.py and agent/report.py

analytics.py converts the selected Asia/Ho_Chi_Minh day to a half-open UTC interval, reads confirmed rounds and gaps, and computes counts, strict streaks, Wilson 95% intervals, and observation frame counts. Tie/GAP breaks a strict streak; the implementation calculates streaks within the selected day.

report.py writes Summary, Rounds, Streaks, Quality, and Methodology sheets through XlsxWriter. It warns when any row comes from DEMO_FIXTURE. Keep real and synthetic databases separate.

## Tools, tests, and deployment files

agent/red_window.py counts one event when a verified strict red run first reaches 13 in the local 07:00–21:00 window, using up to 13 earlier events to handle a run crossing 07:00. agent/red_report.py exports the separate Excel workbook, including source evidence references when available. The caller must supply a source and BANKER or PLAYER as its validated red mapping; the workbook marks coverage UNKNOWN. A table ID shared by multiple sources is rejected until the schema gains a source namespace. tools/generate_synthetic_lobby.py creates a harmless six-table learning image. tools/build_full_guide.py combines maintained Markdown files. tools/migrate_sqlite_to_postgres.py imports a legacy SQLite snapshot into an empty PostgreSQL database. The test suite has 72 tests: seventeen PostgreSQL integration tests, one Chromium reader smoke test, three end-to-end simulated-site tests (tests/test_live_simulation.py), and fifty-one source-independent tests. Dockerfile packages Python, Psycopg, migrations, and Playwright Chromium. compose.yaml adds a PostgreSQL service with a named volume and health check; data/ is mounted read-only only for legacy import.

## Example call paths

    docker compose run --rm preview
      → agent.cli preview
      → config.load_regions
      → vision.load_image / analyze_frame
      → output/roi_preview.png and JSON

    docker compose run --rm report
      → agent.cli report
      → storage.connect
      → report.export_daily
      → analytics.daily_data
      → output/reports/baccarat_daily_YYYY-MM-DD.xlsx

Read CLI → config → vision → browser → validator → adapter contract → pipeline → storage → analytics → report while exploring the code.
