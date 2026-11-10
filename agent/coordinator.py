"""Fail-closed coordinator between an approved adapter and durable storage."""
from uuid import uuid4

from .live_store import record_source_gap, save_candidate
from .pipeline import CandidatePipeline
from .site_adapter import CapturedFrame, ExtractedEvidence, SiteAdapter
from .storage import parse_utc


class SourceCoordinator:
    def __init__(self, conn, source_id: str, expected_tables: set[str],
                 max_frame_gap_seconds: float = 30, auto_tables: bool = False):
        if not source_id or not (expected_tables or auto_tables) or max_frame_gap_seconds <= 0:
            raise ValueError("source, expected tables (or auto_tables), and positive gap limit are required")
        self.auto_tables = auto_tables
        self.conn = conn
        self.source_id = source_id
        self.expected_tables = set(expected_tables)
        self.max_frame_gap_seconds = max_frame_gap_seconds
        self.pipeline = CandidatePipeline(source_id)
        self.run_id = uuid4().hex
        self.seen_in_run: set[str] = set()
        self.missing_tables: set[str] = set()

    def gap(self, table_id: str, frame_id: str, at_utc: str, reason: str) -> bool:
        if table_id not in self.expected_tables:
            raise ValueError("unexpected table")
        self.pipeline.gap(table_id)
        return record_source_gap(self.conn, self.source_id, table_id,
                                 f"{reason}:{frame_id}", at_utc, reason)

    def process(self, record: ExtractedEvidence) -> str:
        record.validate()
        if record.source_id != self.source_id or record.evidence.table_id not in self.expected_tables:
            raise ValueError("evidence source or table is not approved for this coordinator")
        table_id = record.evidence.table_id
        frame_id = record.evidence.frame_id
        captured = parse_utc(record.captured_at_utc)
        try:
            with self.conn.transaction():
                old_frame = self.conn.execute("""SELECT 1 FROM processed_source_frames
                    WHERE source_id = %s AND table_id = %s AND frame_id = %s""",
                    (self.source_id, table_id, frame_id)).fetchone()
                if old_frame:
                    return "DUPLICATE_FRAME"
                checkpoint = self.conn.execute("""SELECT last_frame_id, last_captured_at_utc
                    FROM worker_checkpoints WHERE source_id = %s AND table_id = %s""",
                    (self.source_id, table_id)).fetchone()
                if checkpoint and table_id not in self.seen_in_run:
                    self.gap(table_id, self.run_id, record.captured_at_utc, "WORKER_RESTART")
                self.seen_in_run.add(table_id)
                if checkpoint:
                    previous = checkpoint["last_captured_at_utc"]
                    if captured <= previous:
                        self.gap(table_id, frame_id, record.captured_at_utc, "STALE_OR_REORDERED")
                        return "STALE"
                    if (captured - previous).total_seconds() > self.max_frame_gap_seconds:
                        self.gap(table_id, frame_id, record.captured_at_utc, "CAPTURE_GAP")
                self.conn.execute("""INSERT INTO processed_source_frames
                    (source_id, table_id, frame_id, captured_at_utc)
                    VALUES (%s, %s, %s, %s)""",
                    (self.source_id, table_id, frame_id, captured))
                self.conn.execute("""INSERT INTO worker_checkpoints
                    (source_id, table_id, last_frame_id, last_captured_at_utc)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source_id, table_id) DO UPDATE SET
                    last_frame_id = EXCLUDED.last_frame_id,
                    last_captured_at_utc = EXCLUDED.last_captured_at_utc,
                    updated_at_utc = now()""",
                    (self.source_id, table_id, frame_id, captured))
                if record.evidence.phase not in ("BETTING", "DEALING", "RESULT"):
                    self.gap(table_id, frame_id, record.captured_at_utc, "UNKNOWN_PHASE")
                    return "UNKNOWN"
                candidate = self.pipeline.accept(record)
                return save_candidate(self.conn, candidate) if candidate else "OBSERVED"
        except Exception:
            self.pipeline.gap(table_id)
            self.seen_in_run.discard(table_id)
            raise

    def process_frame(self, frame: CapturedFrame, adapter: SiteAdapter) -> dict[str, str]:
        frame.validate()
        if frame.source_id != self.source_id or adapter.source_id != self.source_id:
            raise ValueError("frame or adapter source does not match coordinator")
        try:
            records = adapter.extract(frame)
        except Exception:
            for table_id in self.expected_tables:
                self.gap(table_id, frame.frame_id, frame.captured_at_utc, "ADAPTER_ERROR")
            raise
        by_table = {}
        if self.auto_tables:
            # Tables discovered in this frame join the observed set before validation.
            self.expected_tables.update(record.evidence.table_id for record in records
                                        if record.evidence.table_id)
        for record in records:
            table_id = record.evidence.table_id
            if (table_id in by_table or table_id not in self.expected_tables
                    or record.source_id != frame.source_id
                    or record.evidence.frame_id != frame.frame_id
                    or parse_utc(record.captured_at_utc) != parse_utc(frame.captured_at_utc)):
                for expected in self.expected_tables:
                    self.gap(expected, frame.frame_id, frame.captured_at_utc, "BAD_ADAPTER_MAPPING")
                raise ValueError("adapter returned duplicate, unexpected, or mismatched evidence")
            by_table[table_id] = record
        result = {}
        for table_id in self.expected_tables:
            if table_id not in by_table:
                if table_id in self.missing_tables:
                    # One gap per continuous absence; keep the validator reset.
                    self.pipeline.gap(table_id)
                else:
                    self.gap(table_id, frame.frame_id, frame.captured_at_utc, "TABLE_MISSING")
                    self.missing_tables.add(table_id)
                result[table_id] = "GAP"
            else:
                self.missing_tables.discard(table_id)
                result[table_id] = self.process(by_table[table_id])
        return result
