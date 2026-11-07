# 15 — Source survey template before writing an adapter

Copy this template into a separate private record for **each authorized website or export**. Do not place passwords, cookies, tokens, balances, or unmasked personal screenshots in the repository. Leave unknown answers as NOT DETERMINED; do not guess.

## A. Authorization and scope

| Question | Answer |
|---|---|
| Source name and responsible owner | NOT DETERMINED |
| Permission for automated observation, allowed rate, and retention rules | NOT DETERMINED |
| Permitted official API or export, if any | NOT DETERMINED |
| Tables and hours in scope | NOT DETERMINED |
| Screenshot access, masking, and deletion policy | NOT DETERMINED |

## B. UI and identity

| Question | Answer |
|---|---|
| Page type and permitted session mechanism | NOT DETERMINED |
| Viewport, zoom, scale, and layout version | NOT DETERMINED |
| Visible table label, reordering, scrolling, and lazy loading | NOT DETERMINED |
| Round ID location and whether it resets per shoe/session | NOT DETERMINED |
| Shoe/session ID and source finish timestamp availability | NOT DETERMINED |
| BETTING/DEALING/RESULT signals and their display duration | NOT DETERMINED |
| Final Banker/Player/Tie source and update delay | NOT DETERMINED |
| Roadmap type and Tie/pair/reset/scroll semantics | NOT DETERMINED |
| Published final outcome represented by red in this exact source/layout; evidence for the mapping | NOT DETERMINED |
| Reporting time zone, 07:00–21:00 coverage, and treatment of results at the boundaries | NOT DETERMINED |

## C. Samples to collect

Capture at least one permitted, labeled example of a normal round, Banker, Player, Tie, shoe change, disconnect, logout, reordered card, full/scrolled roadmap, repeated frame, and theme/layout change. Record UTC time, table ID, viewport, file hash, and reviewer. Mask account information before sharing captures.

## D. Feasibility decision

| Decision | Answer |
|---|---|
| Can the adapter automatically verify rounds? Which evidence is sufficient? | NOT DETERMINED |
| Without a trusted ID, can continuity and restart recovery be demonstrated? | NOT DETERMINED |
| Which tables/hours remain observation-only or manually reviewed? | NOT DETERMINED |
| Parser version, approver, and approval date | NOT DETERMINED |

Use the survey to finalize TableEvidence fields in docs/13-integration-contracts.md and the corpus/tests in docs/14-acceptance.md.
