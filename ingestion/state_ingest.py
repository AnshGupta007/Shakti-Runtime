"""
state_ingest.py — SHAKTI Operational State Telemetry Ingestion

Accepts raw state payloads, validates, normalizes, and returns a
deterministic telemetry record. NEVER raises exceptions to caller.
NEVER calls datetime.now() or random() internally.
"""

import hashlib
import json


def _derive_trace_id(source_type: str, device_id: str, raw_payload: dict) -> str:
    """Derive a deterministic trace_id from source_type + device_id + raw_payload hash."""
    payload_canonical = json.dumps(raw_payload, sort_keys=True, ensure_ascii=True)
    content = f"{source_type}:{device_id}:{payload_canonical}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest(raw: dict, ingestion_timestamp: str) -> dict:
    """
    Validate and normalize a raw operational state payload.

    Args:
        raw: Raw state payload dict.
        ingestion_timestamp: ISO-8601 string injected by the caller.

    Returns:
        Normalized telemetry record dict. validation_status is "valid" or "rejected".
        Never raises an exception.
    """
    source_type = "state"

    device_id = str(raw.get("device_id", "")).strip()
    region = str(raw.get("region", "")).strip()
    state_key = str(raw.get("state_key", "")).strip()
    state_value = raw.get("state_value")
    raw_version = raw.get("version")

    trace_id = _derive_trace_id(source_type, device_id, raw)

    # --- Validate required presence ---
    if not device_id:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: device_id")

    if not region:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: region")

    if not state_key:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing or empty required field: state_key")

    if state_value is None:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: state_value")

    if raw_version is None:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: version")

    # --- Validate version is a positive integer ---
    try:
        version_int = int(raw_version)
    except (TypeError, ValueError):
        return _rejected(
            trace_id, source_type, device_id, region, raw, ingestion_timestamp,
            f"version must be an integer, got: '{raw_version}'"
        )

    if version_int <= 0:
        return _rejected(
            trace_id, source_type, device_id, region, raw, ingestion_timestamp,
            f"version must be a positive integer, got: {version_int}"
        )

    return {
        "trace_id": trace_id,
        "source_type": source_type,
        "device_id": device_id,
        "region": region,
        "payload": {
            "state_key": state_key,
            "state_value": str(state_value),
            "version": version_int,
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
