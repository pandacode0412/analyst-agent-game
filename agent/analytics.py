"""Descriptive historical statistics only. No next-round betting prediction."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TZ)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denom
    return max(0.0, center - half), min(1.0, center + half)


def daily_data(conn, day: date) -> dict:
    start, end = day_bounds(day)
    rounds = [dict(r) for r in conn.execute("""SELECT table_id, round_id, finished_at_utc,
               result, method, source, reviewer FROM confirmed_rounds
               WHERE finished_at_utc >= %s AND finished_at_utc < %s
               ORDER BY table_id, finished_at_utc, id""", (start, end))]
    gaps = [dict(g) for g in conn.execute("""SELECT table_id, detected_at_utc, reason FROM observation_gaps
               WHERE detected_at_utc >= %s AND detected_at_utc < %s
               ORDER BY detected_at_utc, id""", (start, end))]
    observations = [dict(o) for o in conn.execute("""SELECT table_id, COUNT(*) AS frames FROM observations
               WHERE observed_at_utc >= %s AND observed_at_utc < %s GROUP BY table_id""", (start, end))]
    for row in rounds:
        row["finished_at_utc"] = row["finished_at_utc"].astimezone(timezone.utc).isoformat()
    for row in gaps:
        row["detected_at_utc"] = row["detected_at_utc"].astimezone(timezone.utc).isoformat()
    by_table: dict[str, list[dict]] = defaultdict(list)
    for r in rounds:
        by_table[r["table_id"]].append(dict(r, kind="ROUND", at=r["finished_at_utc"]))
    for g in gaps:
        by_table[g["table_id"]].append(dict(g, kind="GAP", at=g["detected_at_utc"]))
    obs = {o["table_id"]: o["frames"] for o in observations}
    summary: list[dict] = []
    streaks: list[dict] = []
    table_ids = sorted(set(by_table) | set(obs))
    for table_id in table_ids:
        events = sorted(by_table[table_id], key=lambda x: (x["at"], x["kind"] == "ROUND"))
        counts = {"BANKER": 0, "PLAYER": 0, "TIE": 0}
        current_type = None
        current_len = 0
        current_start = ""
        current_end = ""
        max_banker = 0
        max_player = 0
        gap_count = 0

        def flush():
            nonlocal max_banker, max_player
            if current_type in ("BANKER", "PLAYER") and current_len:
                streaks.append({"table_id": table_id, "result": current_type,
                                "length": current_len, "start_utc": current_start,
                                "end_utc": current_end})
                if current_type == "BANKER":
                    max_banker = max(max_banker, current_len)
                else:
                    max_player = max(max_player, current_len)

        for event in events:
            if event["kind"] == "GAP":
                gap_count += 1
                flush()
                current_type, current_len, current_start, current_end = None, 0, "", ""
                continue
            result = event["result"]
            counts[result] += 1
            if result == "TIE":
                flush()
                current_type, current_len, current_start, current_end = None, 0, "", ""
            elif result == current_type:
                current_len += 1
                current_end = event["at"]
            else:
                flush()
                current_type, current_len = result, 1
                current_start = current_end = event["at"]
        flush()
        total = sum(counts.values())
        ci_lo, ci_hi = wilson_interval(counts["BANKER"], total)
        summary.append({"table_id": table_id, "total": total,
                        "banker": counts["BANKER"], "player": counts["PLAYER"],
                        "tie": counts["TIE"], "banker_pct": counts["BANKER"] / total if total else None,
                        "banker_ci_low": ci_lo, "banker_ci_high": ci_hi,
                        "max_banker_strict": max_banker, "max_player_strict": max_player,
                        "streak_13_banker": sum(s["result"] == "BANKER" and s["length"] >= 13
                                                for s in streaks if s["table_id"] == table_id),
                        "gaps": gap_count, "observation_frames": obs.get(table_id, 0)})
    is_demo = any(r["source"] == "DEMO_FIXTURE" for r in rounds)
    return {"date": str(day), "summary": summary, "rounds": rounds,
            "streaks": streaks, "gaps": gaps, "is_demo": is_demo}
