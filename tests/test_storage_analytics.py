import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import psycopg
from psycopg import sql

from agent.analytics import daily_data, wilson_interval
from agent.config import load_regions
from agent.storage import connect, insert_verified_round, mark_gap
from agent.vision import analyze_frame, load_image
from agent.report import export_daily
from agent.red_report import export_red_window
from agent.red_window import red_window_data
from agent.streak_report import export_streak_window
from agent.streak_window import streak_window_data
from agent.adapters.structured import StructuredExportAdapter
from agent.coordinator import SourceCoordinator
from agent.live_store import save_candidate
from agent.pipeline import ConfirmedCandidate
from agent.site_adapter import CapturedFrame
from tools.migrate_sqlite_to_postgres import migrate


class PureAnalyticsTests(unittest.TestCase):
    def test_wilson_boundary(self):
        self.assertEqual(wilson_interval(0, 0), (None, None))
        low, high = wilson_interval(50, 100)
        self.assertLess(low, .5)
        self.assertGreater(high, .5)

    def test_vision_roi_is_observation_not_result(self):
        root = Path(__file__).resolve().parents[1]
        frame = load_image(root / "assets/synthetic_lobby.png")
        regions = load_regions(root / "config/synthetic_tables.yaml")
        overlay, observations = analyze_frame(frame, regions)
        self.assertEqual(overlay.shape, frame.shape)
        self.assertEqual(len(observations), 6)
        self.assertTrue(all(r["status"] == "OBSERVED_NOT_CONFIRMED" for r in observations))
        self.assertTrue(any(r["red_markers"] > 0 for r in observations))
        self.assertTrue(any(r["blue_markers"] > 0 for r in observations))


