"""CLI for observation, reviewed import, structured source replay, and reports."""
import argparse
import asyncio
import csv
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import cv2
from .analytics import TZ
from .browser import capture_page, monitor_browser, monitor_dom_browser
from .config import load_regions
from .report import export_daily
from .red_report import export_red_window
from .adapters.structured import StructuredExportAdapter
from .coordinator import SourceCoordinator
from .site_adapter import CapturedFrame
from .storage import connect, insert_verified_round, mark_gap, record_observations
from .vision import analyze_frame, load_image


def _args():
    parser = argparse.ArgumentParser(prog="python -m agent.cli", description="Baccarat analytics PoC (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview", help="Annotate screenshot ROIs; NOT round results")
    p.add_argument("--image", default="assets/synthetic_lobby.png")
    p.add_argument("--config", default="config/synthetic_tables.yaml")
    p.add_argument("--out", default="output/roi_preview.png")
    p = sub.add_parser("monitor-image", help="Repeat static screenshot observations; NOT round results")
    p.add_argument("--image", default="assets/synthetic_lobby.png")
    p.add_argument("--config", default="config/synthetic_tables.yaml")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--interval", type=float, default=0.2)
    p = sub.add_parser("capture-browser", help="Screenshot public/browser-accessible page, without login")
    p.add_argument("--url", default="https://example.com")
    p.add_argument("--out", default="output/browser_capture.png")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--wait-ms", type=int, default=3000)
    p = sub.add_parser("monitor-browser", help="Monitor ROIs in browser; outcomes remain UNCONFIRMED")
    p.add_argument("--url", default="https://example.com")
    p.add_argument("--config", default="config/synthetic_tables.yaml")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p.add_argument("--output-dir", default="output/observations")
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--interval", type=float, default=5)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p = sub.add_parser("monitor-dom", help="Observe an authorized DOM layout; trusted IDs require source review")
    p.add_argument("--config", default="config/real_dom.example.yaml")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p.add_argument("--output-dir", default="output/dom_evidence")
    p.add_argument("--iterations", type=int, default=3, help="0 runs continuously")
    p.add_argument("--interval", type=float, default=5)
    p.add_argument("--trusted-round-ids", action="store_true",
                   help="Enable only after this exact source/layout and ID rule pass labeled review")
    p = sub.add_parser("ingest-csv", help="Import ONLY manually reviewed / trusted results")
    p.add_argument("--input", default="samples/verified_demo.csv")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p = sub.add_parser("ingest-gaps", help="Record known observation gaps from CSV")
    p.add_argument("--input", default="samples/gaps_demo.csv")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p = sub.add_parser("report", help="Export Excel for selected HCMC local day")
    p.add_argument("--date", help="YYYY-MM-DD; default yesterday in Asia/Ho_Chi_Minh")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p.add_argument("--output-dir", default="output/reports")
    p = sub.add_parser("report-red-window", help="Export verified 13-red events in local [07:00, 21:00)")
    p.add_argument("--date", required=True, help="YYYY-MM-DD in Asia/Ho_Chi_Minh")
    p.add_argument("--source", required=True, help="Source value stored with reviewed rounds")
    p.add_argument("--red-outcome", choices=("BANKER", "PLAYER"), required=True,
                   help="Published final outcome represented by red on this source; verify first")
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    p.add_argument("--output-dir", default="output/reports")
    p = sub.add_parser("replay-export", help="Validate a structured, authorized source export")
    p.add_argument("--input", required=True, help="JSONL with capture and per-table state")
    p.add_argument("--source-id", required=True)
    p.add_argument("--tables", required=True, help="Comma-separated approved table IDs")
    p.add_argument("--trusted-round-ids", action="store_true",
                   help="Enable only after the source ID/phase/result contract was independently validated")
    p.add_argument("--globally-unique-ids", action="store_true",
                   help="Use only if round IDs never reset per shoe")
    p.add_argument("--max-frame-gap-seconds", type=float, default=30)
    p.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    return parser.parse_args()


