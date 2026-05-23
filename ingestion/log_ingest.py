"""
log_ingest.py — SHAKTI Log Telemetry Ingestion

Accepts raw log payloads, validates, normalizes, and returns a
deterministic telemetry record. NEVER raises exceptions to caller.
NEVER calls datetime.now() or random() internally.
"""

import hashlib
import json

VALID_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}


def _derive_trace_id(source_type: str, device_id: str, raw_payload: dict) -> str:
    """Derive a deterministic trace_id from source_type + device_id + raw_payload hash."""
    payload_canonical = json.dumps(raw_payload, sort_keys=True, ensure_ascii=True)
    content = f"{source_type}:{device_id}:{payload_canonical}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest(raw: dict, ingestion_timestamp: str) -> dict:
    """
    Validate and normalize a raw log payload.

    Args:
        raw: Raw log payload dict.
        ingestion_timestamp: ISO-8601 string injected by the caller.

    Returns:
        Normalized telemetry record dict. validation_status is "valid" or "rejected".
        Never raises an exception.
    """
    source_type = "log"

    device_id = str(raw.get("device_id", "")).strip()
    region = str(raw.get("region", "")).strip()
    level = str(raw.get("level", "")).strip().upper()
    message = str(raw.get("message", "")).strip()
    component = str(raw.get("component", "")).strip()

    trace_id = _derive_trace_id(source_type, device_id, raw)

    # --- Validate required presence ---
    if not device_id:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: device_id")

    if not region:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: region")

    if not level:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: level")

    if not message:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: message")

    if not component:
        return _rejected(trace_id, source_type, device_id, region, raw,
                         ingestion_timestamp, "Missing required field: component")

    # --- Validate level ---
    # Normalize WARN → WARN (not WARNING) for consistency
    normalized_level = "WARN" if level == "WARNING" else level
    if normalized_level not in VALID_LEVELS:
        return _rejected(
            trace_id, source_type, device_id, region, raw, ingestion_timestamp,
            f"Invalid log level '{level}'. Must be one of: DEBUG, INFO, WARN, ERROR, CRITICAL"
        )

    return {
        "trace_id": trace_id,
        "source_type": source_type,
        "device_id": device_id,
        "region": region,
        "payload": {
            "level": normalized_level,
            "message": message,
            "component": component,
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
