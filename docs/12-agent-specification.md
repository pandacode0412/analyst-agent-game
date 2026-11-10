# 12 — Specification for the Baccarat analytics agent

## Purpose and boundary

Collect **verified historical results** from multiple Baccarat tables, measure data coverage, aggregate by day and table, and produce traceable reports. The output is descriptive statistics. There is no betting action, game control, betting signal, or guarantee about the next round.

Current state: this repository is a prototype. Preview, marker monitoring, a configurable DOM reader, structured export replay, transactional reviewed CSV import, PostgreSQL, daily Excel, a separate verified-round 07:00–21:00 red-streak Excel report, a conservative FSM, and a source coordinator with evidence and checkpoint storage have code. It lacks a validated adapter for a named real website, measured coverage, managed session lifecycle, and production soak results.

## Inputs, users, and outputs

| Group | Definition |
|---|---|
| Inputs | Authorized UI or export; captures from a screen the operator may observe; independently reviewed CSV |
| Users | Operator, data reviewer, report reader |
| Current outputs | PostgreSQL observations, confirmed_rounds, observation_gaps, and the migration 003 source tables (evidence, conflicts, source gaps, processed frames, checkpoints); five-sheet daily Excel; three-sheet 07:00–21:00 red-window Excel |
| Target outputs | Evidence-backed rounds, per-table quality/coverage, and conflict/unknown lists |
| Time | Store UTC; current daily report boundary is Asia/Ho_Chi_Minh |

## Functional requirements

| ID | Requirement | Current state | Acceptance condition |
|---|---|---|---|
| F01 | Assign the correct table_id to each observation | Partial | Reordered cards never assign results to a different table; mismatch becomes UNKNOWN/GAP |
| F02 | Keep frames separate from rounds | Implemented; tests replay 100 identical frames through the candidate pipeline and check that marker paths do not reference round writers | 100 identical frames add zero confirmed rounds |
| F03 | Extract phase, ID, final result, and revision from a real source | Configurable DOM reader and structured export adapter; no named source validated | Evidence and tests exist for each source/layout |
| F04 | Confirm each round once | Structured source coordinator and durable writer implemented; real source trust pending | Independent frames, trusted ID, consistent final result, no restart duplication |
| F05 | Mark missing or unknowable data | Structured source gaps for restart, out-of-order timestamps, capture gaps, unknown phase, adapter errors, and missing tables implemented; page-content freshness (a frozen page) is not detected; real page behavior unvalidated | Outage, stale frame, ROI shift, and shoe change are recorded and break continuity |
| F06 | Aggregate outcomes, streaks, and Wilson 95% | Implemented | Confirmed only; by table/day; Tie/GAP breaks strict streak |
| F07 | Show provenance and quality | Partial | Synthetic/real source, confirmed count, gaps, unknown, and coverage are visible |
| F08 | Recover and run on a schedule | Checkpoint, continuous DOM loop, and a login-session lifecycle (human CAPTCHA, automatic re-login otherwise) exist; health, measured session lifetime, soak, and report scheduling remain | Backoff, heartbeat, checkpoint, and idempotent daily report |
| F09 | Handle conflict | Structured source conflicts quarantined; manual CSV conflicts raise | Never overwrite; queue both payloads and evidence for review |
| F10 | Count verified Banker runs and Player runs that first reach 13 in an operator-chosen local window (default 07:00–21:00), under both a strict and a tie-transparent Tie policy | Partial: `report-streaks` implements both sides, both Tie policies, the operator window, and the headline from stored confirmed rounds; no real-source validation, shoe-boundary detection, or coverage ledger | Definition in chapter 07; one event per maximal run at its 13th result; per table, side, and policy counts, totals, evidence, and coverage; color labels only after verified mapping; A13–A20 pass |

## Target data flow

    Authorized source → capture → frame envelope and quality checks
                             ├→ ROI/marker observations → PostgreSQL, never a round
                             └→ source adapter → TableEvidence → per-table FSM
                                                     ├→ UNKNOWN/GAP → quality log
                                                     └→ VerifiedResult → evidence and validation
                                                                         → single writer → confirmed_rounds
    confirmed_rounds + gaps + coverage → analytics → Excel/read-only API

The source adapter and confirmed_round write path are a trust boundary. No marker-count shortcut is allowed. Use one adapter per approved source and versioned layout; do not assume one heuristic works across sites.

## Components to implement

1. **Capture and clock:** frame UTC time, monotonic sequence, viewport, source ID, URL/page state; detect duplicate/stale frames, page errors, and logout. Database insertion time is not automatically round finish time.
2. **Identity and layout:** verify a displayed table name and layout version before cropping. A mismatch blocks that table's confirmation.
3. **Source adapter:** produce TableEvidence with field-level provenance and quality. High OCR confidence alone does not make round_id_trusted true.
4. **Validator:** one FSM per table, building on ConservativeRoundValidator; add freshness, sequence, shoe/reset, and restart recovery.
5. **Event store:** save confirmed results, gaps, evidence metadata, and conflicts atomically or through one writer queue. Include source/shoe namespace if IDs can collide.
6. **Analytics and report:** read a consistent snapshot and display confirmed, unknown, gap, and coverage per table. Version metric definitions if semantics change.
7. **Operations:** health, structured logs, stale/low-coverage alerts, backup/restore, capture retention, and access control.

## Business invariants

- Each confirmed result has a stable (source, table, round) identity, Banker/Player/Tie outcome, UTC finish time or documented estimate, and retrievable evidence.
- Conflicting results for one key require review; never silently replace the old row.
- Missing ID, phase, final outcome, or freshness means UNKNOWN. Lost continuity means GAP, not an inferred round.
- Rates use confirmed rounds only. Show coverage so missing data is not mistaken for zero games.
- Tie breaks the current strict streak. Different roadmap semantics need a separately named/versioned metric.
- Synthetic data must use a separate database.
- Never interpret a site's red color as Banker or Player without a validated mapping for that source/layout. Count 13-in-a-row events only from verified results, independently by table and side, using the window and Tie-policy rules in chapter 07.

## Decisions before a real adapter

Complete docs/15-source-survey.md for each source: access permission/rate, ID stability across shoes, where final results appear, Tie rules, UI latency, viewport/layout, number of simultaneously visible tables, and evidence retention. If no trustworthy source ID exists, use a local sequence only after continuity and restart recovery have been demonstrated. Otherwise keep manual verification.

## Delivery milestones

| Milestone | Reviewable output | Exit gate |
|---|---|---|
| M0 — current prototype | Synthetic preview/CSV/structured export/Excel, red-window and reached-13 streak reports, and 72 tests, seventeen requiring PostgreSQL, one Chromium, and three both | Runs on target machine; team understands data is synthetic and coverage is unknown |
| M1 — one real table | Adapter, labeled corpus, evidence viewer | Held-out criteria in chapter 14 pass |
| M2 — 3–6 tables | Worker, checkpoint, gap/conflict, coverage report | 24–72 hour soak and per-table comparison |
| M3 — scale | CPU/RAM/latency benchmark and worker groups | Per-table quality does not decline; backup/restore and alerts pass |

Do not promise dates for M1–M3 until an authorized source has been surveyed.
