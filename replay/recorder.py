"""
recorder.py — SHAKTI Append-Only Telemetry Recorder

Writes normalized telemetry records to a SQLite store.
Records are NEVER updated or deleted.
Sequence numbers are monotonically incrementing, derived from the store.
Writes are atomic via SQLite transactions.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

# Default store path — can be overridden for testing
DEFAULT_STORE_PATH = Path(__file__).parent.parent / "data" / "replay_store.db"


class Recorder:
    """
    Append-only recorder backed by SQLite.

    Args:
        store_path: Path to the SQLite database file. Created if not exists.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = Path(store_path) if store_path else DEFAULT_STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.store_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the records table if it does not exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_records (
                    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id        TEXT NOT NULL,
                    source_type     TEXT NOT NULL,
                    device_id       TEXT NOT NULL,
                    region          TEXT NOT NULL,
                    payload_json    TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    rejection_reason  TEXT,
                    ingestion_timestamp TEXT NOT NULL,
                    record_hash     TEXT NOT NULL
                )
            """)
            conn.commit()

    def _compute_record_hash(self, telemetry: dict) -> str:
        """Compute a stable hash over the full telemetry record for divergence detection."""
        import hashlib
        canonical = json.dumps(telemetry, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record(self, telemetry: dict) -> str:
        """
        Append a normalized telemetry record to the store.

        Args:
            telemetry: Normalized telemetry dict (output of ingest modules).

        Returns:
            The trace_id of the written record.

        Notes:
            - Atomic: uses SQLite transaction.
            - If the same trace_id exists, the record is still written
              (idempotency is tracked by the replay engine, not the recorder).
        """
        trace_id = telemetry["trace_id"]
        record_hash = self._compute_record_hash(telemetry)

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO telemetry_records
                    (trace_id, source_type, device_id, region,
                     payload_json, validation_status, rejection_reason,
                     ingestion_timestamp, record_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                telemetry.get("source_type", ""),
                telemetry.get("device_id", ""),
                telemetry.get("region", ""),
                json.dumps(telemetry.get("payload", {}), sort_keys=True),
                telemetry.get("validation_status", ""),
                telemetry.get("rejection_reason"),
                telemetry.get("ingestion_timestamp", ""),
                record_hash,
            ))
            conn.commit()

        return trace_id

    def get_all(self) -> list[dict]:
        """Return all records in sequence order."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM telemetry_records ORDER BY sequence_number ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_range(self, from_sequence: int, to_sequence: Optional[int] = None) -> list[dict]:
        """Return records in [from_sequence, to_sequence] inclusive, ordered by sequence."""
        if to_sequence is None:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM telemetry_records WHERE sequence_number >= ? ORDER BY sequence_number ASC",
                    (from_sequence,)
                ).fetchall()
        else:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """SELECT * FROM telemetry_records
                       WHERE sequence_number >= ? AND sequence_number <= ?
                       ORDER BY sequence_number ASC""",
                    (from_sequence, to_sequence)
                ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        """Return total number of records in the store."""
        with self._get_conn() as conn:
            result = conn.execute("SELECT COUNT(*) FROM telemetry_records").fetchone()
        return result[0]

    def trace_id_exists(self, trace_id: str) -> bool:
        """Check if a trace_id has already been recorded (for idempotency checks)."""
        with self._get_conn() as conn:
            result = conn.execute(
                "SELECT 1 FROM telemetry_records WHERE trace_id = ? LIMIT 1",
                (trace_id,)
            ).fetchone()
        return result is not None

    def corrupt_record_for_testing(self, sequence_number: int, new_payload_json: str) -> None:
        """
        TEST-ONLY method: directly mutate a stored record's payload_json
        to simulate silent data corruption for divergence detection tests.
        """
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE telemetry_records SET payload_json = ? WHERE sequence_number = ?",
                (new_payload_json, sequence_number)
            )
            conn.commit()
