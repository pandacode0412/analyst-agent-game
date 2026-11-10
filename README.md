# Baccarat Multi-Table Analytics Agent — Docker MVP v2

**Language:** English. **Purpose:** a reproducible observation and historical reporting prototype, with a clear path toward a source-specific agent.

> This project does not place bets or provide reliable next-round predictions. A screenshot or a roadmap marker does not prove that a new round has ended. Color detections remain OBSERVED_NOT_CONFIRMED. The sample CSV contains synthetic rounds, not data from a real website.

The maintained documentation is README.md, AGENTS.md, the Markdown files in docs/, and the schema notes in samples/. The combined Markdown handbook FULL_DEVELOPER_GUIDE.md is generated in English from README.md and docs/.

**Version baseline:** CPython 3.12.x, Playwright 1.55.0, and PostgreSQL 17. See [the complete direct-dependency inventory and version policy](docs/16-dependencies-and-version-policy.md). Several Python packages still use version ranges, and indirect packages are not locked; the current files are not yet a reproducible production dependency lock.

**Target operator question:** For each authorized table, within an operator-chosen local window (default 07:00–21:00), how many verified Banker runs and Player runs first reach 13 consecutive results, counted once with Tie breaking the run and once with Tie skipped? The full definition is in docs/07-statistics-and-excel.md. The read-only `report-streaks` command answers this from stored confirmed rounds and prints a headline such as "Banker 3, Player 2, total 5 events across 12 tables" for each Tie policy. The older `report-red-window` command remains for one side with the strict policy. A maximal streak is counted once when its 13th result occurs in the window; a streak of 14 is not counted twice. See docs/07-statistics-and-excel.md for boundary and gap rules. The current POC does not automatically verify results from a real site or measure complete coverage.

To rebuild the handbook after editing its sources (standard library only):

    python3 tools/build_full_guide.py

The English demo Excel workbook is BACCARAT_Excel_Demo_Formatted.xlsx.

## What works today

| Capability | Current state |
|---|---|
| Generate a synthetic six-table lobby and preview configured ROIs | Implemented |
| Count red/blue markers in a screenshot | Implemented for the demo image; real layouts need calibration |
| Capture a browser page with Playwright | Implemented for accessible pages |
| Monitor browser frames and store marker observations | Implemented by `monitor-browser`; never writes confirmed rounds |
| Read an authorized DOM layout or structured export through a verification pipeline | Implemented as configurable code; no real website layout has been validated |
| Import human-reviewed CSV rounds into PostgreSQL with duplicate detection | Implemented; each CSV batch is transactional |
| Store observation gaps | Implemented; repeat imports are not idempotent yet |
| Compute historical Banker/Player/Tie counts, strict streaks, and Wilson 95% intervals | Implemented from confirmed rounds |
| Export a five-sheet Excel workbook | Implemented |
| Report Banker and Player runs reaching 13 in a chosen window, both Tie policies, with an all-table headline (`report-streaks`) | Implemented for stored confirmed rounds; coverage remains unknown |
| Export a separate 07:00–21:00 Excel count of verified 13-red events | Implemented for stored confirmed rounds with an explicit red mapping; coverage remains unknown |
| Validate and persist structured round evidence | Connected to a transactional writer with evidence, gaps, checkpoints, and conflict quarantine; source trust still requires review |
| Tests | 72 tests passed in Docker with PostgreSQL and Chromium; seventeen require a server, one requires Chromium, three end-to-end simulation tests require both, and fifty-one run without either |
| Automatically confirm every round on a real website | Generic DOM worker exists; no named website adapter or accuracy evidence yet |
| Continuous operation | `monitor-dom --iterations 0` loops with reconnect attempts; no production soak or managed session lifecycle yet |
| Automatic login, CAPTCHA bypass, private API access, or betting | Outside scope |

## Run the Docker demo

Requirements: Docker Desktop with WSL 2 on Windows, or Docker Engine with Compose v2 on Ubuntu. Allow about 4 GB of free RAM and several GB of disk space for Playwright and PostgreSQL. Build requires internet access. Set a unique strong POSTGRES_PASSWORD in the untracked .env file before a real deployment.

    cp .env.example .env
    docker compose build
    docker compose up -d db
    docker compose run --rm preview
    docker compose run --rm monitor-image
    docker compose run --rm import-demo
    docker compose run --rm import-gaps-demo
    docker compose run --rm replay-export-demo
    docker compose run --rm report
    docker compose run --rm test

In PowerShell, use Copy-Item .env.example .env. PostgreSQL data persists in the named pg_data volume; image and Excel outputs remain under output/. The demo workbook is output/reports/baccarat_daily_2026-10-19.xlsx. Run import-gaps-demo only once: the current gap table does not deduplicate. Keep demo and real data in separate databases or Compose projects.

