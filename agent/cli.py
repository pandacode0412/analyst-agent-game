"""CLI for observation, reviewed import, structured source replay, and reports."""
import argparse
import asyncio
import csv
import json
import signal
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import cv2
from .analytics import TZ
from .adapters.dom import load_dom_config
from .browser import capture_page, monitor_browser, monitor_dom_browser
from .config import load_regions
from .report import export_daily
from .red_report import export_red_window
from .streak_report import export_streak_window
from .run_settings import plan_run
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
    # Unset flags fall back to the config's run: block (docs/17), then to built-in defaults.
    p.add_argument("--iterations", type=int, default=None,
                   help="Capture count; 0 = no limit. Default: until run.stop_at, else 3")
    p.add_argument("--interval", type=float, default=None, help="Seconds between captures (run.interval_seconds)")
    p.add_argument("--trusted-round-ids", action="store_true", default=None,
                   help="Enable only after this exact source/layout and ID rule pass labeled review")
    p.add_argument("--report-on-exit", action="store_true", default=None,
                   help="Print and export the reached-13 report when the worker stops")
    p.add_argument("--report-start", default=None, help="Local window start for the exit report")
    p.add_argument("--report-end", default=None, help="Local window end for the exit report")
    p.add_argument("--report-dir", default=None)
    p.add_argument("--start-now", action="store_true", help="Ignore run.start_at and start immediately")
    p.add_argument("--duration-minutes", type=float, default=None,
                   help="Stop after this many minutes (the earlier of this and run.stop_at wins)")
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
    p = sub.add_parser("report-streaks",
                       help="Banker and Player runs reaching 13 in a local window, both Tie policies")
    p.add_argument("--date", required=True, help="YYYY-MM-DD in Asia/Ho_Chi_Minh")
    p.add_argument("--source", required=True, help="Source value stored with confirmed rounds")
    p.add_argument("--start", default="07:00", help="Local window start HH:MM (default 07:00)")
    p.add_argument("--end", default="21:00", help="Local window end HH:MM, exclusive; 24:00 allowed")
    p.add_argument("--red-outcome", choices=("BANKER", "PLAYER"),
                   help="Optional color label; omit until the source mapping is verified")
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


def _wait_until(start_utc: datetime) -> None:
    """Sleep until the planned start; Ctrl+C or docker stop still interrupts."""
    remaining = (start_utc - datetime.now(timezone.utc)).total_seconds()
    if remaining > 1:
        print(f"waiting_until={start_utc.astimezone(TZ).isoformat(timespec='minutes')}", flush=True)
    while remaining > 0:
        time.sleep(min(remaining, 30))
        remaining = (start_utc - datetime.now(timezone.utc)).total_seconds()


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def _report_on_exit(args, plan) -> None:
    """Print the reached-13 headline for the run's start date and write the workbook.

    Never masks the reason the worker stopped.
    """
    try:
        source = load_dom_config(args.config).source_id
        with connect(args.database_url) as conn:
            filename, data = export_streak_window(conn, plan.report_day, source, plan.report_dir,
                                                  plan.report_start, plan.report_end)
        print("\n".join(data["headline"]), flush=True)
        print(f"Excel written: {filename}", flush=True)
    except Exception as exc:
        print(f"report_on_exit_failed={type(exc).__name__}: {exc}", flush=True)


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
        signal.signal(signal.SIGTERM, _raise_interrupt)  # docker stop -> clean shutdown
        config = load_dom_config(args.config)
        plan = plan_run(config.run, datetime.now(timezone.utc), iterations=args.iterations,
                        interval=args.interval, trusted=args.trusted_round_ids,
                        report_on_exit=args.report_on_exit, report_start=args.report_start,
                        report_end=args.report_end, report_dir=args.report_dir,
                        start_now=args.start_now, duration_minutes=args.duration_minutes)
        stop_text = plan.stop_utc.astimezone(TZ).isoformat(timespec="minutes") if plan.stop_utc else "none"
        print(f"run_plan start={plan.start_utc.astimezone(TZ).isoformat(timespec='minutes')} "
              f"stop={stop_text} iterations={plan.iterations or 'unlimited'} "
              f"interval={plan.interval_seconds}s trusted={plan.trusted_round_ids} "
              f"report_on_exit={plan.report_on_exit}", flush=True)
        stop_reason = "COMPLETED"
        try:
            _wait_until(plan.start_utc)
            asyncio.run(monitor_dom_browser(args.config, args.database_url, args.output_dir,
                                            plan.iterations, plan.interval_seconds,
                                            plan.trusted_round_ids, stop_utc=plan.stop_utc,
                                            login_reminder_seconds=plan.login_reminder_seconds))
        except KeyboardInterrupt:
            stop_reason = "STOPPED_BY_OPERATOR"
        except BaseException:
            stop_reason = "FAILED"
            raise
        finally:
            print(f"monitor_stopped reason={stop_reason}", flush=True)
            if plan.report_on_exit:
                _report_on_exit(args, plan)
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
    elif args.command == "report-streaks":
        report_day = date.fromisoformat(args.date)
        with connect(args.database_url) as conn:
            filename, data = export_streak_window(conn, report_day, args.source, args.output_dir,
                                                  args.start, args.end, args.red_outcome)
        print("\n".join(data["headline"]))
        print(f"Excel written: {filename}")
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
