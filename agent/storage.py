"""PostgreSQL storage for observations, reviewed rounds, and gaps.

The structured source coordinator uses the verified-round write path. Raw marker
observations never become confirmed rounds through this module.
"""
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import os
import re

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SCHEMA_LOCK = 20261022


def parse_utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return moment.astimezone(timezone.utc)


def ensure_schema(conn: psycopg.Connection) -> None:
    """Apply pending numbered migrations and detect edits to applied files."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
        installed = {row["version"]: row["checksum"] for row in conn.execute(
            "SELECT version, checksum FROM schema_migrations"
        )}
        files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        versions = {int(path.name[:3]) for path in files}
        if not files or len(versions) != len(files) or set(installed) - versions:
            raise RuntimeError("PostgreSQL migration files are missing or duplicated")
        for path in files:
            version = int(path.name[:3])
            source = path.read_bytes()
            checksum = sha256(source).hexdigest()
            if version in installed:
                if installed[version] != checksum:
                    raise RuntimeError(f"Applied migration {version} was modified: {path.name}")
                continue
            for statement in (part.strip() for part in source.decode("utf-8").split(";")):
                if statement:
                    conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                         (version, checksum))


def connect(database_url: str | None = None, *, schema: str | None = None) -> psycopg.Connection:
    """Connect using a URL or libpq PG* environment variables and ensure schema.

    schema is reserved for isolated integration tests. Production uses public.
    """
    conninfo = database_url if database_url is not None else os.getenv("DATABASE_URL", "")
    conn = psycopg.connect(conninfo, autocommit=True, row_factory=dict_row, connect_timeout=10)
    try:
        if schema is not None:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
                raise ValueError("invalid PostgreSQL schema name")
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        ensure_schema(conn)
        return conn
    except Exception:
        conn.close()
        raise


def record_observations(conn: psycopg.Connection, readings: list[dict], evidence_path: str = "") -> None:
    if not readings:
        return
    timestamp = datetime.now(timezone.utc)
    values = [(r["table_id"], timestamp, r["red_markers"], r["blue_markers"],
               "OBSERVED_NOT_CONFIRMED", evidence_path) for r in readings]
    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.executemany("""INSERT INTO observations
                (table_id, observed_at_utc, red_markers, blue_markers, status, evidence_path)
                VALUES (%s, %s, %s, %s, %s, %s)""", values)


def insert_verified_round(conn: psycopg.Connection, *, table_id: str, round_id: str,
                          finished_at_utc: str, result: str, method: str,
                          source: str, reviewer: str) -> bool:
    """Return False for an exact duplicate; raise on a conflicting round key.

    INSERT ... ON CONFLICT handles concurrent writers without a read-before-write race.
    """
    if not all((table_id, round_id, finished_at_utc, source, reviewer)):
        raise ValueError("table_id, round_id, time, source, reviewer are mandatory")
    if result not in ("BANKER", "PLAYER", "TIE"):
        raise ValueError(f"Bad result: {result}")
    if method not in ("MANUAL_VERIFIED", "TRUSTED_ROUND_ID"):
        raise ValueError(f"Bad verification method: {method}")
    finished = parse_utc(finished_at_utc)
    with conn.transaction():
        created = conn.execute("""INSERT INTO confirmed_rounds
            (table_id, round_id, finished_at_utc, result, method, source, reviewer, recorded_at_utc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_id, round_id) DO NOTHING RETURNING id""",
            (table_id, round_id, finished, result, method, source, reviewer,
             datetime.now(timezone.utc))).fetchone()
        if created:
            return True
        old = conn.execute("""SELECT finished_at_utc, result, method, source, reviewer
            FROM confirmed_rounds WHERE table_id = %s AND round_id = %s""",
            (table_id, round_id)).fetchone()
        if old is None:
            raise RuntimeError("round conflict was reported but the existing row is missing")
        previous = (old["finished_at_utc"].astimezone(timezone.utc), old["result"],
                    old["method"], old["source"], old["reviewer"])
        incoming = (finished, result, method, source, reviewer)
        if previous != incoming:
            raise ValueError(f"CONFLICT for {table_id}/{round_id}; check original evidence")
        return False


def mark_gap(conn: psycopg.Connection, table_id: str, detected_at_utc: str, reason: str) -> None:
    if not table_id or not reason:
        raise ValueError("table_id and reason are mandatory")
    timestamp = parse_utc(detected_at_utc)
    with conn.transaction():
        conn.execute("""INSERT INTO observation_gaps (table_id, detected_at_utc, reason)
            VALUES (%s, %s, %s)""", (table_id, timestamp, reason))
