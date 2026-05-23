"""
test_ingest.py — Phase 1 Proof: Telemetry Ingestion Tests

All tests must pass. Each test has at least one assertion.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion import sensor_ingest, log_ingest, state_ingest

_TS = "2026-05-23T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Sensor tests
# ---------------------------------------------------------------------------

def test_sensor_valid_payload():
    raw = {
        "device_id": "sensor-01",
        "region": "north-grid",
        "metric": "voltage",
        "value": 220.5,
        "unit": "V",
    }
    result = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "valid"
    assert result["rejection_reason"] is None
    assert result["source_type"] == "sensor"
    assert result["device_id"] == "sensor-01"
    assert result["region"] == "north-grid"
    assert result["payload"]["metric"] == "voltage"
    assert result["payload"]["value"] == 220.5
    assert result["payload"]["unit"] == "V"
    assert result["ingestion_timestamp"] == _TS
    assert "trace_id" in result
    assert len(result["trace_id"]) == 64  # SHA-256 hex


def test_sensor_malformed_metric():
    """Unknown metric should be rejected gracefully — no exception."""
    raw = {
        "device_id": "sensor-01",
        "region": "north-grid",
        "metric": "warp_power",       # invalid
        "value": 99.0,
        "unit": "W",
    }
    result = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "rejected"
    assert result["rejection_reason"] is not None
    assert "warp_power" in result["rejection_reason"]
    # Must NOT raise — function returned normally


def test_sensor_non_numeric_value():
    """Non-numeric value should be rejected — no crash."""
    raw = {
        "device_id": "sensor-02",
        "region": "zone-4",
        "metric": "voltage",
        "value": "NOT_A_NUMBER",
        "unit": "V",
    }
    result = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "rejected"
    assert result["rejection_reason"] is not None
    assert "NOT_A_NUMBER" in result["rejection_reason"] or "Non-numeric" in result["rejection_reason"]


# ---------------------------------------------------------------------------
# Log tests
# ---------------------------------------------------------------------------

def test_log_valid_payload():
    raw = {
        "device_id": "relay-01",
        "region": "south-hub",
        "level": "ERROR",
        "message": "  disk threshold exceeded  ",
        "component": "storage-monitor",
    }
    result = log_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "valid"
    assert result["rejection_reason"] is None
    assert result["source_type"] == "log"
    assert result["payload"]["level"] == "ERROR"
    # message should be stripped
    assert result["payload"]["message"] == "disk threshold exceeded"
    assert result["payload"]["component"] == "storage-monitor"
    assert result["ingestion_timestamp"] == _TS


def test_log_invalid_level():
    """Invalid log level should be rejected."""
    raw = {
        "device_id": "relay-01",
        "region": "south-hub",
        "level": "VERBOSE",           # not a valid level
        "message": "some log message",
        "component": "monitor",
    }
    result = log_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "rejected"
    assert result["rejection_reason"] is not None
    assert "VERBOSE" in result["rejection_reason"]


# ---------------------------------------------------------------------------
# State tests
# ---------------------------------------------------------------------------

def test_state_valid_payload():
    raw = {
        "device_id": "controller-01",
        "region": "zone-4",
        "state_key": "expected_state",
        "state_value": "operational",
        "version": 3,
    }
    result = state_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert result["validation_status"] == "valid"
    assert result["rejection_reason"] is None
    assert result["source_type"] == "state"
    assert result["payload"]["state_key"] == "expected_state"
    assert result["payload"]["state_value"] == "operational"
    assert result["payload"]["version"] == 3
    assert result["ingestion_timestamp"] == _TS


# ---------------------------------------------------------------------------
# Determinism and timestamp injection tests
# ---------------------------------------------------------------------------

def test_trace_id_is_deterministic():
    """Same raw input must always produce the same trace_id."""
    raw = {
        "device_id": "sensor-X",
        "region": "north-grid",
        "metric": "current",
        "value": 55.0,
        "unit": "A",
    }
    r1 = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)
    r2 = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)

    assert r1["trace_id"] == r2["trace_id"]
    assert len(r1["trace_id"]) == 64


def test_timestamp_is_injected_not_generated():
    """
    The ingestion_timestamp in the record must exactly match what was passed in.
    This verifies the module stores the caller-provided timestamp, not its own.
    """
    specific_ts = "2099-12-31T23:59:59+00:00"
    raw = {
        "device_id": "sensor-Z",
        "region": "zone-4",
        "metric": "pressure",
        "value": 101.3,
        "unit": "kPa",
    }
    result = sensor_ingest.ingest(raw, ingestion_timestamp=specific_ts)

    assert result["ingestion_timestamp"] == specific_ts
    # If the module called datetime.now(), this would be a different value.


def test_sensor_missing_device_id():
    """Missing device_id must produce a rejected record, not a crash."""
    raw = {
        "region": "north-grid",
        "metric": "voltage",
        "value": 220.0,
        "unit": "V",
    }
    result = sensor_ingest.ingest(raw, ingestion_timestamp=_TS)
    assert result["validation_status"] == "rejected"
    assert "device_id" in result["rejection_reason"]


def test_state_negative_version():
    """Negative version must be rejected."""
    raw = {
        "device_id": "ctrl-01",
        "region": "zone-4",
        "state_key": "mode",
        "state_value": "active",
        "version": -1,
    }
    result = state_ingest.ingest(raw, ingestion_timestamp=_TS)
    assert result["validation_status"] == "rejected"
    assert result["rejection_reason"] is not None
