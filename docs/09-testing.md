# 09 — Tests and troubleshooting

## Required scenarios

| ID | Scenario | Expected result |
|---|---|---|
| T01 | Preview the synthetic six-table image | ROIs align and visible marker counts are nonzero |
| T02 | Capture the same image 100 times | More observations; zero new confirmed rounds |
| T03 | Import the 46-round CSV twice | First import +46; second +0 with duplicates reported |
| T04 | Reuse one round ID with a different result | Conflict; existing row remains unchanged |
| T05 | 13 Banker, then Tie, then Banker | Maximum strict Banker run 13; one run reaches 13 |
| T06 | Banker → GAP → Banker | Two separate runs |
| T07 | B51 Banker and B20 Player | Independent table summaries |
| T08 | Local 23:59 and 00:00 boundary | Correct day assignment, no double count |
| T09 | Page logged out | No confirmed outcome; quality warning in target implementation |
| T10 | Viewport, zoom, or card position changes | Block wrong ROI mapping |
| T11 | Network outage | GAP; no streak across unknown interval |
| T12 | Restart while RESULT remains visible | No duplicate confirmed round |
| T13 | Tie overlay | No extra round from a secondary marker |
| T14 | Shoe change or roadmap reset | Rebaseline before confirmation |
| T15 | Same source key with conflicting data | Quarantine; no silent correction |

The 72 current tests and CLI demo cover only parts of T01–T08, PostgreSQL storage behavior, legacy migration, report export, red-window boundary and gap rules, mixed-source rejection, a synthetic structured candidate-to-storage flow, and a Chromium DOM-reader smoke test. Seventeen PostgreSQL integration tests run when RUN_PG_TESTS=1 and one browser smoke test runs when RUN_BROWSER_TESTS=1; Compose supplies both. T11 (missing-table/capture gap), T12 (restart), and T15 (conflict quarantine) have synthetic structured-source tests; T02 is covered at the candidate-pipeline level by a 100-identical-frame test and a check that marker paths do not reference round writers. T09–T15 all still need a validated named-source adapter, real labeled evidence, and held-out integration tests before they count as accepted. The full acceptance matrix is in docs/14-acceptance.md.

## Commands

    python3 -m unittest discover -s tests -v
    docker compose run --rm test

To observe import deduplication, run docker compose run --rm import-demo twice on a disposable demo database. The second run should print inserted=0 and exact_duplicates=46. Avoid running import-gaps-demo twice.

## Ground truth for a real UI

Start with 200–500 ended rounds across 3–6 tables and varied phases, outcomes, layouts, resets, and outages, subject to access and privacy rules. Two people label table ID, source round ID, final outcome, timing, and gaps independently. Resolve disagreements against evidence. Split calibration and held-out sets by session/day. Report precision, recall, duplicates, missed rounds, coverage, and gap detection per table. A proposed release target is at least 99% confirmation precision and zero duplicate confirmed rows; those are criteria, not measured prototype results.

## Troubleshooting

- Docker daemon unavailable: start Docker Desktop/Engine and check user permissions.
- PostgreSQL unhealthy or connection refused: check docker compose ps db, POSTGRES_* values in .env, and whether the named volume was initialized with different credentials. Do not delete a non-demo volume to fix a login error.
- Image pull or build fails: check registry access, network, and Playwright image tag.
- No Excel output: check the date, imported confirmed data, output mount, and write permissions. Observations alone produce no rounds.
- Empty workbook: the chosen day has no confirmed rounds, or only observations.
- ROI shifted: match screenshot dimensions, zoom, and config; inspect the overlay manually.
- Wrong marker counts: recalibrate HSV/contours with labeled real images; inspect Tie/pair icons.
- CONFLICT on import: review the original evidence; do not manually overwrite the database.
- Login screenshot: the current browser has no session; do not bypass access controls.
- Time appears seven hours off: distinguish UTC storage from Asia/Ho_Chi_Minh report time.
- Import error for cv2/numpy/yaml: install requirements.txt; it is an environment problem, not a passed business test.

In the rebuilt Docker image, all 72 tests passed against PostgreSQL 17 and Chromium. Without a running database or Chromium, twenty-one integration tests skip and the other fifty-one run. docker compose run --rm test enables both integration groups on a machine with Docker. The generated preview, structured export, and sample Excel are synthetic; real-source accuracy still needs separate evaluation.