def main():
    args = _args()
    if args.command in ("preview", "monitor-image"):
        frame = load_image(args.image)
        overlay, readings = analyze_frame(frame, load_regions(args.config))
        if args.command == "preview":
            output = Path(args.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output), overlay)
            print(json.dumps({"preview": str(output), "observations": readings,
                              "warning": "marker count != round count"}, ensure_ascii=False, indent=2))
        else:
            if args.iterations < 1:
                raise ValueError("iterations must be positive")
            with connect(args.database_url) as conn:
                for i in range(args.iterations):
                    record_observations(conn, readings, str(args.image))
                    print(f"observation_frame={i+1}, confirmed_rounds_written=0", flush=True)
                    if i + 1 < args.iterations:
                        time.sleep(args.interval)
    elif args.command == "capture-browser":
        asyncio.run(capture_page(args.url, args.out, args.width, args.height, args.wait_ms))
    elif args.command == "monitor-browser":
        if args.iterations < 1:
            raise ValueError("iterations must be positive")
        asyncio.run(monitor_browser(args.url, args.config, args.database_url, args.output_dir,
                                    args.iterations, args.interval, args.width, args.height))
    elif args.command == "monitor-dom":
        asyncio.run(monitor_dom_browser(args.config, args.database_url, args.output_dir,
                                        args.iterations, args.interval,
                                        args.trusted_round_ids))
    elif args.command == "ingest-csv":
        inserted, duplicate = 0, 0
        with open(args.input, newline="", encoding="utf-8-sig") as f, connect(args.database_url) as conn:
            with conn.transaction():
                rows = list(csv.DictReader(f))
                for row in rows:
                    if row.get("verified", "").strip().upper() != "YES":
                        raise ValueError(f"Unverified CSV row: table={row.get('table_id')} round={row.get('round_id')}")
                    created = insert_verified_round(conn,
                        table_id=row["table_id"].strip(), round_id=row["round_id"].strip(),
                        finished_at_utc=row["finished_at_utc"].strip(), result=row["result"].strip().upper(),
                        method=row["method"].strip(), source=row["source"].strip(),
                        reviewer=row["reviewer"].strip())
                    inserted += int(created)
                    duplicate += int(not created)
        print(f"Verified CSV import: inserted={inserted}, exact_duplicates={duplicate}")
    elif args.command == "ingest-gaps":
        with open(args.input, newline="", encoding="utf-8-sig") as f, connect(args.database_url) as conn:
            with conn.transaction():
                for row in csv.DictReader(f):
                    mark_gap(conn, row["table_id"], row["detected_at_utc"], row["reason"])
        print("Gaps imported. Note: importing same gaps twice creates duplicates; use once for demo.")
    elif args.command == "report":
        report_day = date.fromisoformat(args.date) if args.date else (datetime.now(TZ).date() - timedelta(days=1))
        with connect(args.database_url) as conn:
            filename = export_daily(conn, report_day, args.output_dir)
        print(f"Excel written: {filename}")
    elif args.command == "report-red-window":
        report_day = date.fromisoformat(args.date)
        with connect(args.database_url) as conn:
            filename = export_red_window(conn, report_day, args.red_outcome, args.source, args.output_dir)
        print(f"Excel written: {filename}; coverage=UNKNOWN; verify red mapping for this source")
    elif args.command == "replay-export":
        expected = {name.strip() for name in args.tables.split(",") if name.strip()}
        adapter = StructuredExportAdapter(args.source_id,
                                          trusted_round_ids=args.trusted_round_ids,
                                          ids_reset_per_shoe=not args.globally_unique_ids)
        counts: dict[str, int] = {}
        with connect(args.database_url) as conn, open(args.input, encoding="utf-8") as source_file:
            coordinator = SourceCoordinator(conn, args.source_id, expected,
                                            args.max_frame_gap_seconds)
            for line_number, line in enumerate(source_file, 1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("source_id") != args.source_id:
                    raise ValueError(f"line {line_number}: source_id does not match")
                frame = CapturedFrame(source_id=args.source_id,
                                      frame_id=str(payload["frame_id"]),
                                      captured_at_utc=str(payload["captured_at_utc"]),
                                      evidence_ref=str(payload["evidence_ref"]), payload=payload)
                for status in coordinator.process_frame(frame, adapter).values():
                    counts[status] = counts.get(status, 0) + 1
        print(json.dumps({"source": args.source_id, "statuses": counts,
                          "warning": "Structured export trust and coverage require source validation"},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
