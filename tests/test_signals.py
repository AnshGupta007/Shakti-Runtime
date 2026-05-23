"""
test_signals.py — Phase 3 Proof: Signal Engine Tests

All tests must pass. Each test has at least one assertion.
All telemetry dicts are hand-constructed — no ingest modules needed.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from signals.signal_engine import evaluate_signal, Signal

_TS = "2026-05-23T00:00:00+00:00"
_TRACE = "a" * 64  # dummy trace_id


def _sensor_telemetry(metric: str, value: float, device_id: str = "dev-01",
                       region: str = "north-grid") -> dict:
    return {
        "trace_id": _TRACE,
        "source_type": "sensor",
        "device_id": device_id,
        "region": region,
        "payload": {"metric": metric, "value": value, "unit": "unit"},
        "validation_status": "valid",
        "rejection_reason": None,
        "ingestion_timestamp": _TS,
    }


def _log_telemetry(level: str, message: str, component: str = "comp-01",
                    device_id: str = "dev-01", region: str = "north-grid") -> dict:
    return {
        "trace_id": _TRACE,
        "source_type": "log",
        "device_id": device_id,
        "region": region,
        "payload": {"level": level, "message": message, "component": component},
        "validation_status": "valid",
        "rejection_reason": None,
        "ingestion_timestamp": _TS,
    }


def _state_telemetry(state_key: str, state_value: str, device_id: str = "dev-01",
                      region: str = "north-grid") -> dict:
    return {
        "trace_id": _TRACE,
        "source_type": "state",
        "device_id": device_id,
        "region": region,
        "payload": {"state_key": state_key, "state_value": state_value, "version": 1},
        "validation_status": "valid",
        "rejection_reason": None,
        "ingestion_timestamp": _TS,
    }


# ---------------------------------------------------------------------------
# OVERLOAD tests
# ---------------------------------------------------------------------------

def test_overload_high_severity():
    """voltage = 250 → OVERLOAD with severity 'high'"""
    telemetry = _sensor_telemetry("voltage", 250.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "OVERLOAD"
    assert signal.severity == "high"
    assert signal.metadata["voltage"] == 250.0
    assert signal.metadata["threshold"] == 240.0


def test_overload_critical():
    """voltage = 270 → OVERLOAD with severity 'critical'"""
    telemetry = _sensor_telemetry("voltage", 270.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "OVERLOAD"
    assert signal.severity == "critical"
    assert signal.metadata["voltage"] == 270.0


def test_overload_not_triggered_at_threshold():
    """voltage = 240.0 exactly must NOT trigger OVERLOAD."""
    telemetry = _sensor_telemetry("voltage", 240.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# DEVICE_FAILURE tests
# ---------------------------------------------------------------------------

def test_device_failure_from_log():
    """CRITICAL log with 'fault' in message → DEVICE_FAILURE critical"""
    telemetry = _log_telemetry("CRITICAL", "fault detected in substation loop", "grid-relay")
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "DEVICE_FAILURE"
    assert signal.severity == "critical"
    assert signal.metadata["log_level"] == "CRITICAL"
    assert signal.metadata["component"] == "grid-relay"


def test_device_failure_error_with_offline():
    """ERROR log with 'offline' → DEVICE_FAILURE high"""
    telemetry = _log_telemetry("ERROR", "unit went offline unexpectedly", "network-switch")
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "DEVICE_FAILURE"
    assert signal.severity == "high"


def test_device_failure_not_triggered_for_info():
    """INFO log with 'fault' should NOT trigger — only ERROR/CRITICAL does."""
    telemetry = _log_telemetry("INFO", "fault logged for review", "monitor")
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# DEMAND_SPIKE tests
# ---------------------------------------------------------------------------

def test_demand_spike():
    """current = 160 → DEMAND_SPIKE high"""
    telemetry = _sensor_telemetry("current", 160.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "DEMAND_SPIKE"
    assert signal.severity == "high"
    assert signal.metadata["current"] == 160.0
    assert signal.metadata["baseline"] == 100.0


def test_demand_spike_medium():
    """current = 120 → DEMAND_SPIKE medium"""
    telemetry = _sensor_telemetry("current", 120.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "DEMAND_SPIKE"
    assert signal.severity == "medium"


def test_demand_spike_not_triggered_at_threshold():
    """current = 100.0 exactly must NOT trigger DEMAND_SPIKE."""
    telemetry = _sensor_telemetry("current", 100.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# SENSOR_DRIFT tests
# ---------------------------------------------------------------------------

def test_sensor_drift():
    """frequency = 56.5 → drift = 6.5 > 5 → SENSOR_DRIFT high"""
    telemetry = _sensor_telemetry("frequency", 56.5)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "SENSOR_DRIFT"
    assert signal.severity == "high"
    assert abs(signal.metadata["drift"] - 6.5) < 1e-9


def test_sensor_drift_medium():
    """frequency = 54.0 → drift = 4.0 → SENSOR_DRIFT medium (3 < drift ≤ 5)"""
    telemetry = _sensor_telemetry("frequency", 54.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "SENSOR_DRIFT"
    assert signal.severity == "medium"


def test_sensor_drift_low():
    """frequency = 52.5 → drift = 2.5 → SENSOR_DRIFT low (2 < drift ≤ 3)"""
    telemetry = _sensor_telemetry("frequency", 52.5)
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "SENSOR_DRIFT"
    assert signal.severity == "low"


def test_sensor_drift_not_triggered():
    """frequency = 51.5 → drift = 1.5 ≤ 2.0 → no signal"""
    telemetry = _sensor_telemetry("frequency", 51.5)
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# STATE_MISMATCH tests
# ---------------------------------------------------------------------------

def test_state_mismatch():
    """state_key='expected_state', state_value != 'operational' → STATE_MISMATCH high"""
    telemetry = _state_telemetry("expected_state", "degraded")
    signal = evaluate_signal(telemetry, triggered_at=_TS)

    assert signal is not None
    assert signal.signal_type == "STATE_MISMATCH"
    assert signal.severity == "high"
    assert signal.metadata["expected"] == "operational"
    assert signal.metadata["actual"] == "degraded"


def test_state_mismatch_not_triggered_when_operational():
    """state_value = 'operational' must NOT trigger STATE_MISMATCH."""
    telemetry = _state_telemetry("expected_state", "operational")
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


def test_state_mismatch_not_triggered_wrong_key():
    """A different state_key must NOT trigger STATE_MISMATCH."""
    telemetry = _state_telemetry("device_mode", "degraded")
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# No signal on normal data
# ---------------------------------------------------------------------------

def test_no_signal_on_normal_data():
    """
    Clean telemetry that triggers no signals:
    - voltage = 220.0 (below 240 threshold)
    """
    telemetry = _sensor_telemetry("voltage", 220.0)
    signal = evaluate_signal(telemetry, triggered_at=_TS)
    assert signal is None


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------

def test_signal_is_deterministic():
    """Same telemetry input must always produce the same signal output."""
    telemetry = _sensor_telemetry("voltage", 265.0)

    s1 = evaluate_signal(telemetry, triggered_at=_TS)
    s2 = evaluate_signal(telemetry, triggered_at=_TS)

    assert s1 is not None
    assert s2 is not None
    assert s1.signal_type == s2.signal_type
    assert s1.severity == s2.severity
    assert s1.metadata == s2.metadata
    assert s1.trigger_trace_id == s2.trigger_trace_id
