# 10 — Roadmap from demo to a multi-table system

The detailed target requirements, integration contract, acceptance plan, and source questionnaire are in chapters 12–15. Start source-specific work only after an authorized source has been surveyed.

Before a production-oriented release, complete the Python and container version controls in docs/16-dependencies-and-version-policy.md. The current POC has no committed transitive dependency lock or immutable image digest.

## Phase 0 — Understand the prototype

Run preview and inspect its ROIs. Run monitor-image and verify that confirmed rounds do not increase. Import synthetic CSV, generate Excel, and read the code. Exit condition: the team can explain the difference between observations and confirmed rounds.

## Phase 1 — One source, then 3–6 tables

Fix viewport and table identity. Create labeled image/video evidence covering phases, Banker, Player, Tie, reset, and disconnect. Configure or implement and validate a source adapter and round-ID trust rules. The generic FSM, coordinator, evidence persistence, conflict review, and restart rebaseline are implemented; prove they work for the selected source and layout. Measure precision, recall, missed rounds, duplicates, and coverage on held-out sessions. Exit condition: the metrics meet predeclared per-table thresholds and every confirmed result has evidence.

Confirm what the source's red marker means before using the existing 07:00–21:00 report on real data. The report now includes source evidence references when available; extend it with measured coverage after verified rounds and gap handling are reliable. Validate its boundary, per-table, and reached-13 cases A13–A16.

## Phase 2 — Continuous Compose operation

Harden the existing DOM worker loop with measured backoff, heartbeat, permitted session lifecycle, page freshness checks, rate limits, and graceful shutdown. Retain GAP logging and checkpoints. Use the existing PostgreSQL store with bounded connections; back up and restore it; rotate logs and retain minimal screenshots. Schedule an idempotent daily report. Run a 24–72 hour soak test including planned outages and restarts. Exit condition: downtime and unknown coverage are visible and state survives restart.

## Phase 3 — Larger deployments

Verify that the source and infrastructure actually allow simultaneous access to all target tables. Benchmark browser sessions, CPU, memory, tab throttling, database connections, and frame latency while scaling gradually. Assign one worker owner per table group and introduce a queue only when measured load requires it. Add a read-only dashboard for coverage, freshness, delays, confirmed, and unknown. Test restarts, network loss, table reordering, and roadmap resets. Exit condition: every table meets its quality and coverage targets.

## Definition of done

- Each confirmed round has a trustworthy key and evidence; marker counts alone never confirm rounds.
- Duplicate and conflict handling survive restart and concurrent processing.
- GAP, UNKNOWN, and low coverage appear in reports.
- Excel documents time zone, provenance, methodology, and synthetic data.
- Results are checked against held-out ground truth, not only the synthetic demo.
- No betting automation or unsupported probability claim is presented.

## Decisions to record

| Decision | Why it matters |
|---|---|
| Lobby screenshot or individual table tabs | Coverage and browser cost |
| Stable source round ID and shoe namespace | Deduplication and recovery |
| Roadmap type and Tie semantics | Correct outcome interpretation |
| Permission for automated observation | Access and acceptable rate |
| Evidence retention period | Privacy and storage cost |
| Required statistics | Scope and report design |

Reference links: [Playwright Docker](https://playwright.dev/python/docs/docker), [OpenCV contours](https://docs.opencv.org/4.x/d4/d73/tutorial_py_contours_begin.html), [Docker Compose](https://docs.docker.com/compose/), [Psycopg 3](https://www.psycopg.org/psycopg3/docs/), [PostgreSQL backup](https://www.postgresql.org/docs/17/backup.html), [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html), [Wizard of Odds Baccarat basics](https://wizardofodds.com/games/baccarat/basics/).
