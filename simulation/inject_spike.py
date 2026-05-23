"""
inject_spike.py — SHAKTI Demand Spike Injection Simulation

Simulates a demand spike event:
- Emits sensor telemetry for current values: [85, 110, 145, 180, 165, 90]
- Only values > 100 should fire DEMAND_SPIKE.
- Prints each step: value, signal_fired (YES/NO), severity (if YES).

Run: python simulation/inject_spike.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import sensor_ingest
from signals import signal_engine
from replay.recorder import Recorder

_CURRENT_VALUES = [85, 110, 145, 180, 165, 90]

_TIMESTAMPS = [
    "2026-05-23T11:00:00+00:00",
    "2026-05-23T11:00:10+00:00",
    "2026-05-23T11:00:20+00:00",
    "2026-05-23T11:00:30+00:00",
    "2026-05-23T11:00:40+00:00",
    "2026-05-23T11:00:50+00:00",
]


def run_spike_injection(recorder: Recorder = None) -> dict:
    """
    Core logic for spike injection. Returns a summary dict.
    Can be called directly from API or as a standalone script.
    """
    if recorder is None:
        recorder = Recorder()

    signals_fired_count = 0

    print("=" * 60)
    print("SHAKTI — Demand Spike Injection Simulation")
    print("=" * 60)
    print(f"{'Step':>4}  {'Current (A)':>12}  {'Signal':>6}  {'Severity':>10}")
    print("-" * 60)

    for i, (value, ts) in enumerate(zip(_CURRENT_VALUES, _TIMESTAMPS), start=1):
        payload = {
            "device_id": f"meter-{i:02d}",
            "region": "zone-4",
            "metric": "current",
            "value": float(value),
            "unit": "A",
        }

        telemetry = sensor_ingest.ingest(payload, ingestion_timestamp=ts)
        recorder.record(telemetry)

        signal = signal_engine.evaluate_signal(telemetry, triggered_at=ts)

        if signal is not None:
            signals_fired_count += 1
            fired_str = "YES"
            severity_str = signal.severity
        else:
            fired_str = "NO"
            severity_str = "-"

        print(f"{i:>4}  {value:>12.1f}  {fired_str:>6}  {severity_str:>10}")

    print("-" * 60)
    print(f"Spike injection complete. {signals_fired_count} signals fired.")

    return {
        "records_processed": len(_CURRENT_VALUES),
        "signals_fired": signals_fired_count,
        "rejections": 0,
    }


if __name__ == "__main__":
    run_spike_injection()
