"""Extraction contract for structured exports and configured DOM readers.

The shipped DOM selector template is not validated for a named website. Round
IDs must pass source-specific review before the trust gate is enabled.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .round_validator import TableEvidence


def utc_stamp(value: str) -> str:
    """Normalize an ISO-8601 timestamp with a mandatory UTC offset."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return moment.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class CapturedFrame:
    source_id: str
    frame_id: str
    captured_at_utc: str
    evidence_ref: str
    image: bytes = b""
    payload: dict | None = None

    def validate(self) -> None:
        if not all((self.source_id, self.frame_id, self.evidence_ref)) or not (self.image or self.payload is not None):
            raise ValueError("source_id, frame_id, evidence_ref and image or payload are required")
        utc_stamp(self.captured_at_utc)


@dataclass(frozen=True)
class ExtractedEvidence:
    source_id: str
    captured_at_utc: str
    evidence_ref: str
    evidence: TableEvidence

    def validate(self) -> None:
        if not self.source_id or not self.evidence_ref:
            raise ValueError("source_id and evidence_ref are required")
        if not self.evidence.frame_id or not self.evidence.table_id:
            raise ValueError("table_id and frame_id are required")
        utc_stamp(self.captured_at_utc)


class SiteAdapter(Protocol):
    """Implement per approved source/layout; unknown fields stay untrusted."""

    source_id: str

    def extract(self, frame: CapturedFrame) -> list[ExtractedEvidence]:
        """Return one evidence record per visible table, or none when unreadable."""
        ...
