# 05 — Round verification and duplicate prevention

## The core problem

The agent needs an event meaning “round R120 has finished with Banker,” not a count of colored dots visible now. The prototype proves the reporting path with reviewed CSV and a synthetic structured export. Its FSM accepts already extracted evidence; a configurable DOM reader is wired in, but no named real page has been validated.

## Current teaching FSM and target workflow

agent/round_validator.py implements UNKNOWN → BETTING → DEALING → RESULT_PENDING → DONE. It requires a trusted round ID, changed roadmap revision, and two separate matching RESULT frames. It does not parse UI, persist state, or write PostgreSQL.

The structured coordinator now records UNKNOWN/GAP, rebaselines after restart or capture gaps, writes durable evidence, quarantines conflicts, and deduplicates processed frames. Real-source health, coverage, and layout accuracy still need validation.

## Example

- 12:00:00: B51 is BETTING with trusted source ID R120 and baseline revision A.
- 12:00:12: DEALING for R120. Write no round.
- 12:00:25: RESULT Banker with revision B. Hold it as a candidate.
- 12:00:30: An independent frame again shows R120, Banker, revision B. The FSM emits one VerifiedResult.
- The durable source writer records one B51/R120 round only after evidence and time checks. Reading the same result repeatedly or advancing to R121 must not create another R120 row.

This is a workflow example, not a claim about a particular site's display timing.

## Evidence levels

**A, preferred:** published final result plus trustworthy source round ID from the UI or a permitted official export, with consistent roadmap change.

**B, requiring separate validation:** a complete phase sequence and a tested roadmap mapping with no observation gap, using a persistent shoe/session-local sequence ID.

**B2, published shoe counters (requires separate validation):** some lobbies publish, as text, per-shoe counters `[total, Banker, Player, Tie]` but no round ID. A round is identified as `(source, table, local shoe namespace, total)`. A new round is accepted only when `total` rises by exactly 1 **and** exactly one of Banker/Player/Tie rises by exactly 1, seen on two independent frames after a BETTING (countdown) and DEALING frame of the same shoe position. A jump of more than one, a decrease (new shoe), an inconsistent delta, a missing card, or a changed card identity is UNKNOWN/GAP. The local shoe namespace is created when a shoe is first observed or after any break, so it never merges two observation periods; rounds missed while not observing are never inferred. See docs/17-source-integration.md.

**C, unconfirmed:** marker count, pixel differences, screenshot timestamps, resize, or hash changes alone. Keep these as observations.

## Invariants

1. One frame is not one round.
2. Confirmed records require a unique key per table and source/shoe namespace.
3. Missing or contradictory evidence remains UNKNOWN or conflict.
4. Store timezone-aware UTC event times; report by the documented local day.
5. GAP interrupts strict streaks.
6. Tables are independent; ROI position is not table identity.
7. Same key with conflicting results must be quarantined, never overwritten.
8. Restart while RESULT is displayed must not insert the previous round again.

## Edge cases

Tie may be an overlay; it still breaks the current strict streak definition. Roadmap reset or shoe change requires a new namespace or rebaseline. Network loss, stale images, logout, table reordering, scrolling, and lazy loading block confirmation for affected tables.

## Integration steps

Configure and validate an authorized source adapter that produces TableEvidence with a separate envelope for UTC capture time, source ID, and evidence reference. agent/site_adapter.py defines the contract; agent/pipeline.py returns a ConfirmedCandidate; agent/coordinator.py and agent/live_store.py handle ordered frames, GAP persistence, evidence, duplicate keys, and conflicts. The source's layout, page freshness, ID reset rule, and final result semantics must pass the held-out checks before enabling trusted round IDs. See docs/13-integration-contracts.md, docs/14-acceptance.md, and docs/17-source-integration.md.
