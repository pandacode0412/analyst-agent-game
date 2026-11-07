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

## Target report: red streaks from 07:00 to 21:00

This is the requested operational metric. It is implemented by the separate `report-red-window` command for stored confirmed rounds, **not by the current daily workbook**. The existing `streak_13_banker` is a whole-day Banker metric; it cannot be presented as the requested red count without a verified source-specific color mapping and time-window calculation.

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
