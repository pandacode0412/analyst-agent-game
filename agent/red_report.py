"""Excel summary of verified red streak threshold events."""
from datetime import date
from hashlib import sha256
from pathlib import Path

import xlsxwriter

from .analytics import TZ
from .red_window import red_window_data


def export_red_window(conn, day: date, red_outcome: str, source: str, output_dir: str | Path) -> Path:
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        data = red_window_data(conn, day, red_outcome, source)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    source_key = sha256(source.encode("utf-8")).hexdigest()[:12]
    outfile = destination / f"baccarat_red_13_{day.isoformat()}_07-21_{source_key}.xlsx"
    wb = xlsxwriter.Workbook(str(outfile))
    head = wb.add_format({"bold": True, "bg_color": "#14243C", "font_color": "white"})
    warning = wb.add_format({"bold": True, "font_color": "#883900", "bg_color": "#F9EAD4"})
    summary = wb.add_worksheet("Summary")
    for col, title in enumerate(("Table", "Reached 13", "Confirmed rounds", "Recorded gaps", "Coverage")):
        summary.write(0, col, title, head)
    summary.set_column(0, 0, 18)
    summary.set_column(1, 3, 20)
    summary.set_column(4, 4, 22)
    for index, row in enumerate(data["summary"], 1):
        for col, key in enumerate(("table_id", "reached_13_events", "confirmed_rounds",
                                   "recorded_gaps", "coverage_status")):
            summary.write(index, col, row[key])
    total_row = len(data["summary"]) + 2
    summary.write(total_row, 0, "Total", head)
    summary.write_number(total_row, 1, data["total_reached_13_events"])
    summary.write(total_row + 2, 0, "Coverage is UNKNOWN; counts are observed verified events, not a guaranteed complete total.", warning)

    details = wb.add_worksheet("Reached 13 events")
    columns = ("Table", "First round ID", "13th round ID", "First UTC", "13th UTC", "13th local",
               "Source", "First evidence", "13th evidence")
    for col, title in enumerate(columns):
        details.write(0, col, title, head)
    details.set_column(0, 2, 22)
    details.set_column(3, 5, 33)
    details.set_column(6, 6, 26)
    details.set_column(7, 8, 44)
    for index, row in enumerate(data["events"], 1):
        values = (row["table_id"], row["first_round_id"], row["thirteenth_round_id"],
                  row["first_utc"].isoformat(), row["thirteenth_utc"].isoformat(),
                  row["thirteenth_utc"].astimezone(TZ).isoformat(),
                  row["source"], row.get("first_evidence_ref") or "",
                  row.get("thirteenth_evidence_ref") or "")
        for col, value in enumerate(values):
            details.write(index, col, value)

    method = wb.add_worksheet("Methodology")
    method.set_column(0, 0, 27)
    method.set_column(1, 1, 110)
    notes = (
        ("Date", data["date"]),
        ("Source", data["source"]),
        ("Time zone", data["timezone"]),
        ("Window", "[07:00, 21:00); 21:00 is excluded"),
        ("RED mapped to", data["red_outcome"] + " — operator must verify against the exact source/layout"),
        ("Event rule", "One event when the 13th verified red result of a strict run finishes in the window"),
        ("Tie and GAP", "Both break a strict red run; runs can begin before 07:00"),
        ("Coverage", "UNKNOWN: this POC has no continuous-source coverage ledger"),
        ("Evidence", "Source-pipeline rounds include references; reviewed CSV rows may not"),
        ("Limit", "Historical description only; no prediction or betting signal"),
    )
    for index, (key, value) in enumerate(notes):
        method.write(index, 0, key, head)
        method.write(index, 1, value)
    wb.close()
    return outfile
