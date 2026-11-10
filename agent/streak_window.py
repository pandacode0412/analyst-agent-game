"""Banker/Player runs reaching 13 in an operator-chosen local window.

Implements the requested metric in docs/07-statistics-and-excel.md: both sides,
two named Tie policies, one event per run at its 13th result, and an all-table
headline. Reads confirmed rounds only. Coverage cannot be inferred here.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from .analytics import TZ

THRESHOLD = 13
SIDES = ("BANKER", "PLAYER")
STRICT = "reached_13_strict_v1"
TIE_TRANSPARENT = "reached_13_tie_transparent_v1"
POLICIES = (STRICT, TIE_TRANSPARENT)
_LOOKBACK_BATCH = 100


def parse_clock(value: str) -> tuple[int, int]:
    """Parse HH:MM; 24:00 is allowed as the end of the day."""
    try:
        hours, minutes = (int(part) for part in value.split(":"))
    except ValueError as exc:
        raise ValueError(f"time must be HH:MM, got {value!r}") from exc
    if not (0 <= minutes < 60 and (0 <= hours < 24 or (hours, minutes) == (24, 0))):
        raise ValueError(f"time must be between 00:00 and 24:00, got {value!r}")
    return hours, minutes


def window_bounds(day: date, start: str = "07:00", end: str = "21:00") -> tuple[datetime, datetime]:
    """Return the UTC half-open interval for a local [start, end) on one date."""
    def local(clock: str) -> datetime:
        hours, minutes = parse_clock(clock)
        if hours == 24:
            return datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
        return datetime.combine(day, time(hours, minutes), tzinfo=TZ)
    begin, finish = local(start), local(end)
    if begin >= finish:
        raise ValueError("window start must be earlier than end; midnight-crossing windows are not supported")
    return begin.astimezone(timezone.utc), finish.astimezone(timezone.utc)


def _sort_key(row: dict):
    return row["at_utc"], 0 if row["kind"] == "GAP" else 1, row["event_id"]


def count_run_events(rows: list[dict], start: datetime, end: datetime,
                     policy: str) -> list[dict]:
    """Return one event per table run whose 13th Banker or Player result is in [start, end)."""
    if policy not in POLICIES:
        raise ValueError(f"unknown Tie policy {policy!r}")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("window bounds must be aware and increasing")
    by_table: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_table[row["table_id"]].append(row)
    found = []
    for table_id, events in sorted(by_table.items()):
        side, length, first, source = None, 0, None, None
        for row in sorted(events, key=_sort_key):
            if row["at_utc"] >= end:
                break
            if row["kind"] == "GAP":
                side, length, first = None, 0, None
                continue
            if source is not None and row["source"] != source:
                side, length, first = None, 0, None
            source = row["source"]
            result = row["result"]
            if result == "TIE":
                if policy == STRICT:
                    side, length, first = None, 0, None
                continue
            if result == side:
                length += 1
            else:
                side, length, first = result, 1, row
            if length == THRESHOLD and start <= row["at_utc"] < end:
                found.append({
                    "table_id": table_id, "side": side, "policy": policy,
                    "source": row["source"],
                    "first_round_id": first["round_id"], "thirteenth_round_id": row["round_id"],
                    "first_utc": first["at_utc"], "thirteenth_utc": row["at_utc"],
                    "first_evidence_ref": first.get("second_evidence_ref"),
                    "thirteenth_evidence_ref": row.get("second_evidence_ref"),
                })
    return found


def lookback_complete(prior_desc: list[dict]) -> bool:
    """True when events before the window settle run continuity for both policies.

    prior_desc is newest first. A strict run needs at most 13 events; a
    tie-transparent run can hide any number of Ties, so keep reading until a
    breaking event, a side change, or 13 same-side results.
    """
    side, counted = None, 0
    for row in prior_desc:
        if row["kind"] == "GAP":
            return True
        if row["result"] == "TIE":
            continue
        if side is None:
            side = row["result"]
        elif row["result"] != side:
            return True
        counted += 1
        if counted >= THRESHOLD:
            return True
    return False


_EVENTS_SQL = """
    SELECT * FROM (
        SELECT r.id AS event_id, r.table_id, r.finished_at_utc AS at_utc,
            'ROUND' AS kind, r.result, r.round_id, r.source, e.second_evidence_ref
        FROM confirmed_rounds r LEFT JOIN source_round_evidence e
            ON e.source_id = r.source AND e.table_id = r.table_id
            AND e.stored_round_id = r.round_id
        WHERE r.table_id = %(table)s AND r.source = %(source)s
            AND r.finished_at_utc >= %(low)s AND r.finished_at_utc < %(high)s
        UNION ALL
        SELECT id AS event_id, table_id, detected_at_utc AS at_utc,
            'GAP' AS kind, NULL AS result, NULL AS round_id, NULL AS source,
            NULL AS second_evidence_ref
        FROM observation_gaps
        WHERE table_id = %(table)s
            AND detected_at_utc >= %(low)s AND detected_at_utc < %(high)s
    ) history
