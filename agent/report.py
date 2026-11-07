"""Create five-sheet Excel for a locally verified day (uses XlsxWriter at runtime)."""
from datetime import date
from pathlib import Path
import xlsxwriter
from .analytics import daily_data


def export_daily(conn, day: date, output_dir: str | Path) -> Path:
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        data = daily_data(conn, day)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outfile = output_dir / f"baccarat_daily_{day.isoformat()}.xlsx"
    wb = xlsxwriter.Workbook(str(outfile))
    navy, teal, red, orange = "#14243C", "#007B75", "#BD3D42", "#F9EAD4"
    title_fmt = wb.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": navy})
    header_fmt = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": teal, "text_wrap": True,
                                 "border": 0, "valign": "vcenter"})
    pct_fmt = wb.add_format({"num_format": "0.00%"})
    info_fmt = wb.add_format({"font_color": "#5B6B80", "italic": True})
    warn_fmt = wb.add_format({"font_color": "#883900", "bg_color": orange, "text_wrap": True})

    def sheet(name: str, cols: list[str], widths: list[int]):
        sh = wb.add_worksheet(name)
        sh.hide_gridlines(2)
        sh.freeze_panes(3, 0)
        sh.merge_range(0, 0, 0, len(cols)-1, f"BACCARAT | {name} | {day.isoformat()}", title_fmt)
        sh.set_row(0, 29)
        for c, (head, width) in enumerate(zip(cols, widths)):
            sh.write(2, c, head, header_fmt)
            sh.set_column(c, c, width)
        sh.set_row(2, 31)
        return sh

    s = sheet("Summary", ["Table", "Confirmed rounds", "Banker", "Player", "Tie", "Banker %",
                           "Wilson 95% low", "Wilson 95% high", "Max Banker streak", "Streaks >=13", "Gaps", "Frames seen"],
              [13, 18, 12, 12, 10, 15, 19, 19, 19, 15, 11, 16])
    for r, item in enumerate(data["summary"], 3):
        vals = [item["table_id"], item["total"], item["banker"], item["player"], item["tie"],
                item["banker_pct"], item["banker_ci_low"], item["banker_ci_high"],
                item["max_banker_strict"], item["streak_13_banker"], item["gaps"], item["observation_frames"]]
        for c, value in enumerate(vals):
            s.write_blank(r, c, None) if value is None else s.write(r, c, value, pct_fmt if c in (5,6,7) else None)
    last_summary = 3 + len(data["summary"])
    s.write(last_summary + 2, 0, "SYNTHETIC DATA — NOT A REAL OBSERVATION" if data["is_demo"] else
            "VERIFIED DATA — review the Quality sheet before interpretation", warn_fmt)
    s.write(last_summary + 3, 0, "Historical rates do not reliably predict the next round.", info_fmt)

    rsh = sheet("Rounds", ["Table", "Round ID", "Finished UTC", "Result", "Method", "Source", "Reviewer"],
                [14, 23, 30, 17, 24, 26, 24])
    for row_idx, item in enumerate(data["rounds"], 3):
        for c, k in enumerate(["table_id","round_id","finished_at_utc","result","method","source","reviewer"]):
            rsh.write(row_idx, c, str(item[k]))

    stsh = sheet("Streaks", ["Table", "Result", "Length", "Start UTC", "End UTC", "Reached 13"],
                 [14, 18, 15, 31, 31, 15])
    for row_idx, item in enumerate(data["streaks"], 3):
        for c, value in enumerate([item["table_id"],item["result"],item["length"],item["start_utc"],
                                   item["end_utc"],"YES" if item["length"] >= 13 else "NO"]):
            stsh.write(row_idx, c, value)

    qsh = sheet("Quality", ["Table", "Type", "UTC", "Notes"], [14, 18, 31, 56])
    idx = 3
    for gap in data["gaps"]:
        for c, value in enumerate([gap["table_id"], "GAP", gap["detected_at_utc"], gap["reason"]]):
            qsh.write(idx, c, value)
        idx += 1
    if not data["gaps"]:
        qsh.write(idx, 0, "No GAP is recorded; this does not imply 100% coverage", warn_fmt)
    qsh.write(idx + 2, 0, "ROI marker observations are not verified rounds", info_fmt)

    msh = sheet("Methodology", ["Item", "Rule / limitation"], [26, 110])
    notes = [
        ("Data status", "DEMO FIXTURE — not real data" if data["is_demo"] else
                        "Confirmed rounds only; review provenance in the Rounds sheet"),
        ("Time zone", "Asia/Ho_Chi_Minh; local day is [00:00:00, next 00:00:00)"),
        ("Outcomes", "BANKER, PLAYER, TIE; imported rows require round ID and reviewer"),
        ("Strict streak", "Tie or GAP breaks a streak; calculated within the report day"),
        ("13 Banker", "One maximal streak of length >=13 counts once; overlapping windows do not"),
        ("Markers", "Colored UI markers are observations, not a count of completed rounds"),
        ("Wilson 95%", "Descriptive binomial interval; a representative sample is still required"),
        ("Prediction", "No next-round inference or betting recommendation"),
        ("Missing data", "Missed-round count is unknown without continuous IDs or a source ledger"),
        ("Access", "Use only sources you are allowed to view and follow their terms"),
    ]
    for r, (key, value) in enumerate(notes, 3):
        msh.write(r, 0, key)
        msh.write(r, 1, value)
    wb.close()
    return outfile
