"""Conservative FSM for already extracted, source-reviewed round evidence.

Input must already be VERIFIED UI evidence, not raw colored-circle counts.
A site-specific adapter or approved structured export must provide trustworthy
round IDs, phase labels, final outcomes and a roadmap revision identifier.
"""
from dataclasses import dataclass

PHASES = {"BETTING", "DEALING", "RESULT"}
RESULTS = {"BANKER", "PLAYER", "TIE"}

@dataclass(frozen=True)
class TableEvidence:
    table_id: str
    frame_id: str
    phase: str
    source_round_id: str | None
    final_result: str | None
    roadmap_revision: str | None
    round_id_trusted: bool = False

@dataclass(frozen=True)
class VerifiedResult:
    table_id: str
    source_round_id: str
    result: str
    evidence_frames: tuple[str, str]


class ConservativeRoundValidator:
    """One instance PER table. Requires betting -> dealing -> result twice,
    trusted ID, new roadmap revision and two independent frame IDs.

    Its existence is not evidence that a particular live site exposes these
    signals or that a configured reader extracts them accurately.
    """
    def __init__(self, table_id: str):
        self.table_id = table_id
        self.state = "UNKNOWN"
        self.base_revision: str | None = None
        self.active_round: str | None = None
        self.first_candidate: TableEvidence | None = None
        self.emitted_ids: set[str] = set()

    def gap(self):
        self.state = "UNKNOWN"
        self.base_revision = None
        self.active_round = None
        self.first_candidate = None

    def accept(self, evidence: TableEvidence) -> VerifiedResult | None:
        if evidence.table_id != self.table_id:
            self.gap()  # mismatch breaks continuity
            return None
        if evidence.phase not in PHASES:
            self.gap()
            return None
        if evidence.phase == "BETTING":
            self.active_round = evidence.source_round_id if evidence.round_id_trusted else None
            self.base_revision = evidence.roadmap_revision
            self.first_candidate = None
            self.state = "BETTING" if self.active_round and self.base_revision else "UNKNOWN"
            return None
        if evidence.phase == "DEALING":
            if (self.state == "BETTING" and evidence.round_id_trusted
                    and evidence.source_round_id == self.active_round):
                self.state = "DEALING"
            else:
                self.gap()
            return None
        if self.state not in ("DEALING", "RESULT_PENDING"):
            return None
        if (not evidence.round_id_trusted or not evidence.source_round_id
                or evidence.source_round_id != self.active_round
                or evidence.final_result not in RESULTS
                or not evidence.roadmap_revision
                or evidence.roadmap_revision == self.base_revision):
            self.first_candidate = None
            return None
        if self.state == "DEALING":
            self.first_candidate = evidence
            self.state = "RESULT_PENDING"
            return None
        first = self.first_candidate
        if (first and first.frame_id != evidence.frame_id
                and first.source_round_id == evidence.source_round_id
                and first.final_result == evidence.final_result
                and first.roadmap_revision == evidence.roadmap_revision):
            self.state = "DONE"
            if evidence.source_round_id in self.emitted_ids:
                return None
            self.emitted_ids.add(evidence.source_round_id)
            return VerifiedResult(self.table_id, evidence.source_round_id,
                                  evidence.final_result, (first.frame_id, evidence.frame_id))
        # If changed between frames, new candidate must also pass 2 stable frames.
        self.first_candidate = evidence
        return None
