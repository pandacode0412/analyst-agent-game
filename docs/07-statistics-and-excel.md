# 07 — Excel and historical statistics

## Five workbook sheets

| Sheet | Purpose |
|---|---|
| Summary | Per-table confirmed totals, Banker/Player/Tie, Banker rate and Wilson interval, strict streaks, gaps, observed frames |
| Rounds | Each confirmed round with ID, UTC time, result, method, source, reviewer |
| Streaks | Strict runs with result, length, start/end, and whether Banker reached 13 |
| Quality | Recorded observation gaps and warnings |
| Methodology | Time zone, synthetic-data warning, Tie/GAP rules, and statistical assumptions |

The workbook is output/reports/baccarat_daily_YYYY-MM-DD.xlsx. If any row uses DEMO_FIXTURE, the report marks the day as synthetic. Keep demo and real data in separate databases.

## Definitions

Observed Banker share is confirmed Banker rounds divided by all confirmed Banker, Player, and Tie rounds. For zero confirmed rounds, the rate and interval stay blank rather than implying 0%.

A strict streak is consecutive results of one side. Player, Tie, or GAP ends a Banker streak; Banker, Tie, or GAP ends a Player streak. A maximal Banker run of length at least 13 counts as one reached-13 streak, not as every overlapping 13-round window. The implementation computes streaks within the selected report day.

For k Banker rounds among n confirmed rounds, Wilson 95% uses z=1.959963984540054:

    p = k/n
    denominator = 1 + z²/n
    center = (p + z²/(2n)) / denominator
    half_width = z * sqrt(p(1-p)/n + z²/(4n²)) / denominator
    interval = [center-half_width, center+half_width]

The interval describes sampling uncertainty under its model. It does not repair selection bias, missed rounds, wrong labels, or unknown shoe composition.

## Interpretation

A run of 13 Banker outcomes does not make Player the guaranteed next outcome. The original guide cites approximate standard eight-deck starting-shoe probabilities of Banker 45.86%, Player 44.62%, and Tie 9.52%; exact rules and remaining cards matter. A screen history alone does not establish a betting edge. Do not issue betting signals from streaks.

The synthetic CSV includes a B51 run of 13 Banker rounds, followed by Tie, then Banker and Player. The report gives max_banker_strict=13 and streak_13_banker=1.

## Requested metric: 13-in-a-row events (agreed 2026-11-07)

This is the operator's target question. It supersedes the narrower red-only description below as the requirement. It is implemented by `agent/streak_window.py`, `agent/streak_report.py`, and the read-only `report-streaks` command for stored confirmed rounds; it still has no real-source validation or coverage ledger.

- **Sides.** Count runs of verified `BANKER` results and runs of verified `PLAYER` results separately. Red and blue are display colors; the stored truth is the published final outcome. Because both sides are counted, a verified color mapping is needed only to *label* a side as red or blue in the workbook, not to compute the counts. Until the mapping is verified, label the columns BANKER and PLAYER and show the color mapping as `UNVERIFIED`. Tie runs are not counted.
- **Threshold.** A run produces **one event when its 13th result finishes**. A run of 14 or 20 is still one event. This is `reached_13`; an `exactly_13` statistic is not requested.
- **Two Tie policies, both reported under distinct names:**

  | Metric name | Tie | GAP, UNKNOWN, untrusted ID, source change, shoe change |
  |---|---|---|
  | `reached_13_strict_v1` | Breaks the run | Breaks the run |
  | `reached_13_tie_transparent_v1` | Skipped: neither breaks the run nor adds to its length (matches how a Big Road usually draws Tie) | Breaks the run |

  Opposite-side results break the run under both policies. A new shoe breaks the run under both policies unless the source survey proves that the source's own roadmap continues across shoes. Never present one policy's number under the other's name.
- **Window.** The operator chooses a local half-open window `[start, end)` within one calendar date in `Asia/Ho_Chi_Minh`. The default is `[07:00, 21:00)`; `[00:00, 24:00)` (the whole day) is allowed. `start` must be earlier than `end`; windows crossing midnight are out of scope for version 1. The event belongs to the window containing its 13th result, even when the run began before `start`. Runs are tracked across the window boundaries so a run started before `start` is not truncated.
- **Lookback.** To decide continuity at `start`, read prior events per table and side until either 13 counted results or a breaking event is found. Under the tie-transparent policy, Ties do not count toward those 13, so a fixed "last 13 rows" lookback is insufficient.
- **Headline summary.** The first thing the operator reads is one line per Tie policy for the whole day's window across all observed tables, for example:

      Date 2026-11-07, window 07:00–21:00 (Asia/Ho_Chi_Minh), source <source>, coverage UNKNOWN
      Tie breaks run (reached_13_strict_v1):           Banker 3, Player 2, total 5 events across 12 tables
      Tie skipped   (reached_13_tie_transparent_v1):   Banker 4, Player 2, total 6 events across 12 tables

  "Across N tables" is the number of tables with at least one confirmed round in the window, not the number of tables on the site. The total is Banker plus Player events; each event belongs to one table. The headline must always carry the coverage status, so a reader does not mistake an observed count for a complete count. All report text (headline, sheet names, column headers, methodology) is in English.
