# 14 — Testing and acceptance for the target agent

## Two test layers

**Prototype:** run python3 -m unittest discover -s tests -v with dependencies installed, or docker compose run --rm test. The 30 tests cover the conservative FSM, structured candidate-to-storage path, frame replay, source conflict quarantine, restart GAP, PostgreSQL deduplication, transactional rollback, one-time SQLite migration, report export, red-window boundaries and mixed-source rejection, strict streaks, gaps, local-day boundary, synthetic ROI, and a Chromium DOM-reader smoke test. Fourteen tests require PostgreSQL and one requires Chromium; Compose runs both. They do not establish accuracy on a real website.

**Real adapter:** create an independently labeled corpus for every source/layout. Preserve permitted captures, timestamps, table labels, phase, round ID, final result, shoe/reset, gaps, and unreadable states. Hold out entire sessions/days/tables from calibration.

## Ground truth workflow

1. Record source ID, UI version, viewport, UTC interval, table, permission, file hash, and deletion policy in a manifest.
2. Have two people label finished rounds and unobservable intervals independently; resolve disagreements by reviewing evidence.
3. Label insufficient evidence UNKNOWN. Do not use the agent's own output as truth.
4. Cover Banker, Player, Tie, pair overlay, shoe reset, reordered cards, scroll, logout, lag, stale frames, network loss, restart, and the Ho Chi Minh City midnight boundary.
5. Split calibration and held-out data by session, not by random adjacent frames of the same round.

The earlier 200–500 round suggestion across 3–6 tables is a starting corpus, not proof that rare errors are absent. Report metric confidence intervals and expand the corpus according to observed risk.

## Required metrics

| Metric | Meaning | Breakdown |
|---|---|---|
| Confirmation precision | TP/(TP+FP), matching table, ID, and outcome | Per table/source/layout and overall |
| Recall | TP/(TP+FN) over ground-truth ended rounds | Separate detector misses, gaps, and absent source signals |
| Duplicate rate | Extra repeated confirmed rows / emitted rows | After replay and restart |
| Conflict rate | Same key with different payload | Evidence and review outcome |
| Coverage | Observable time/rounds divided by in-scope time/rounds | Per table and hour; never extrapolate to hidden tables |
| Gap detection | Reported true gaps and detection delay | Outage, stale frame, layout change |
| Latency | Capture → confirm → report, p50/p95/p99 | By table count and hardware |

A correct color on the wrong table counts as both a false positive and a false negative. UNKNOWN is not confirmed. High precision from confirming almost nothing is insufficient without recall and coverage.

## Minimum integration matrix

| ID | Scenario | Expected result |
|---|---|---|
| A01 | Replay 100 identical frames | Zero new rounds |
| A02 | Stable BETTING → DEALING → RESULT with trusted ID | One round with two evidence frames |
| A03 | Banker changes to Player between RESULT frames | No confirmation; quality/conflict event |
| A04 | Tie overlay without new marker | One Tie only if final source result confirms it; strict streak breaks |
| A05 | Round ID resets after shoe change | No key collision; correct gap/rebaseline |
| A06 | Disconnect or stale frame | UNKNOWN/GAP; no streak across missing interval |
| A07 | Table card reorders or ROI shifts | Block wrong mapping |
| A08 | Restart while RESULT is displayed | No duplicate; recover safely or await a new cycle |
| A09 | Two writers process one key | One row or a reviewed conflict, with evidence preserved |
| A10 | 23:59:59–00:00:01 local boundary | Correct day by documented time policy |
| A11 | CSV has an error midway | Production importer rolls back the whole batch |
| A12 | Report reruns at one watermark | Same checksum and no duplicate delivery |
| A13 | Twelve red results before 07:00, then the 13th at 07:00; run continues to 20 | One reached-13 event inside the window, with no repeat for results 14–20 |
| A14 | The 13th red result at 21:00 or a gap before the 13th | Zero in-window reached-13 events; gap breaks continuity |
| A15 | Two tables each first reach 13 inside the window | One event per table and two in the aggregate; no cross-table streak |
| A16 | Site red mapping unverified or coverage incomplete | No asserted red-streak total; show unknown mapping or incomplete coverage |

## Suggested release gate

For **each source/layout/table**, approve a held-out report showing at least 99% confirmation precision and zero duplicate confirmed rows, with recall and coverage meeting thresholds set before evaluation. Review all conflicts. No confirmed round may come from marker count alone. The 99% figure was a proposed criterion in the original testing guide, not a measured prototype result. Include sample sizes and uncertainty; gather more data if the sample is too small.

Before 24/7 operation, run a 24–72 hour soak including deliberate restart and network loss, then check backup/restore, report latency, and each table's quality. Do not scale table count if p95 latency causes missed rounds or coverage falls. Rerun regression corpus tests for every adapter release and store parser/validator versions.

## Acceptance package

Deliver a corpus manifest, labeling protocol, resolved disagreements, A01–A16 results, metrics by source/layout/table, false positive/negative cases, masked evidence links, source configuration, viewport, verified red mapping, Tie semantics, time policy, soak results, backup/restore results, and a named approval decision.
