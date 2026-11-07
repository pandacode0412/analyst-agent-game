"""Verified red-result streak events in a local reporting window.

The caller must supply a source-validated mapping from RED to BANKER or PLAYER.
Missing source coverage cannot be inferred from the stored rounds.
"""
from collections import defaultdict, deque
from datetime import date, datetime, time, timezone

from .analytics import TZ


def window_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(7), tzinfo=TZ)
    end = datetime.combine(day, time(21), tzinfo=TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def count_red_events(rows: list[dict], red_outcome: str, start: datetime, end: datetime) -> list[dict]:
    """Count each run once, at the 13th verified red result, per table."""
    if red_outcome not in ("BANKER", "PLAYER"):
        raise ValueError("red_outcome must be BANKER or PLAYER")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("window bounds must be aware and increasing")
    by_table: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_table[row["table_id"]].append(row)
    found = []
    for table_id, events in sorted(by_table.items()):
        recent = deque(maxlen=13)
        streak_length = 0
        current_source = None
        ordered = sorted(events, key=lambda row: (
            row["at_utc"], 0 if row["kind"] == "GAP" else 1, row["event_id"]))
        for row in ordered:
            if row["at_utc"] >= end:
                break
            if row["kind"] == "ROUND" and current_source is not None and row["source"] != current_source:
                recent.clear()
                streak_length = 0
            if row["kind"] == "GAP" or row["result"] != red_outcome:
                recent.clear()
                streak_length = 0
                if row["kind"] == "ROUND":
                    current_source = row["source"]
                continue
            current_source = row["source"]
            recent.append(row)
            streak_length = min(streak_length + 1, 14)
            if streak_length == 13 and start <= row["at_utc"] < end:
                found.append({
                    "table_id": table_id,
                    "first_round_id": recent[0]["round_id"],
                    "thirteenth_round_id": row["round_id"],
                    "first_utc": recent[0]["at_utc"],
                    "thirteenth_utc": row["at_utc"],
                    "source": row["source"],
                    "first_evidence_ref": recent[0].get("second_evidence_ref"),
                    "thirteenth_evidence_ref": row.get("second_evidence_ref"),
                })
    return found


def red_window_data(conn, day: date, red_outcome: str, source: str) -> dict:
    if red_outcome not in ("BANKER", "PLAYER"):
        raise ValueError("red_outcome must be BANKER or PLAYER")
    if not source or not source.strip():
        raise ValueError("source is required")
    start, end = window_bounds(day)
    active_tables = [row["table_id"] for row in conn.execute("""
        SELECT DISTINCT table_id FROM confirmed_rounds
        WHERE source = %s AND finished_at_utc >= %s AND finished_at_utc < %s
        ORDER BY table_id
    """, (source, start, end))]
    events = []
    gap_counts = {}
    round_counts = {}
    for table_id in active_tables:
        # Version 1 keys gaps only by table, so mixing provider histories for
        # one table ID would make continuity unknowable. Fail closed.
        mixed = conn.execute("""SELECT 1 FROM confirmed_rounds
            WHERE table_id = %s AND source <> %s LIMIT 1""", (table_id, source)).fetchone()
        if mixed:
            raise ValueError(f"multiple sources use table {table_id}; source namespace migration required")
        # The last 13 prior events suffice: either 13 reds already reached the
        # threshold, or a reset lies within those 13 events.
        before = [dict(row) for row in conn.execute("""
            SELECT * FROM (
                SELECT r.id AS event_id, r.table_id, r.finished_at_utc AS at_utc,
                    'ROUND' AS kind, r.result, r.round_id, r.source,
                    e.second_evidence_ref
                FROM confirmed_rounds r LEFT JOIN source_round_evidence e
                    ON e.source_id = r.source AND e.table_id = r.table_id
                    AND e.stored_round_id = r.round_id
                WHERE r.table_id = %s AND r.source = %s AND r.finished_at_utc < %s
                UNION ALL
                SELECT id AS event_id, table_id, detected_at_utc AS at_utc,
                    'GAP' AS kind, NULL AS result, NULL AS round_id, NULL AS source,
                    NULL AS second_evidence_ref
                FROM observation_gaps WHERE table_id = %s AND detected_at_utc < %s
            ) history ORDER BY at_utc DESC, kind DESC, event_id DESC LIMIT 13
        """, (table_id, source, start, table_id, start))]
        current = [dict(row) for row in conn.execute("""
            SELECT * FROM (
                SELECT r.id AS event_id, r.table_id, r.finished_at_utc AS at_utc,
                    'ROUND' AS kind, r.result, r.round_id, r.source,
                    e.second_evidence_ref
                FROM confirmed_rounds r LEFT JOIN source_round_evidence e
                    ON e.source_id = r.source AND e.table_id = r.table_id
                    AND e.stored_round_id = r.round_id
                WHERE r.table_id = %s AND r.source = %s
                    AND r.finished_at_utc >= %s AND r.finished_at_utc < %s
                UNION ALL
                SELECT id AS event_id, table_id, detected_at_utc AS at_utc,
                    'GAP' AS kind, NULL AS result, NULL AS round_id, NULL AS source,
                    NULL AS second_evidence_ref
                FROM observation_gaps
                WHERE table_id = %s AND detected_at_utc >= %s AND detected_at_utc < %s
            ) window_events ORDER BY at_utc, kind, event_id
        """, (table_id, source, start, end, table_id, start, end))]
        round_counts[table_id] = sum(row["kind"] == "ROUND" for row in current)
        gap_counts[table_id] = sum(row["kind"] == "GAP" for row in current)
        events.extend(before)
        events.extend(current)
    reached = count_red_events(events, red_outcome, start, end)
    summary = [{"table_id": table_id,
                "reached_13_events": sum(item["table_id"] == table_id for item in reached),
                "confirmed_rounds": round_counts[table_id],
                "recorded_gaps": gap_counts[table_id],
                "coverage_status": "UNKNOWN"} for table_id in active_tables]
    return {"date": day.isoformat(), "timezone": TZ.key, "source": source,
            "window_start_local": "07:00", "window_end_local": "21:00",
            "red_outcome": red_outcome, "summary": summary, "events": reached,
            "total_reached_13_events": len(reached), "coverage_status": "UNKNOWN"}
