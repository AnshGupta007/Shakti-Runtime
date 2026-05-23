"""
replay_engine.py — SHAKTI Replay Continuity Engine

Reads recorded telemetry in sequence order and re-delivers it,
detecting divergences where stored trace_id doesn't match recomputed trace_id.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from replay.recorder import Recorder


@dataclass
class ReplayResult:
    total_replayed: int
    duration_ms: int
    divergences: list
    replay_id: str


def _compute_replay_id(from_sequence: int, to_sequence: Optional[int], speed: float) -> str:
    """Derive a deterministic replay_id from replay parameters."""
    content = f"{from_sequence}:{to_sequence}:{speed}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()



def _verify_record_integrity(stored_record: dict) -> bool:
    """
    Re-compute the record_hash from stored fields and compare with stored hash.
    Returns True if the record is intact, False if it has been mutated.
    """
    # Reconstruct the original telemetry dict from stored fields
    reconstructed = {
        "trace_id": stored_record["trace_id"],
        "source_type": stored_record["source_type"],
        "device_id": stored_record["device_id"],
        "region": stored_record["region"],
        "payload": json.loads(stored_record["payload_json"]),
        "validation_status": stored_record["validation_status"],
        "rejection_reason": stored_record["rejection_reason"],
        "ingestion_timestamp": stored_record["ingestion_timestamp"],
    }
    canonical = json.dumps(reconstructed, sort_keys=True, ensure_ascii=True)
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return expected_hash == stored_record.get("record_hash", "")


def replay(
    recorder: Recorder,
    from_sequence: int = 0,
    to_sequence: Optional[int] = None,
    speed: float = 1.0,
    on_event: Optional[Callable] = None,
) -> ReplayResult:
    """
    Replay recorded telemetry in sequence order.

    Args:
        recorder: Recorder instance to read from.
        from_sequence: Start from this sequence number (inclusive).
        to_sequence: End at this sequence number (inclusive). None = replay all.
        speed: Playback speed multiplier. 1.0 = real-time, 2.0 = 2× faster.
               0 = deliver all instantly (no sleep).
        on_event: Optional callback invoked with each replayed record dict.

    Returns:
        ReplayResult with total_replayed, duration_ms, divergences, replay_id.
    """
    replay_id = _compute_replay_id(from_sequence, to_sequence, speed)
    records = recorder.get_range(from_sequence, to_sequence)

    divergences: list[dict] = []
    start_time = time.monotonic()

    for i, record in enumerate(records):
        # --- Divergence detection ---
        is_intact = _verify_record_integrity(record)
        if not is_intact:
            divergences.append({
                "sequence_number": record["sequence_number"],
                "trace_id": record["trace_id"],
                "reason": "record_hash mismatch — stored payload has been mutated",
            })

        # --- Speed-controlled delivery ---
        if speed != 0 and i > 0:
            # Use stored ingestion_timestamp to compute inter-event delay
            prev_record = records[i - 1]
            try:
                from datetime import datetime, timezone
                prev_ts = datetime.fromisoformat(prev_record["ingestion_timestamp"])
                curr_ts = datetime.fromisoformat(record["ingestion_timestamp"])
                delta_seconds = (curr_ts - prev_ts).total_seconds()
                if delta_seconds > 0:
                    sleep_duration = delta_seconds / speed
                    time.sleep(sleep_duration)
            except (ValueError, KeyError):
                # Timestamps not parseable — skip delay
                pass

        # --- Deliver event ---
        if on_event is not None:
            on_event(record)

    end_time = time.monotonic()
    duration_ms = int((end_time - start_time) * 1000)

    return ReplayResult(
        total_replayed=len(records),
        duration_ms=duration_ms,
        divergences=divergences,
        replay_id=replay_id,
    )
