"""Durable, source-scoped writes for validated round candidates and gaps."""
from hashlib import sha256
import json

from psycopg.types.json import Jsonb

from .pipeline import ConfirmedCandidate
from .storage import insert_verified_round, mark_gap, parse_utc


def stored_round_key(source_id: str, source_round_id: str) -> str:
    """Keep the legacy table/round unique key distinct across sources."""
    if not source_id or not source_round_id:
        raise ValueError("source and round identity are required")
    return f"{len(source_id)}:{source_id}:{source_round_id}"


def record_source_gap(conn, source_id: str, table_id: str, event_key: str,
                      detected_at_utc: str, reason: str) -> bool:
    if not all((source_id, table_id, event_key, reason)):
        raise ValueError("source, table, event key, and reason are required")
    stamp = parse_utc(detected_at_utc)
    with conn.transaction():
        created = conn.execute("""INSERT INTO source_gaps
            (source_id, table_id, event_key, detected_at_utc, reason)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING RETURNING event_key""",
            (source_id, table_id, event_key, stamp, reason)).fetchone()
        if created:
            mark_gap(conn, table_id, detected_at_utc, f"{source_id}:{reason}")
        return bool(created)


def save_candidate(conn, candidate: ConfirmedCandidate) -> str:
    """Return INSERTED, DUPLICATE, or CONFLICT; preserve conflicting evidence."""
    key = stored_round_key(candidate.source_id, candidate.source_round_id)
    incoming = {
        "result": candidate.result,
        "finished_at_utc": parse_utc(candidate.observed_result_at_utc).isoformat(),
        "evidence_frames": list(candidate.evidence_frames),
        "evidence_refs": list(candidate.evidence_refs),
        "time_policy": candidate.time_policy,
    }
    if (len(candidate.evidence_frames) != 2 or len(candidate.evidence_refs) != 2
            or not all(candidate.evidence_frames) or not all(candidate.evidence_refs)
            or candidate.evidence_frames[0] == candidate.evidence_frames[1]
            or candidate.evidence_refs[0] == candidate.evidence_refs[1]):
        raise ValueError("two distinct evidence frames and references are required")
    with conn.transaction():
        try:
            created = insert_verified_round(
                conn, table_id=candidate.table_id, round_id=key,
                finished_at_utc=candidate.observed_result_at_utc, result=candidate.result,
                method="TRUSTED_ROUND_ID", source=candidate.source_id, reviewer="AUTO_VALIDATED")
        except ValueError:
            old = conn.execute("""SELECT result, finished_at_utc, source FROM confirmed_rounds
                WHERE table_id = %s AND round_id = %s""", (candidate.table_id, key)).fetchone()
            if old is None:
                raise
            existing = {"result": old["result"],
                        "finished_at_utc": old["finished_at_utc"].isoformat(),
                        "source": old["source"]}
            payload = json.dumps(incoming, sort_keys=True)
            event_key = sha256((candidate.source_id + "\0" + candidate.table_id + "\0"
                                + candidate.source_round_id + "\0" + payload).encode()).hexdigest()
            conn.execute("""INSERT INTO source_conflicts
                (event_key, source_id, table_id, source_round_id, existing_payload, incoming_payload)
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (event_key, candidate.source_id, candidate.table_id,
                 candidate.source_round_id, Jsonb(existing), Jsonb(incoming)))
            return "CONFLICT"
        conn.execute("""INSERT INTO source_round_evidence
            (source_id, table_id, source_round_id, stored_round_id,
             first_frame_id, second_frame_id, first_evidence_ref,
             second_evidence_ref, time_policy)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING""",
            (candidate.source_id, candidate.table_id, candidate.source_round_id, key,
             *candidate.evidence_frames, *candidate.evidence_refs, candidate.time_policy))
        return "INSERTED" if created else "DUPLICATE"