To move a legacy SQLite database into an **empty** PostgreSQL database, run docker compose run --rm migrate-sqlite. The job copies a consistent SQLite snapshot in one PostgreSQL transaction and refuses a nonempty target. Back up both databases first; see docs/06-data-model.md.

See docs/02-installation.md for host setup and the exact behavior of each command.

## Repository map

| Path | Purpose |
|---|---|
| AGENTS.md | Instructions and work order for AI coding agents |
| agent/AGENTS.md; tests/AGENTS.md | Package-specific and test-specific instructions |
| agent/cli.py | CLI entry point |
| agent/browser.py | Browser capture and observation loop |
| agent/config.py; agent/vision.py | ROI configuration and marker detection |
| agent/round_validator.py | Conservative teaching FSM |
| agent/site_adapter.py; agent/pipeline.py | Source adapter contract and confirmed-candidate validation |
| agent/adapters/; agent/coordinator.py; agent/live_store.py | Structured export and DOM adapters, per-table coordination, and durable source writes |
| agent/storage.py; migrations/ | PostgreSQL connection, transactional writes, and versioned schema |
| agent/analytics.py; agent/report.py | Historical metrics and Excel export |
| agent/streak_window.py; agent/streak_report.py | Banker/Player reached-13 counting for both Tie policies, headline, and Excel export |
| agent/red_window.py; agent/red_report.py | Older one-side 13-red window counting and separate Excel export |
| config/ | Synthetic and unverified real-lobby ROI examples |
| assets/synthetic_lobby.png | Synthetic image for learning and tests |
| samples/ | Synthetic verified-round CSV, gap CSV, and structured export fixtures |
| tests/ | Unit tests |
| docs/ | Architecture, implementation, data, operations, and acceptance criteria |
| tools/build_full_guide.py | Rebuilds the combined Markdown handbook |
| tools/migrate_sqlite_to_postgres.py | One-time legacy SQLite import into empty PostgreSQL |

## Reading order

1. docs/01-architecture.md — system boundary and data flow.
2. docs/02-installation.md — setup and demo.
3. docs/03-codebase.md — each module and its input/output.
4. docs/04-screen-reading.md — ROI and visual calibration.
5. docs/05-round-verification.md — round identity, FSM, and duplicate prevention.
6. docs/06-data-model.md — PostgreSQL, legacy migration, CSV, and backup.
7. docs/07-statistics-and-excel.md — report definitions and limitations.
8. docs/08-operations.md — 24/7 design and scheduling.
9. docs/09-testing.md — tests and troubleshooting.
10. docs/10-production-roadmap.md — phased implementation.
11. docs/11-faq.md — common questions.
12. docs/12-agent-specification.md — requirements for the target agent.
13. docs/13-integration-contracts.md — event contracts and storage changes.
14. docs/14-acceptance.md — ground truth, metrics, and release gates.
15. docs/15-source-survey.md — survey template for an authorized source.
16. docs/16-dependencies-and-version-policy.md — Python, package inventory, and release locking policy.
17. docs/17-source-integration.md — structured export replay and configurable DOM worker.

AI coding agents should start with AGENTS.md. The source-specific adapter cannot be completed until docs/15-source-survey.md has been filled for an authorized website or export.

The source-independent pipeline can be tried with `docker compose run --rm replay-export-demo`. See docs/17-source-integration.md for its JSONL contract and the observation-only DOM trial. The demo uses a separate synthetic table ID and does not validate a real website.

## Trying an authorized real page

Use only a site you are permitted to observe and follow its terms. Do not put credentials, cookies, tokens, balances, or personal screenshots in the repository. The current browser command does not log in. If the page requires a session, design a permitted session mechanism without bypassing access controls.

Capture at a fixed viewport, update config/real_lobby.example.yaml for that exact screenshot, and inspect the annotated preview:

    docker compose run --rm preview python -m agent.cli preview \
      --image assets/my_lobby.png --config config/real_lobby.example.yaml \
      --out output/my_lobby_roi.png

The assets mount is read-only inside Docker. Put your authorized screenshot on the host first. The current real-lobby ROI coordinates are only approximate; do not use them as validated ground truth.

A real adapter must extract a trustworthy round ID, phase, final result, and roadmap revision, then pass the acceptance tests before automatic confirmed-round writes are enabled. Never map marker counts directly to Banker or Player rounds.

## Statistical limits

Reported rates describe the confirmed sample, not a betting edge. The current strict streak definition treats Tie and GAP as breaks. Wilson intervals express sampling uncertainty but do not correct missing tables, selection bias, hidden shoes, or wrong labels. The application cannot infer other players' stakes from a roadmap.
