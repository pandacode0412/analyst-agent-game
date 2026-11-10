"""Excel export (English) for Banker/Player runs reaching 13 in a local window."""
from datetime import date
from hashlib import sha256
from pathlib import Path

import xlsxwriter

from .streak_window import (POLICIES, POLICY_LABELS, SIDES, local_time, round_label,
                            streak_window_data)


def export_streak_window(conn, day: date, source: str, output_dir: str | Path,
                         start: str = "07:00", end: str = "21:00",
                         red_outcome: str | None = None) -> tuple[Path, dict]:
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        data = streak_window_data(conn, day, source, start, end, red_outcome)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    source_key = sha256(source.encode("utf-8")).hexdigest()[:12]
    window = f"{start.replace(':', '')}-{end.replace(':', '')}"
    outfile = destination / f"baccarat_streak13_{day.isoformat()}_{window}_{source_key}.xlsx"
    wb = xlsxwriter.Workbook(str(outfile))
    head = wb.add_format({"bold": True, "bg_color": "#14243C", "font_color": "white", "text_wrap": True})
    big = wb.add_format({"bold": True, "font_size": 14})
    warning = wb.add_format({"bold": True, "font_color": "#883900", "bg_color": "#F9EAD4"})
    tz = data["timezone"]

    sheet = wb.add_worksheet("Headline")
    sheet.set_column(0, 0, 120)
    for row, line in enumerate(data["headline"]):
        sheet.write(row, 0, line, big if row else head)
    sheet.write(len(data["headline"]) + 1, 0,
                "Coverage is UNKNOWN: counts are observed verified events, not a guaranteed complete total.",
                warning)
    sheet.write(len(data["headline"]) + 2, 0, f"All times are local ({tz}) unless the column says UTC.")

    tables = wb.add_worksheet("Per table")
    columns = ["Table", "Confirmed rounds", "Recorded gaps",
               f"First round ({tz})", "First round #", f"Last round ({tz})", "Last round #"]
    for policy in POLICIES:
        columns += [f"{side.capitalize()} reached 13 — {POLICY_LABELS[policy]}" for side in SIDES]
    columns.append("Coverage")
    for col, title in enumerate(columns):
        tables.write(0, col, title, head)
    tables.set_row(0, 45)
    tables.set_column(0, 0, 10)
    tables.set_column(1, 2, 12)
    tables.set_column(3, 6, 21)
    tables.set_column(7, len(columns) - 1, 18)
    for index, item in enumerate(data["summary"], 1):
        values = [item["table_id"], item["confirmed_rounds"], item["recorded_gaps"],
                  local_time(item["first_round_utc"]), item["first_round_no"],
                  local_time(item["last_round_utc"]), item["last_round_no"]]
        for policy in POLICIES:
            values += [item["counts"][policy][side] for side in SIDES]
        values.append(item["coverage_status"])
        for col, value in enumerate(values):
            tables.write(index, col, value)
    total_row = len(data["summary"]) + 2
    tables.write(total_row, 0, "Total", head)
    tables.write_number(total_row, 1, sum(item["confirmed_rounds"] for item in data["summary"]))
    tables.write_number(total_row, 2, sum(item["recorded_gaps"] for item in data["summary"]))
    col = 7
    for policy in POLICIES:
        for side in SIDES:
            tables.write_number(total_row, col, data["totals"][policy][side])
            col += 1

    details = wb.add_worksheet("Events")
    headers = ("Table", "Side", "Tie policy", f"Run start ({tz})", f"13th result ({tz})",
               "Minutes to 13th", "First round #", "13th round #", "Source",
               "First round key", "13th round key", "Run start UTC", "13th result UTC",
               "First evidence", "13th evidence")
    for col, title in enumerate(headers):
        details.write(0, col, title, head)
    details.set_row(0, 30)
    details.set_column(0, 2, 16)
    details.set_column(3, 4, 21)
    details.set_column(5, 8, 14)
    details.set_column(9, len(headers) - 1, 34)
    for index, event in enumerate(data["events"], 1):
        minutes = (event["thirteenth_utc"] - event["first_utc"]).total_seconds() / 60
        values = (event["table_id"], event["side"], POLICY_LABELS[event["policy"]],
                  local_time(event["first_utc"]), local_time(event["thirteenth_utc"]), round(minutes, 1),
                  round_label(event["first_round_id"]), round_label(event["thirteenth_round_id"]),
                  event["source"], event["first_round_id"], event["thirteenth_round_id"],
                  event["first_utc"].isoformat(), event["thirteenth_utc"].isoformat(),
                  event.get("first_evidence_ref") or "", event.get("thirteenth_evidence_ref") or "")
        for col, value in enumerate(values):
            details.write(index, col, value)
    if not data["events"]:
        details.write(1, 0, "No run reached 13 in this window.")

    method = wb.add_worksheet("Methodology")
    method.set_column(0, 0, 30)
    method.set_column(1, 1, 110)
    mapping = ", ".join(f"{side}={color}" for side, color in data["color_mapping"].items())
    notes = (
        ("Date", data["date"]),
        ("Source", data["source"]),
        ("Time zone", tz),
        ("Window", f"[{data['window_start_local']}, {data['window_end_local']}); end excluded"),
        ("Color mapping", mapping + " — colors are labels only and must be verified for this source"),
        ("Event rule", "One event when the 13th result of a maximal Banker or Player run finishes in the window"),
        (f"{POLICY_LABELS[POLICIES[0]]} ({POLICIES[0]})",
         "Tie breaks the run; GAP, source change, and the opposite side also break it"),
        (f"{POLICY_LABELS[POLICIES[1]]} ({POLICIES[1]})",
         "Tie is skipped (no break, no length); GAP, source change, and the opposite side break it"),
        ("Round #", "Short round number = last segment of the stored round key (for example the shoe position)"),
        ("Shoe change", "Detected only when the source pipeline records it as a gap"),
        ("Coverage", "UNKNOWN: no continuous-source coverage ledger exists yet"),
        ("Limit", "Historical description only; no prediction or betting signal"),
    )
    for index, (key, value) in enumerate(notes):
        method.write(index, 0, key, head)
        method.write(index, 1, value)
    wb.close()
    return outfile, data