@unittest.skipUnless(os.getenv("RUN_PG_TESTS") == "1", "requires a PostgreSQL test service")
class PostgreSQLPipelineTests(unittest.TestCase):
    def setUp(self):
        self.schema = "test_" + uuid4().hex
        self.conninfo = os.getenv("DATABASE_URL", "")
        with psycopg.connect(self.conninfo, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn = connect(self.conninfo, schema=self.schema)

    def tearDown(self):
        self.conn.close()
        with psycopg.connect(self.conninfo, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def add(self, table_id, round_id, result, timestamp="2026-10-19T06:00:00Z"):
        return insert_verified_round(
            self.conn, table_id=table_id, round_id=round_id, finished_at_utc=timestamp,
            result=result, method="MANUAL_VERIFIED", source="UNIT_TEST", reviewer="QA"
        )

    def test_dedupe_and_conflict(self):
        self.assertTrue(self.add("B51", "id1", "BANKER"))
        self.assertFalse(self.add("B51", "id1", "BANKER"))
        with self.assertRaises(ValueError):
            self.add("B51", "id1", "PLAYER")
        self.assertEqual(daily_data(self.conn, date(2026, 10, 19))["summary"][0]["total"], 1)

    def test_exactly_13_streak_tie_break(self):
        for i in range(13):
            self.add("B51", f"s{i}", "BANKER", f"2026-10-19T06:{i:02d}:00Z")
        self.add("B51", "tie", "TIE", "2026-10-19T06:13:00Z")
        self.add("B51", "one", "BANKER", "2026-10-19T06:14:00Z")
        result = daily_data(self.conn, date(2026, 10, 19))
        summary = result["summary"][0]
        self.assertEqual(summary["total"], 15)
        self.assertEqual(summary["max_banker_strict"], 13)
        self.assertEqual(summary["streak_13_banker"], 1)
        self.assertEqual([row["length"] for row in result["streaks"]], [13, 1])

    def test_gap_breaks_streak(self):
        self.add("B07", "1", "BANKER", "2026-10-19T05:00:00Z")
        mark_gap(self.conn, "B07", "2026-10-19T05:01:00Z", "network_loss")
        self.add("B07", "2", "BANKER", "2026-10-19T05:02:00Z")
        result = daily_data(self.conn, date(2026, 10, 19))
        self.assertEqual(result["summary"][0]["max_banker_strict"], 1)
        self.assertEqual(result["summary"][0]["gaps"], 1)

    def test_tables_isolated(self):
        self.add("B51", "1", "BANKER")
        self.add("B20", "1", "PLAYER")
        summary = {r["table_id"]: r for r in daily_data(self.conn, date(2026, 10, 19))["summary"]}
        self.assertEqual(summary["B51"]["banker"], 1)
        self.assertEqual(summary["B20"]["banker"], 0)

    def test_local_day_boundary(self):
        self.add("B51", "at-start", "BANKER", "2026-10-18T17:00:00Z")
        self.add("B51", "next-day", "PLAYER", "2026-10-19T17:00:00Z")
        result = daily_data(self.conn, date(2026, 10, 19))
        self.assertEqual(result["summary"][0]["total"], 1)
        self.assertEqual(result["summary"][0]["banker"], 1)

    def test_outer_transaction_rolls_back_partial_import(self):
        with self.assertRaises(ValueError):
            with self.conn.transaction():
                self.add("B51", "valid", "BANKER")
                self.add("B51", "invalid", "UNKNOWN")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 0
        )

    def test_report_exports_postgresql_timestamps(self):
        self.add("B51", "R1", "BANKER")
        with tempfile.TemporaryDirectory() as temporary:
            path = export_daily(self.conn, date(2026, 10, 19), temporary)
            self.assertTrue(path.is_file())
            with ZipFile(path) as workbook:
                strings = workbook.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn("B51", strings)
            self.assertIn("BANKER", strings)

    def test_red_window_uses_prior_rounds_and_exports_count(self):
        for index in range(12):
            self.add("B51", f"prior-{index}", "BANKER", f"2026-10-18T23:{index:02d}:00Z")
        self.add("B51", "threshold", "BANKER", "2026-10-19T00:05:00Z")
        self.add("B51", "continued", "BANKER", "2026-10-19T00:06:00Z")
        self.add("B20", "one", "PLAYER", "2026-10-19T00:07:00Z")
        result = red_window_data(self.conn, date(2026, 10, 19), "BANKER", "UNIT_TEST")
        self.assertEqual(result["total_reached_13_events"], 1)
        self.assertEqual(result["events"][0]["thirteenth_round_id"], "threshold")
        self.assertEqual(result["coverage_status"], "UNKNOWN")
        with tempfile.TemporaryDirectory() as temporary:
            path = export_red_window(self.conn, date(2026, 10, 19), "BANKER", "UNIT_TEST", temporary)
            with ZipFile(path) as workbook:
                strings = workbook.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn("threshold", strings)
            self.assertIn("Coverage is UNKNOWN", strings)

    def test_streak_window_long_lookback_both_policies_and_export(self):
        # 12 Bankers, then 120 Ties before 07:00 local (00:00 UTC); 13th Banker inside the window.
        for index in range(12):
            self.add("B51", f"b-{index}", "BANKER", f"2026-10-18T20:{index:02d}:00Z")
        for index in range(120):
            self.add("B51", f"t-{index}", "TIE", f"2026-10-18T21:{index // 60:02d}:{index % 60:02d}Z")
        self.add("B51", "thirteenth", "BANKER", "2026-10-19T00:05:00Z")
        for index in range(13):
            self.add("B20", f"p-{index}", "PLAYER", f"2026-10-19T03:{index:02d}:00Z")
        data = streak_window_data(self.conn, date(2026, 10, 19), "UNIT_TEST")
        self.assertEqual(data["totals"]["reached_13_strict_v1"], {"BANKER": 0, "PLAYER": 1})
        self.assertEqual(data["totals"]["reached_13_tie_transparent_v1"], {"BANKER": 1, "PLAYER": 1})
        self.assertEqual(data["tables_observed"], 2)
        self.assertEqual(data["color_mapping"], {"BANKER": "UNVERIFIED", "PLAYER": "UNVERIFIED"})
        self.assertIn("total 2 events across 2 tables", data["headline"][2])
        self.assertTrue(data["headline"][0].startswith("Date 2026-10-19, window 07:00–21:00"))
        b51 = next(item for item in data["summary"] if item["table_id"] == "B51")
        self.assertEqual((b51["first_round_no"], b51["last_round_no"]), ("thirteenth", "thirteenth"))
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = export_streak_window(self.conn, date(2026, 10, 19), "UNIT_TEST", temporary,
                                           "00:00", "24:00", "BANKER")
            with ZipFile(path) as workbook:
                strings = workbook.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn("thirteenth", strings)
            self.assertIn("Banker (red)", strings)
            self.assertIn("2026-10-19 07:05:00", strings)  # local time of the 13th result
            self.assertIn("Tie skipped", strings)

    def test_monitor_dom_prints_report_when_interrupted(self):
        import contextlib, io, sys
        from datetime import datetime, timedelta, timezone
        from unittest import mock
        import agent.cli as cli
        now = datetime.now(timezone.utc)
        for index in range(13):
            stamp = (now - timedelta(seconds=13 - index)).isoformat()
            self.add("B51", f"exit-{index}", "BANKER", stamp)
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "source.yaml"
            config.write_text("source_id: UNIT_TEST\nreader: lobby_counters\nurl: http://127.0.0.1/\n"
                              "viewport: {width: 800, height: 600}\ntables: [{id: B51}]\n", encoding="utf-8")
            url = f"{self.conninfo} options='-csearch_path={self.schema}'".strip()

            def interrupted(coroutine):
                coroutine.close()
                raise KeyboardInterrupt

            argv = ["agent.cli", "monitor-dom", "--config", str(config), "--database-url", url,
                    "--report-on-exit", "--report-start", "00:00", "--report-end", "24:00",
                    "--report-dir", temporary]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(cli.asyncio, "run", interrupted),                     contextlib.redirect_stdout(output):
                cli.main()
            text = output.getvalue()
            self.assertIn("monitor_stopped reason=STOPPED_BY_OPERATOR", text)
            self.assertIn("(reached_13_strict_v1): Banker 1, Player 0", text)
            self.assertTrue(list(Path(temporary).glob("baccarat_streak13_*.xlsx")))

    def test_red_window_rejects_mixed_sources_for_same_table(self):
        self.add("B51", "one", "BANKER", "2026-10-19T00:00:00Z")
        insert_verified_round(self.conn, table_id="B51", round_id="other", result="BANKER",
                              finished_at_utc="2026-10-18T23:00:00Z",
                              method="MANUAL_VERIFIED", source="OTHER_SOURCE", reviewer="QA")
        with self.assertRaisesRegex(ValueError, "source namespace migration required"):
            red_window_data(self.conn, date(2026, 10, 19), "BANKER", "UNIT_TEST")

    def test_structured_source_pipeline_writes_evidence_and_deduplicates_replay(self):
        adapter = StructuredExportAdapter("DEMO_STRUCTURED", trusted_round_ids=True)
        coordinator = SourceCoordinator(self.conn, "DEMO_STRUCTURED", {"S01"})
        path = Path(__file__).resolve().parents[1] / "samples/structured_export_demo.jsonl"
        import json
        frames = [json.loads(line) for line in path.read_text().splitlines()]
        statuses = []
        for payload in frames:
            frame = CapturedFrame(payload["source_id"], payload["frame_id"],
                                  payload["captured_at_utc"], payload["evidence_ref"],
                                  payload=payload)
            statuses.append(coordinator.process_frame(frame, adapter)["S01"])
        self.assertEqual(statuses, ["OBSERVED", "OBSERVED", "OBSERVED", "INSERTED"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 1)
        evidence = self.conn.execute("SELECT * FROM source_round_evidence").fetchone()
        self.assertEqual(evidence["first_frame_id"], "demo-f3")
        self.assertEqual(evidence["second_frame_id"], "demo-f4")
        fresh = SourceCoordinator(self.conn, "DEMO_STRUCTURED", {"S01"})
        frame = CapturedFrame(frames[-1]["source_id"], frames[-1]["frame_id"],
                              frames[-1]["captured_at_utc"], frames[-1]["evidence_ref"],
                              payload=frames[-1])
        self.assertEqual(fresh.process_frame(frame, adapter)["S01"], "DUPLICATE_FRAME")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 1)

    def test_source_conflict_is_quarantined(self):
        base = dict(source_id="DEMO_STRUCTURED", table_id="S01", source_round_id="shoe:round-1",
                    observed_result_at_utc="2026-10-19T00:00:15Z",
                    evidence_frames=("f3", "f4"), evidence_refs=("demo://3", "demo://4"))
        self.assertEqual(save_candidate(self.conn, ConfirmedCandidate(result="BANKER", **base)), "INSERTED")
        self.assertEqual(save_candidate(self.conn, ConfirmedCandidate(result="PLAYER", **base)), "CONFLICT")
        self.assertEqual(self.conn.execute("SELECT result FROM confirmed_rounds").fetchone()["result"], "BANKER")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM source_conflicts").fetchone()["n"], 1)

    def test_untrusted_export_and_missing_table_do_not_confirm(self):
        adapter = StructuredExportAdapter("DEMO_STRUCTURED")
        coordinator = SourceCoordinator(self.conn, "DEMO_STRUCTURED", {"S01"})
        payload = {"tables": [{"table_id": "S01", "shoe_id": "shoe-1",
                               "round_id": "round-1", "phase": "RESULT",
                               "final_result": "BANKER", "roadmap_revision": "rev-b"}]}
        frame = CapturedFrame("DEMO_STRUCTURED", "f1", "2026-10-19T00:00:00Z", "demo://1", payload=payload)
        self.assertEqual(coordinator.process_frame(frame, adapter)["S01"], "OBSERVED")
        missing = CapturedFrame("DEMO_STRUCTURED", "f2", "2026-10-19T00:00:05Z", "demo://2",
                                payload={"tables": []})
        self.assertEqual(coordinator.process_frame(missing, adapter)["S01"], "GAP")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM source_gaps").fetchone()["n"], 1)
        # A continuing absence adds no gap rows; a new absence after reappearing does.
        for index, tables in ((3, []), (4, []), (5, payload["tables"]), (6, [])):
            coordinator.process_frame(CapturedFrame("DEMO_STRUCTURED", f"f{index}", f"2026-10-19T00:00:{index * 5:02d}Z",
                                                    f"demo://{index}", payload={"tables": tables}), adapter)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM source_gaps").fetchone()["n"], 2)

    def test_auto_tables_grow_and_gap_once_per_absence(self):
        adapter = StructuredExportAdapter("DEMO_STRUCTURED")
        coordinator = SourceCoordinator(self.conn, "DEMO_STRUCTURED", set(), auto_tables=True)

        def state(table):
            return {"table_id": table, "shoe_id": "s", "round_id": "1", "phase": "BETTING",
                    "final_result": None, "roadmap_revision": "r"}

        frames = [["B06"], ["B06", "A36"], ["A36"], ["A36"], ["A36", "B06"]]
        results = []
        for index, tables in enumerate(frames):
            frame = CapturedFrame("DEMO_STRUCTURED", f"a{index}", f"2026-10-19T00:00:{index * 5:02d}Z",
                                  f"demo://{index}", payload={"tables": [state(t) for t in tables]})
            results.append(coordinator.process_frame(frame, adapter))
        self.assertEqual(results[0], {"B06": "OBSERVED"})
        self.assertEqual(results[2], {"A36": "OBSERVED", "B06": "GAP"})
        self.assertEqual(coordinator.expected_tables, {"B06", "A36"})
        gaps = self.conn.execute("SELECT table_id, reason FROM source_gaps").fetchall()
        self.assertEqual([(g["table_id"], g["reason"]) for g in gaps], [("B06", "TABLE_MISSING")])
        with self.assertRaises(ValueError):
            SourceCoordinator(self.conn, "DEMO_STRUCTURED", set())

    def test_restart_requires_new_phase_cycle(self):
        adapter = StructuredExportAdapter("DEMO_STRUCTURED", trusted_round_ids=True)
        path = Path(__file__).resolve().parents[1] / "samples/structured_export_demo.jsonl"
        import json
        frames = [json.loads(line) for line in path.read_text().splitlines()]
        first_worker = SourceCoordinator(self.conn, "DEMO_STRUCTURED", {"S01"})
        for payload in frames[:2]:
            first_worker.process_frame(CapturedFrame(payload["source_id"], payload["frame_id"],
                                                     payload["captured_at_utc"], payload["evidence_ref"],
                                                     payload=payload), adapter)
        restarted = SourceCoordinator(self.conn, "DEMO_STRUCTURED", {"S01"})
        for payload in frames[2:]:
            result = restarted.process_frame(CapturedFrame(payload["source_id"], payload["frame_id"],
                                                            payload["captured_at_utc"], payload["evidence_ref"],
                                                            payload=payload), adapter)
            self.assertEqual(result["S01"], "OBSERVED")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 0)
        self.assertEqual(self.conn.execute("""SELECT COUNT(*) AS n FROM source_gaps
            WHERE reason = 'WORKER_RESTART'""").fetchone()["n"], 1)

    def test_legacy_sqlite_migration_is_atomic_and_one_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.sqlite3"
            with sqlite3.connect(path) as legacy:
                legacy.executescript("""
                    CREATE TABLE observations (id INTEGER PRIMARY KEY, table_id TEXT,
                        observed_at_utc TEXT, red_markers INTEGER, blue_markers INTEGER,
                        status TEXT, evidence_path TEXT);
                    CREATE TABLE confirmed_rounds (id INTEGER PRIMARY KEY, table_id TEXT,
                        round_id TEXT, finished_at_utc TEXT, result TEXT, method TEXT,
                        source TEXT, reviewer TEXT, recorded_at_utc TEXT);
                    CREATE TABLE observation_gaps (id INTEGER PRIMARY KEY, table_id TEXT,
                        detected_at_utc TEXT, reason TEXT);
                    INSERT INTO observations VALUES
                        (1,'B51','2026-10-19T06:00:00+00:00',1,0,'OBSERVED_NOT_CONFIRMED','frame.png');
                    INSERT INTO confirmed_rounds VALUES
                        (1,'B51','R1','2026-10-19T06:01:00+00:00','BANKER',
                         'MANUAL_VERIFIED','UNIT_TEST','QA','2026-10-19T06:02:00+00:00');
                    INSERT INTO observation_gaps VALUES
                        (1,'B51','2026-10-19T06:03:00+00:00','network_loss');
                """)
            self.assertEqual(
                migrate(path, self.conninfo, schema=self.schema),
                {"observations": 1, "confirmed_rounds": 1, "observation_gaps": 1},
            )
            with self.assertRaises(ValueError):
                migrate(path, self.conninfo, schema=self.schema)
            self.assertEqual(daily_data(self.conn, date(2026, 10, 19))["summary"][0]["total"], 1)


if __name__ == "__main__":
    unittest.main()
