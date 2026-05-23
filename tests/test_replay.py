"""
test_replay.py — Phase 2 Proof: Replay Engine Tests

All tests must pass. Each test has at least one assertion.
Uses temporary SQLite stores to avoid cross-test pollution.
"""

import json
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import sensor_ingest
from replay.recorder import Recorder
from replay import replay_engine

_TS = "2026-05-23T00:00:00+00:00"
_TS2 = "2026-05-23T00:00:05+00:00"
_TS3 = "2026-05-23T00:00:10+00:00"


def _fresh_recorder() -> Recorder:
    """Create a Recorder backed by a temp SQLite DB (isolated per test)."""
    db_path = Path(tempfile.mkdtemp()) / "test_store.db"
    return Recorder(store_path=db_path)


def _make_sensor_telemetry(device_id: str = "sensor-01", value: float = 100.0,
                            ts: str = _TS) -> dict:
    raw = {
        "device_id": device_id,
        "region": "north-grid",
        "metric": "voltage",
        "value": value,
        "unit": "V",
    }
    return sensor_ingest.ingest(raw, ingestion_timestamp=ts)


# ---------------------------------------------------------------------------
# Recorder tests
# ---------------------------------------------------------------------------

def test_record_writes_to_store():
    """Recording a telemetry record increases the count in the store."""
    recorder = _fresh_recorder()
    assert recorder.count() == 0

    telemetry = _make_sensor_telemetry()
    trace_id = recorder.record(telemetry)

    assert recorder.count() == 1
    assert isinstance(trace_id, str)
    assert len(trace_id) == 64  # SHA-256 hex


def test_record_is_idempotent():
    """
    Recording the same trace_id twice is safe — it appends both
    (the store is append-only). Idempotency is checked via trace_id_exists().
    """
    recorder = _fresh_recorder()
    telemetry = _make_sensor_telemetry()

    trace_id_1 = recorder.record(telemetry)
    # The trace_id must already exist after the first write
    assert recorder.trace_id_exists(trace_id_1)

    # Recording again should NOT crash — recorder accepts duplicates in append-only fashion
    trace_id_2 = recorder.record(telemetry)

    assert trace_id_1 == trace_id_2
    # Both writes succeeded
    assert recorder.count() == 2


# ---------------------------------------------------------------------------
# Replay sequence tests
# ---------------------------------------------------------------------------

def test_replay_sequence_matches_record_order():
    """Replayed events must arrive in monotonically increasing sequence order."""
    recorder = _fresh_recorder()

    for i, ts in enumerate([_TS, _TS2, _TS3], start=1):
        telemetry = _make_sensor_telemetry(device_id=f"sensor-{i:02d}", value=float(i * 10), ts=ts)
        recorder.record(telemetry)

    received = []

    def capture(record):
        received.append(record["sequence_number"])

    result = replay_engine.replay(recorder=recorder, speed=0, on_event=capture)

    assert result.total_replayed == 3
    assert received == sorted(received), "Sequence numbers must be monotonically increasing"
    assert received[0] < received[1] < received[2]


def test_replay_detects_divergence():
    """
    Manually corrupt a stored record's payload_json and verify
    the replay engine detects the hash mismatch as a divergence.
    """
    recorder = _fresh_recorder()
    telemetry = _make_sensor_telemetry()
    recorder.record(telemetry)

    # Get the sequence number that was just written
    records = recorder.get_all()
    assert len(records) == 1
    seq = records[0]["sequence_number"]

    # Corrupt the stored payload_json directly
    corrupted_payload = json.dumps({"metric": "CORRUPTED", "value": 9999.0, "unit": "X"})
    recorder.corrupt_record_for_testing(seq, corrupted_payload)

    # Replay should detect the divergence
    result = replay_engine.replay(recorder=recorder, speed=0)

    assert len(result.divergences) == 1
    assert result.divergences[0]["sequence_number"] == seq
    assert "mismatch" in result.divergences[0]["reason"].lower()


def test_replay_result_is_deterministic():
    """Same replay parameters must always produce the same replay_id."""
    recorder = _fresh_recorder()
    telemetry = _make_sensor_telemetry()
    recorder.record(telemetry)

    result_1 = replay_engine.replay(recorder=recorder, from_sequence=0, to_sequence=None, speed=1.0)
    result_2 = replay_engine.replay(recorder=recorder, from_sequence=0, to_sequence=None, speed=1.0)

    assert result_1.replay_id == result_2.replay_id
    assert len(result_1.replay_id) == 64


def test_replay_no_divergence_on_clean_records():
    """Clean records produce zero divergences."""
    recorder = _fresh_recorder()
    for i, ts in enumerate([_TS, _TS2, _TS3], start=1):
        telemetry = _make_sensor_telemetry(device_id=f"clean-{i}", value=float(i), ts=ts)
        recorder.record(telemetry)

    result = replay_engine.replay(recorder=recorder, speed=0)

    assert result.total_replayed == 3
    assert result.divergences == []


def test_replay_from_sequence_filter():
    """Replay from_sequence should exclude earlier records."""
    recorder = _fresh_recorder()

    for i, ts in enumerate([_TS, _TS2, _TS3], start=1):
        telemetry = _make_sensor_telemetry(device_id=f"sensor-{i}", value=float(i), ts=ts)
        recorder.record(telemetry)

    # Get all records to find sequence numbers
    all_records = recorder.get_all()
    assert len(all_records) == 3

    # Replay from the second record onward
    second_seq = all_records[1]["sequence_number"]
    result = replay_engine.replay(recorder=recorder, from_sequence=second_seq, speed=0)

    assert result.total_replayed == 2
