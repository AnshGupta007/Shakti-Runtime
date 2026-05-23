"""
inject_failure.py — SHAKTI Failure Injection Simulation

Simulates a device fault loop:
- Emits 3 consecutive CRITICAL log telemetry records.
- Passes each through signal_engine → expects DEVICE_FAILURE signal.
- Records all to the replay store.
- Prints each signal with timestamp and severity.
- Exits with summary line.

Run: python simulation/inject_failure.py
"""

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import log_ingest
from signals import signal_engine
from replay.recorder import Recorder

_TS_BASE = "2026-05-23T10:00:00+00:00"
_TIMESTAMPS = [
    "2026-05-23T10:00:00+00:00",
    "2026-05-23T10:00:05+00:00",
    "2026-05-23T10:00:10+00:00",
]

_FAULT_PAYLOADS = [
    {
        "device_id": "relay-unit-01",
        "region": "north-grid",
        "level": "CRITICAL",
        "message": "fault detected in substation loop",
        "component": "grid-relay",
    },
    {
        "device_id": "relay-unit-02",
        "region": "north-grid",
        "level": "CRITICAL",
        "message": "fault detected in substation loop",
        "component": "grid-relay",
    },
    {
        "device_id": "relay-unit-03",
        "region": "north-grid",
        "level": "CRITICAL",
        "message": "fault detected in substation loop",
        "component": "grid-relay",
    },
]


def run_failure_injection(recorder: Recorder = None) -> dict:
    """
    Core logic for failure injection. Returns a summary dict.
    Can be called directly from API or as a standalone script.
    """
    if recorder is None:
        recorder = Recorder()

    records_processed = 0
    signals_fired_count = 0

    print("=" * 60)
    print("SHAKTI — Failure Injection Simulation")
    print("=" * 60)

    for i, (payload, ts) in enumerate(zip(_FAULT_PAYLOADS, _TIMESTAMPS), start=1):
        # Ingest
        telemetry = log_ingest.ingest(payload, ingestion_timestamp=ts)

        # Record
        recorder.record(telemetry)
        records_processed += 1

        # Evaluate signal
        signal = signal_engine.evaluate_signal(telemetry, triggered_at=ts)

        if signal is not None:
            signals_fired_count += 1
            print(
                f"[{i}] SIGNAL FIRED | type={signal.signal_type} | "
                f"device={signal.device_id} | severity={signal.severity} | "
                f"timestamp={signal.triggered_at}"
            )
        else:
            print(f"[{i}] No signal for record {telemetry['trace_id'][:12]}...")

    print("-" * 60)
    print(
        f"Failure injection complete. "
        f"{records_processed} records. {signals_fired_count} signals."
    )

    return {
        "records_processed": records_processed,
        "signals_fired": signals_fired_count,
        "rejections": 0,
    }


if __name__ == "__main__":
    run_failure_injection()