- **Output.** For each source/table: confirmed rounds, recorded gaps, the local time (Asia/Ho_Chi_Minh, `YYYY-MM-DD HH:MM:SS`) of the first and last confirmed round in the window, and the event count per side and Tie policy. Per side and policy: the sum across tables (table-level events are never merged into a cross-table run). For each event: table, side, policy, run start and 13th-result local times, minutes from run start to the 13th result, the short round numbers ("round #") and full stored round keys of the first and 13th rounds, UTC times, source, and evidence references when stored. A short round number is the last segment of the stored key, for example the shoe-local position. Coverage stays `UNKNOWN` until a coverage ledger exists, so every count is an observed verified count, not a complete census.

Worked example for one table, default window, no gaps: 6 Banker, Tie, 7 Banker finishing at 08:00 gives `reached_13_strict_v1` = 0 and `reached_13_tie_transparent_v1` = 1 for BANKER. On the same table, 13 Player results with the 13th at 15:00 add 1 PLAYER event under both policies. With window `[00:00, 24:00)` the same data give the same counts; with `[09:00, 21:00)` the Banker event at 08:00 is excluded.

Run it after importing or recording verified rounds:

    docker compose run --rm report python -m agent.cli report-streaks \n      --date 2026-10-19 --source DEMO_FIXTURE --start 07:00 --end 21:00

The command prints the headline and writes `output/reports/baccarat_streak13_YYYY-MM-DD_HHMM-HHMM_<source-hash>.xlsx` with Headline, Per table, Events, and Methodology sheets. `--start`/`--end` set the window (`--end 24:00` for the whole day). `--red-outcome BANKER|PLAYER` only adds color labels; omit it until the source mapping is verified, and the workbook shows `UNVERIFIED`. Shoe boundaries are not detected by this report; until the source records them, rely on recorded gaps. Acceptance cases A17–A20 in docs/14-acceptance.md cover the Tie policies, both sides, window assignment, and the long tie-transparent lookback.

The older `report-red-window` command below remains for compatibility: one side per run, strict Tie policy only, fixed 07:00–21:00 window, and a 13-row lookback that is correct only for the strict policy.

## Current implementation: red streaks from 07:00 to 21:00

This section describes the implemented subset of the requested metric above: one side, strict Tie policy, fixed window. It is implemented by the separate `report-red-window` command for stored confirmed rounds, **not by the current daily workbook**. The existing `streak_13_banker` is a whole-day Banker metric; it cannot be presented as the requested red count without a verified source-specific color mapping and time-window calculation.

- Configure one local time zone, initially `Asia/Ho_Chi_Minh`, and use the half-open interval `[07:00, 21:00)` for each calendar date. A result at 07:00 is in scope; a result at 21:00 is outside it. Store and compare UTC finish times, then convert for display.
- Configure `RED` only after the authorized source survey confirms which published final outcome its red marker represents. Keep the source's final `BANKER`, `PLAYER`, or `TIE` label as the stored truth. Marker counts or color alone never create a round.
- Process verified rounds independently for each stable source/table identity, in result order. Opposite-side results, Tie, a known GAP, an untrusted ID, or loss of continuity end the current strict red run. A new shoe does not automatically join two runs; follow the verified source continuity rule.
- Maintain the run across 07:00 and 21:00 so boundary handling is honest. The requested count increases **once when the 13th verified red result in a run finishes inside the window**. A run of 14 or 20 does not produce another count. If its 13th result occurred before 07:00, continued red results inside the window do not count it again. A run reaching 13 at or after 21:00 belongs outside that day's window.
- Report the per-table count and a sum across tables, plus each counted run's source/table, first and 13th round IDs, local and UTC timestamps, and evidence references when the source pipeline stored them. The sum counts table-level events; it never merges results from different tables. The current report shows confirmed-round and recorded-gap counts, but marks coverage `UNKNOWN` because no independently measured continuous-source coverage ledger exists yet. Therefore its count is observed verified events, not a guaranteed complete total.
- A future `exactly_13_completed_runs` statistic would qualify a maximal run only when it ends at length 13. This differs from the requested `reached_13_events`, which includes longer runs. A run whose end is unobserved cannot yet be classified as exactly 13.

Worked example for one table: 12 verified red results before 07:00 followed by one at 07:05 produce one `reached_13_events` in the window. If that run continues to 14, it still produces one event and zero `exactly_13_completed_runs`. A separate run reaches its 13th red at 20:59 and adds one event. A third run reaches 13 at 21:00 and adds none. The target count for this table is **2**, assuming no gaps or uncertain rounds.

The `exactly_13_completed_runs` statistic is a future extension; it is not exported now. The current database also cannot prove a run's continuity across an unrecorded outage or shoe reset. Verify the source's red mapping and data provenance before using the report.

Run the separate workbook after importing trusted, reviewed rounds:

    docker compose run --rm report python -m agent.cli report-red-window \
      --date 2026-10-19 --source DEMO_FIXTURE --red-outcome BANKER

Choose `PLAYER` instead only if the surveyed website maps red to the published Player result. Set `--source` to the exact source value stored with the reviewed rounds. The command writes `output/reports/baccarat_red_13_YYYY-MM-DD_07-21_<source-hash>.xlsx` with Summary, Reached 13 events, and Methodology sheets. The hash distinguishes reports from different sources without placing their names in filenames. Marker observations are excluded. The current schema cannot safely combine two sources that reuse a table ID, so the report rejects that case. Never treat the `UNKNOWN` coverage status as a complete census.

## Report another day

    docker compose run --rm report python -m agent.cli report --date 2026-10-19

Without --date, Python chooses yesterday in Asia/Ho_Chi_Minh. The default Compose report command explicitly passes the sample REPORT_DATE instead; override it as above for another day.
