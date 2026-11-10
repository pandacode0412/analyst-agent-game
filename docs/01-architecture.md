# 01 — Architecture and data flow

## Goal

For each day, report how many tables were observed; each table's confirmed Banker, Player, and Tie rounds; its longest strict Banker/Player streak; the number of Banker streaks reaching 13; missing data; and uncertainty around historical rates. This is descriptive analytics, not a prediction or betting system.

The separate `report-red-window` command answers a narrower question from stored confirmed rounds: from 07:00 to 21:00 in the fixed Asia/Ho_Chi_Minh time zone, how many distinct verified red-result streaks first reach 13 consecutive rounds on each table? The mapping from a site's red display to a final outcome must be established in its source survey. The current POC cannot automatically verify a live site's rounds or prove complete coverage.

## Separate evidence paths in the prototype

    Browser or demo image       Human-reviewed CSV       Structured export / configured DOM
             |                         |                              |
      table-specific ROI           CSV validation             source adapter + identity
             |                         |                              |
    OpenCV marker counts         duplicate check           per-table FSM + coordinator
             |                         |                              |
    PostgreSQL observations ─── never promoted           evidence + transactional writer
      (UNCONFIRMED)                   |                              |
                              PostgreSQL confirmed_rounds ←──────────┘
                                         |
                              daily and 07:00–21:00 Excel

There is no automatic arrow from marker observations to confirmed_rounds. A separate structured source path now connects extracted evidence to the FSM, coordinator, and durable writer. Its trust flag must be enabled only after source-specific acceptance tests. No named website adapter has passed that review. See docs/12-agent-specification.md, docs/13-integration-contracts.md, and docs/17-source-integration.md.

## Multiple tables

Each visible table has an ROI with x, y, width, height in raw screenshot pixels. A frame passes through every configured ROI; observations are tagged with table_id. If a table disappears or the layout changes, mark that table unknown or gapped rather than assigning another table's result to it.

A single lobby screenshot covers only visible tables. Pagination, scrolling, lazy loading, and background-tab throttling can hide rounds. Do not claim continuous coverage for tables that were not actually observed. Scaling needs permitted browser contexts or tabs, table ownership, and measured latency.

## Stored data classes

| Class | Meaning | Used for outcome rates? |
|---|---|---|
| observations | Red/blue marker counts seen in an ROI at a time | No |
| confirmed_rounds | One final result with a unique identity and verified source | Yes |
| observation_gaps | A known interruption that may break streak continuity | Used to break strict streaks |
| source_round_evidence | Two frame IDs and evidence references for each source-pipeline round | No; audit trail |
| source_conflicts | Quarantined payloads that disagree with a stored round | No; awaits review |
| source_gaps | Idempotent per-source gap events (also copied once into observation_gaps) | Indirectly, through observation_gaps |
| processed_source_frames, worker_checkpoints | Replay prevention and restart detection per source/table | No |

## Prototype and target system

The prototype provides static-image calibration, browser capture, PostgreSQL storage, transactional reviewed CSV import, a conservative FSM, a structured source coordinator with persistent checkpoints/gaps/evidence/conflicts, and Excel output. A production system also needs an authorized session lifecycle, a validated site-specific result/ID extractor, measured coverage, evidence retention, backup, monitoring, and measured precision/recall on labeled captures.

## Principal risks

- Reading the same frame hundreds of times must create zero new rounds.
- A shoe reset or roadmap redraw can look like a new round.
- Tie and pair icons can resemble result markers.
- Browser resize, zoom, theme changes, or card reordering can invalidate ROI mapping.
- Background tabs can stop rendering fresh frames.
- Full screenshots can expose account information; store minimal masked regions.
- A container restart cannot recover unseen rounds. Record a GAP and rebaseline.
