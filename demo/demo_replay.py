"""
demo_replay.py — SHAKTI Replay Demo

Ingests 5 sensor records, records them, replays at speed=2.0,
and prints each replayed record with sequence number and trace_id.

Run: python demo/demo_replay.py
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import sensor_ingest
from replay.recorder import Recorder
from replay import replay_engine

# Use a temporary store so the demo doesn't pollute the main store
_DEMO_DB = Path(tempfile.mkdtemp()) / "demo_replay.db"

_SENSOR_DATA = [
    {"device_id": "sensor-A", "region": "north-grid", "metric": "voltage",     "value": 220.5, "unit": "V",  "ts": "2026-05-23T09:00:00+00:00"},
    {"device_id": "sensor-B", "region": "north-grid", "metric": "current",     "value": 95.2,  "unit": "A",  "ts": "2026-05-23T09:00:05+00:00"},
    {"device_id": "sensor-C", "region": "zone-4",     "metric": "temperature", "value": 72.0,  "unit": "°C", "ts": "2026-05-23T09:00:10+00:00"},
    {"device_id": "sensor-D", "region": "zone-4",     "metric": "pressure",    "value": 1013.0,"unit": "hPa","ts": "2026-05-23T09:00:15+00:00"},
    {"device_id": "sensor-E", "region": "south-hub",  "metric": "frequency",   "value": 50.1,  "unit": "Hz", "ts": "2026-05-23T09:00:20+00:00"},
]


def main():
    print("=" * 65)
    print("SHAKTI — Replay Demo (speed=2.0)")
    print("=" * 65)

    # --- Ingest and record 5 sensors ---
    recorder = Recorder(store_path=_DEMO_DB)

    print("\n[INGEST PHASE]")
    for entry in _SENSOR_DATA:
        ts = entry["ts"]
        payload = {k: v for k, v in entry.items() if k != "ts"}
        telemetry = sensor_ingest.ingest(payload, ingestion_timestamp=ts)
        trace_id = recorder.record(telemetry)
        print(f"  Recorded trace_id={trace_id[:16]}... ts={ts}")

    print(f"\n  Total records in store: {recorder.count()}")

    # --- Replay at speed=2.0 ---
    print("\n[REPLAY PHASE — speed=2.0]")
    replayed_events = []

    def on_event(record: dict):
        replayed_events.append(record)
        print(
            f"  seq={record['sequence_number']:>3} | "
            f"trace_id={record['trace_id'][:16]}... | "
            f"device={record['device_id']:<10} | "
            f"ts={record['ingestion_timestamp']}"
        )

    result = replay_engine.replay(
        recorder=recorder,
        from_sequence=0,
        to_sequence=None,
        speed=2.0,
        on_event=on_event,
    )

    print("\n[REPLAY RESULT]")
    print(f"  total_replayed : {result.total_replayed}")
    print(f"  duration_ms    : {result.duration_ms}")
    print(f"  divergences    : {result.divergences}")
    print(f"  replay_id      : {result.replay_id}")
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
