"""One-time, atomic import from a legacy SQLite file to an empty PostgreSQL store."""
import argparse
import sqlite3
from pathlib import Path

from agent.storage import connect, parse_utc

TABLES = ("observations", "confirmed_rounds", "observation_gaps")
BATCH_SIZE = 1000


def copy_rows(source, destination, select_sql, insert_sql, transform):
    reader = source.execute(select_sql)
    total = 0
    with destination.cursor() as cursor:
        while True:
            batch = reader.fetchmany(BATCH_SIZE)
            if not batch:
                break
            cursor.executemany(insert_sql, [transform(row) for row in batch])
            total += len(batch)
    return total


def migrate(sqlite_path: Path, database_url: str | None = None,
            *, schema: str | None = None) -> dict[str, int]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Legacy SQLite database not found: {sqlite_path}")
    uri = sqlite_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as old:
        snapshot = sqlite3.connect(":memory:")
        try:
            old.backup(snapshot)
            snapshot.row_factory = sqlite3.Row
            with connect(database_url, schema=schema) as new:
                with new.transaction():
                    new.execute("LOCK TABLE observations, confirmed_rounds, observation_gaps IN ACCESS EXCLUSIVE MODE")
                    existing = {name: new.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
                                for name in TABLES}
                    if any(existing.values()):
                        raise ValueError(
                            "PostgreSQL target is not empty; use a fresh database for one-time migration"
                        )
                    counts = {}
                    counts["observations"] = copy_rows(
                        snapshot, new,
                        """SELECT table_id, observed_at_utc, red_markers, blue_markers, status,
                                  evidence_path FROM observations ORDER BY id""",
                        """INSERT INTO observations
                           (table_id, observed_at_utc, red_markers, blue_markers, status, evidence_path)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        lambda r: (r["table_id"], parse_utc(r["observed_at_utc"]),
                                   r["red_markers"], r["blue_markers"], r["status"], r["evidence_path"]),
                    )
                    counts["confirmed_rounds"] = copy_rows(
                        snapshot, new,
                        """SELECT table_id, round_id, finished_at_utc, result, method, source,
                                  reviewer, recorded_at_utc FROM confirmed_rounds ORDER BY id""",
                        """INSERT INTO confirmed_rounds
                           (table_id, round_id, finished_at_utc, result, method, source,
                            reviewer, recorded_at_utc)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        lambda r: (r["table_id"], r["round_id"], parse_utc(r["finished_at_utc"]),
                                   r["result"], r["method"], r["source"], r["reviewer"],
                                   parse_utc(r["recorded_at_utc"])),
                    )
                    counts["observation_gaps"] = copy_rows(
                        snapshot, new,
                        """SELECT table_id, detected_at_utc, reason
                           FROM observation_gaps ORDER BY id""",
                        """INSERT INTO observation_gaps
                           (table_id, detected_at_utc, reason) VALUES (%s, %s, %s)""",
                        lambda r: (r["table_id"], parse_utc(r["detected_at_utc"]), r["reason"]),
                    )
                    for name, expected in counts.items():
                        actual = new.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
                        if actual != expected:
                            raise RuntimeError(f"{name}: expected {expected}, found {actual}")
                    return counts
        finally:
            snapshot.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL or PG* environment")
    args = parser.parse_args()
    print(f"Legacy migration complete: {migrate(args.sqlite, args.database_url)}")
