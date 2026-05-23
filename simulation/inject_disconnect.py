"""
inject_disconnect.py — SHAKTI Malformed Telemetry Stress Test

Simulates 5 intentionally corrupted/malformed telemetry records.
Each must be rejected gracefully — no crashes.
Prints result: payload type, validation_status, rejection_reason.

Run: python simulation/inject_disconnect.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import sensor_ingest, state_ingest

_TS = "2026-05-23T12:00:00+00:00"


def run_disconnect_injection() -> dict:
    """
    Core logic for disconnect injection. Returns a summary dict.
    Can be called directly from API or as a standalone script.
    """
    corruptions = [
        # 1. Missing required field "device_id"
        {
            "label": "Missing device_id",
            "ingestor": sensor_ingest,
            "payload": {
                "region": "zone-4",
                "metric": "voltage",
                "value": 220.0,
                "unit": "V",
            },
        },
        # 2. Non-numeric voltage value
        {
            "label": "Non-numeric value",
            "ingestor": sensor_ingest,
            "payload": {
                "device_id": "sensor-99",
                "region": "north-grid",
                "metric": "voltage",
                "value": "high!",
                "unit": "V",
            },
        },
        # 3. Unknown metric type
        {
            "label": "Unknown metric type",
            "ingestor": sensor_ingest,
            "payload": {
                "device_id": "sensor-99",
                "region": "north-grid",
                "metric": "magic_field",
                "value": 42.0,
                "unit": "X",
            },
        },
        # 4. Empty region string
        {
            "label": "Empty region",
            "ingestor": sensor_ingest,
            "payload": {
                "device_id": "sensor-99",
                "region": "",
                "metric": "voltage",
                "value": 220.0,
                "unit": "V",
            },
        },
        # 5. Negative version number for state telemetry
        {
            "label": "Negative version (state)",
            "ingestor": state_ingest,
            "payload": {
                "device_id": "controller-01",
                "region": "zone-4",
                "state_key": "expected_state",
                "state_value": "degraded",
                "version": -3,
            },
        },
    ]

    rejections = 0
    crashes = 0

    print("=" * 70)
    print("SHAKTI — Disconnect / Malformed Telemetry Injection")
    print("=" * 70)

    for i, case in enumerate(corruptions, start=1):
        try:
            result = case["ingestor"].ingest(case["payload"], ingestion_timestamp=_TS)
            status = result.get("validation_status", "unknown")
            reason = result.get("rejection_reason", "none")
            if status == "rejected":
                rejections += 1

            print(
                f"[{i}] {case['label']:<30} | "
                f"status={status:<10} | "
                f"reason={reason}"
            )
        except Exception as exc:
            crashes += 1
            print(f"[{i}] {case['label']:<30} | CRASH — {type(exc).__name__}: {exc}")

    print("-" * 70)
    print(
        f"Disconnect injection complete. "
        f"{rejections} rejected. {crashes} crashes."
    )

    return {
        "records_processed": len(corruptions),
        "signals_fired": 0,
        "rejections": rejections,
    }


if __name__ == "__main__":
    run_disconnect_injection()
