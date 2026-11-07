"""Adapter for authorized structured round-state exports and labeled replays.

This does not parse a website image. Its trust flag must be enabled only after
the export's identity and result semantics have been independently checked.
"""
from ..round_validator import TableEvidence
from ..site_adapter import CapturedFrame, ExtractedEvidence


class StructuredExportAdapter:
    def __init__(self, source_id: str, *, trusted_round_ids: bool = False,
                 ids_reset_per_shoe: bool = True):
        if not source_id:
            raise ValueError("source_id is required")
        self.source_id = source_id
        self.trusted_round_ids = trusted_round_ids
        self.ids_reset_per_shoe = ids_reset_per_shoe

    def extract(self, frame: CapturedFrame) -> list[ExtractedEvidence]:
        frame.validate()
        if (frame.source_id != self.source_id or frame.payload is None
                or frame.payload.get("source_id", self.source_id) != self.source_id):
            raise ValueError("structured payload source does not match adapter")
        entries = frame.payload.get("tables")
        if not isinstance(entries, list):
            raise ValueError("structured payload must contain a tables list")
        output = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each table state must be an object")
            table_id = str(entry.get("table_id", "")).strip()
            raw_id = str(entry.get("round_id", "")).strip()
            shoe_id = str(entry.get("shoe_id", "")).strip()
            if not table_id:
                raise ValueError("table_id is required")
            if self.ids_reset_per_shoe and raw_id and not shoe_id:
                raise ValueError("shoe_id is required when source IDs reset per shoe")
            round_id = f"{len(shoe_id)}:{shoe_id}:{raw_id}" if raw_id and shoe_id else raw_id or None
            result = entry.get("final_result")
            revision = entry.get("roadmap_revision")
            phase = str(entry.get("phase", "UNKNOWN")).upper()
            evidence = TableEvidence(
                table_id=table_id, frame_id=frame.frame_id, phase=phase,
                source_round_id=round_id,
                final_result=str(result).upper() if result is not None else None,
                roadmap_revision=str(revision) if revision is not None else None,
                round_id_trusted=bool(self.trusted_round_ids and raw_id),
            )
            output.append(ExtractedEvidence(
                source_id=self.source_id, captured_at_utc=frame.captured_at_utc,
                evidence_ref=str(entry.get("evidence_ref") or f"{frame.evidence_ref}#{table_id}"),
                evidence=evidence))
        return output
