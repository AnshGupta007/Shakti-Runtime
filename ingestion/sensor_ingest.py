"""
sensor_ingest.py — SHAKTI Sensor Telemetry Ingestion

Accepts raw sensor payloads, validates, normalizes, and returns a
deterministic telemetry record. NEVER raises exceptions to caller.
NEVER calls datetime.now() or random() internally.
"""

import hashlib
import json
from typing import Any

VALID_METRICS = {"voltage", "current", "temperature", "pressure", "frequency"}


def _derive_trace_id(source_type: str, device_id: str, raw_payload: dict) -> str:
    """Derive a deterministic trace_id from source_type + device_id + raw_payload hash."""
    payload_canonical = json.dumps(raw_payload, sort_keys=True, ensure_ascii=True)
    content = f"{source_type}:{device_id}:{payload_canonical}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest(raw: dict, ingestion_timestamp: str) -> dict:
    """
    Validate and normalize a raw sensor payload.

    Args:
        raw: Raw sensor payload dict.
        ingestion_timestamp: ISO-8601 string injected by the caller.

    Returns:
        Normalized telemetry record dict. validation_status is "valid" or "rejected".
        Never raises an exception.
    """
    source_type = "sensor"

    # --- Extract fields with safe defaults ---
    device_id = str(raw.get("device_id", "")).strip()
    region = str(raw.get("region", "")).strip()
    metric = str(raw.get("metric", "")).strip()
    raw_value = raw.get("value")
    unit = str(raw.get("unit", "")).strip()

    # Derive trace_id deterministically from the raw payload
    trace_id = _derive_trace_id(source_type, device_id, raw)

    # --- Validate required presence ---
    if not device_id:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: device_id")

    if not region:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: region")

    if not metric:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: metric")

    if raw_value is None:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: value")

    if not unit:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: unit")

    # --- Validate metric ---
    if metric not in VALID_METRICS:
        return _rejected(
            trace_id, source_type, device_id, region, raw, ingestion_timestamp,
            f"Unknown metric '{metric}'. Must be one of: {sorted(VALID_METRICS)}"
        )

    # --- Validate value is numeric ---
    try:
        value_float = float(raw_value)
    except (TypeError, ValueError):
        return _rejected(
            trace_id, source_type, device_id, region, raw, ingestion_timestamp,
            f"Non-numeric value: '{raw_value}'. Expected a number."
        )

    # --- Return normalized valid record ---
    return {
        "trace_id": trace_id,
        "source_type": source_type,
        "device_id": device_id,
        "region": region,
        "payload": {
            "metric": metric,
            "value": value_float,
            "unit": unit,
        },
        "validation_status": "valid",
        "rejection_reason": None,
        "ingestion_timestamp": ingestion_timestamp,
    }


def _rejected(
    trace_id: str,
    source_type: str,
    device_id: str,
    region: str,
    raw: dict,
    ingestion_timestamp: str,
    reason: str,
) -> dict:
    """Build a rejected telemetry record — never raises."""
    return {
        "trace_id": trace_id,
        "source_type": source_type,
        "device_id": device_id,
        "region": region,
        "payload": dict(raw),
        "validation_status": "rejected",
        "rejection_reason": reason,
        "ingestion_timestamp": ingestion_timestamp,
    }
