"""Candidate pipeline between source extraction and the durable coordinator.

This module intentionally does not write confirmed_rounds. The coordinator
provides persistence; source semantics still require independent validation.
"""
from dataclasses import dataclass

from .round_validator import ConservativeRoundValidator
from .site_adapter import ExtractedEvidence, utc_stamp


@dataclass(frozen=True)
class ConfirmedCandidate:
    source_id: str
    table_id: str
    source_round_id: str
    result: str
    observed_result_at_utc: str
    evidence_frames: tuple[str, str]
    evidence_refs: tuple[str, str]
    time_policy: str = "SECOND_RESULT_FRAME_OBSERVED_AT"


class CandidatePipeline:
    """Fail-closed, in-memory validation for one approved source at a time.

    Caller must explicitly pass the source ID that was reviewed. A candidate is
    not a persisted/fully audited round until the coordinator writes it.
    """

    def __init__(self, approved_source_id: str):
        if not approved_source_id:
            raise ValueError("approved_source_id is required")
        self.approved_source_id = approved_source_id
        self._validators: dict[str, ConservativeRoundValidator] = {}
        self._previous_result_ref: dict[str, tuple[str, str]] = {}

    def gap(self, table_id: str) -> None:
        if table_id in self._validators:
            self._validators[table_id].gap()
        self._previous_result_ref.pop(table_id, None)

    def accept(self, record: ExtractedEvidence) -> ConfirmedCandidate | None:
        record.validate()
        if record.source_id != self.approved_source_id:
            raise ValueError("evidence source does not match approved source")
        evidence = record.evidence
        table_id = evidence.table_id
        validator = self._validators.setdefault(table_id, ConservativeRoundValidator(table_id))
        if evidence.phase not in ("BETTING", "DEALING", "RESULT"):
            self.gap(table_id)
            return None
        if evidence.phase != "RESULT":
            self._previous_result_ref.pop(table_id, None)
        prior = self._previous_result_ref.get(table_id)
        verified = validator.accept(evidence)
        if evidence.phase == "RESULT":
            self._previous_result_ref[table_id] = (evidence.frame_id, record.evidence_ref)
        if verified is None:
            return None
        if prior is None or prior[0] != verified.evidence_frames[0]:
            # Do not release a candidate whose first frame cannot be traced.
            self.gap(table_id)
            return None
        return ConfirmedCandidate(
            source_id=record.source_id,
            table_id=verified.table_id,
            source_round_id=verified.source_round_id,
            result=verified.result,
            observed_result_at_utc=utc_stamp(record.captured_at_utc),
            evidence_frames=verified.evidence_frames,
            evidence_refs=(prior[1], record.evidence_ref),
        )