"""
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _prior_events(conn, table_id: str, source: str, start: datetime) -> list[dict]:
    """Read history newest-first in batches until run continuity at start is settled."""
    prior: list[dict] = []
    while True:
        batch = [dict(row) for row in conn.execute(
            _EVENTS_SQL + " ORDER BY at_utc DESC, kind DESC, event_id DESC LIMIT %(limit)s OFFSET %(offset)s",
            {"table": table_id, "source": source, "low": _EPOCH, "high": start,
             "limit": _LOOKBACK_BATCH, "offset": len(prior)})]
        prior.extend(batch)
        if len(batch) < _LOOKBACK_BATCH or lookback_complete(prior):
            return prior


def streak_window_data(conn, day: date, source: str, start: str = "07:00", end: str = "21:00",
                       red_outcome: str | None = None) -> dict:
    """Per table, side, and Tie policy counts plus an all-table headline."""
    if not source or not source.strip():
        raise ValueError("source is required")
    if red_outcome not in (None, "BANKER", "PLAYER"):
        raise ValueError("red_outcome must be BANKER, PLAYER, or omitted")
    low, high = window_bounds(day, start, end)
    tables = [row["table_id"] for row in conn.execute("""
        SELECT DISTINCT table_id FROM confirmed_rounds
        WHERE source = %s AND finished_at_utc >= %s AND finished_at_utc < %s
        ORDER BY table_id""", (source, low, high))]
    rows: list[dict] = []
    round_counts, gap_counts, spans = {}, {}, {}
    for table_id in tables:
        # Gaps are keyed by table only, so another provider on this table ID
        # would make continuity unknowable. Fail closed.
        if conn.execute("""SELECT 1 FROM confirmed_rounds
                WHERE table_id = %s AND source <> %s LIMIT 1""", (table_id, source)).fetchone():
            raise ValueError(f"multiple sources use table {table_id}; source namespace migration required")
        current = [dict(row) for row in conn.execute(
            _EVENTS_SQL + " ORDER BY at_utc, kind, event_id",
            {"table": table_id, "source": source, "low": low, "high": high})]
        round_counts[table_id] = sum(row["kind"] == "ROUND" for row in current)
        played = [row for row in current if row["kind"] == "ROUND"]
        spans[table_id] = (played[0], played[-1]) if played else (None, None)
        gap_counts[table_id] = sum(row["kind"] == "GAP" for row in current)
        rows.extend(_prior_events(conn, table_id, source, low))
        rows.extend(current)
    events = [event for policy in POLICIES for event in count_run_events(rows, low, high, policy)]
    counts = {table_id: {policy: {side: 0 for side in SIDES} for policy in POLICIES}
              for table_id in tables}
    totals = {policy: {side: 0 for side in SIDES} for policy in POLICIES}
    for event in events:
        counts[event["table_id"]][event["policy"]][event["side"]] += 1
        totals[event["policy"]][event["side"]] += 1
    if red_outcome is None:
        colors = {"BANKER": "UNVERIFIED", "PLAYER": "UNVERIFIED"}
    else:
        colors = {red_outcome: "RED", ("PLAYER" if red_outcome == "BANKER" else "BANKER"): "BLUE"}
    data = {
        "date": day.isoformat(), "timezone": TZ.key, "source": source,
        "window_start_local": start, "window_end_local": end,
        "color_mapping": colors, "coverage_status": "UNKNOWN",
        "tables_observed": len(tables), "totals": totals, "events": events,
        "summary": [{"table_id": table_id, "confirmed_rounds": round_counts[table_id],
                     "recorded_gaps": gap_counts[table_id], "counts": counts[table_id],
                     "first_round_utc": spans[table_id][0]["at_utc"] if spans[table_id][0] else None,
                     "last_round_utc": spans[table_id][1]["at_utc"] if spans[table_id][1] else None,
                     "first_round_no": round_label(spans[table_id][0]["round_id"]) if spans[table_id][0] else "",
                     "last_round_no": round_label(spans[table_id][1]["round_id"]) if spans[table_id][1] else "",
                     "coverage_status": "UNKNOWN"} for table_id in tables],
    }
    data["headline"] = headline_lines(data)
    return data


POLICY_LABELS = {STRICT: "Tie breaks run", TIE_TRANSPARENT: "Tie skipped"}


def round_label(round_id: str | None) -> str:
    """Short round number: the last segment of a stored key (for example the shoe position)."""
    return str(round_id or "").rsplit(":", 1)[-1]


def local_time(moment) -> str:
    """Report-local timestamp, YYYY-MM-DD HH:MM:SS in Asia/Ho_Chi_Minh."""
    return moment.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S") if moment else ""


def headline_lines(data: dict) -> list[str]:
    """Operator-facing summary, one line per Tie policy (docs/07 headline)."""
    def side_label(side: str) -> str:
        color = data["color_mapping"][side]
        return side.capitalize() if color == "UNVERIFIED" else f"{side.capitalize()} ({color.lower()})"
    lines = [f"Date {data['date']}, window {data['window_start_local']}–{data['window_end_local']} "
             f"({data['timezone']}), source {data['source']}, coverage {data['coverage_status']}"]
    for policy in POLICIES:
        totals = data["totals"][policy]
        lines.append(f"{POLICY_LABELS[policy]} ({policy}): "
                     f"{side_label('BANKER')} {totals['BANKER']}, {side_label('PLAYER')} {totals['PLAYER']}, "
                     f"total {totals['BANKER'] + totals['PLAYER']} events across {data['tables_observed']} tables")
    return lines
