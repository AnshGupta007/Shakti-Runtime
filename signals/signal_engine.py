"""
signal_engine.py — SHAKTI Signal Detection Engine

Five pure, deterministic signal evaluation functions.
No I/O, no logging, no side effects inside evaluate_signal().
Given the same telemetry dict → always produces the same Signal or None.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    signal_type: str       # one of: OVERLOAD, DEVICE_FAILURE, DEMAND_SPIKE, SENSOR_DRIFT, STATE_MISMATCH
    device_id: str
    region: str
    trigger_trace_id: str  # trace_id of the telemetry that triggered this signal
    triggered_at: str      # injected timestamp
    severity: str          # "low" | "medium" | "high" | "critical"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "device_id": self.device_id,
            "region": self.region,
            "trigger_trace_id": self.trigger_trace_id,
            "triggered_at": self.triggered_at,
            "severity": self.severity,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Individual signal evaluators (pure functions)
# ---------------------------------------------------------------------------

def _evaluate_overload(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """OVERLOAD: sensor metric=voltage and value > 240.0"""
    if telemetry.get("source_type") != "sensor":
        return None
    payload = telemetry.get("payload", {})
    if payload.get("metric") != "voltage":
        return None
    try:
        v = float(payload["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if v <= 240.0:
        return None

    severity = "critical" if v > 260.0 else "high"
    return Signal(
        signal_type="OVERLOAD",
        device_id=telemetry["device_id"],
        region=telemetry["region"],
        trigger_trace_id=telemetry["trace_id"],
        triggered_at=triggered_at,
        severity=severity,
        metadata={"voltage": v, "threshold": 240.0},
    )


def _evaluate_device_failure(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """DEVICE_FAILURE: log level=ERROR or CRITICAL, message contains 'fault', 'failure', or 'offline'"""
    if telemetry.get("source_type") != "log":
        return None
    payload = telemetry.get("payload", {})
    level = payload.get("level", "")
    if level not in ("ERROR", "CRITICAL"):
        return None

    message = payload.get("message", "").lower()
    trigger_words = ("fault", "failure", "offline")
    if not any(word in message for word in trigger_words):
        return None

    severity = "critical" if level == "CRITICAL" else "high"
    return Signal(
        signal_type="DEVICE_FAILURE",
        device_id=telemetry["device_id"],
        region=telemetry["region"],
        trigger_trace_id=telemetry["trace_id"],
        triggered_at=triggered_at,
        severity=severity,
        metadata={"log_level": level, "component": payload.get("component", "")},
    )


def _evaluate_demand_spike(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """DEMAND_SPIKE: sensor metric=current and value > 100.0"""
    if telemetry.get("source_type") != "sensor":
        return None
    payload = telemetry.get("payload", {})
    if payload.get("metric") != "current":
        return None
    try:
        v = float(payload["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if v <= 100.0:
        return None

    severity = "high" if v > 150.0 else "medium"
    return Signal(
        signal_type="DEMAND_SPIKE",
        device_id=telemetry["device_id"],
        region=telemetry["region"],
        trigger_trace_id=telemetry["trace_id"],
        triggered_at=triggered_at,
        severity=severity,
        metadata={"current": v, "baseline": 100.0},
    )


def _evaluate_sensor_drift(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """SENSOR_DRIFT: sensor metric=frequency and abs(value - 50.0) > 2.0"""
    if telemetry.get("source_type") != "sensor":
        return None
    payload = telemetry.get("payload", {})
    if payload.get("metric") != "frequency":
        return None
    try:
        v = float(payload["value"])
    except (KeyError, TypeError, ValueError):
        return None

    drift = abs(v - 50.0)
    if drift <= 2.0:
        return None

    if drift > 5.0:
        severity = "high"
    elif drift > 3.0:
        severity = "medium"
    else:
        severity = "low"

    return Signal(
        signal_type="SENSOR_DRIFT",
        device_id=telemetry["device_id"],
        region=telemetry["region"],
        trigger_trace_id=telemetry["trace_id"],
        triggered_at=triggered_at,
        severity=severity,
        metadata={"frequency": v, "nominal": 50.0, "drift": drift},
    )


def _evaluate_state_mismatch(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """STATE_MISMATCH: state record with state_key='expected_state' and state_value != 'operational'"""
    if telemetry.get("source_type") != "state":
        return None
    payload = telemetry.get("payload", {})
    if payload.get("state_key") != "expected_state":
        return None
    state_value = payload.get("state_value", "")
    if state_value == "operational":
        return None

    return Signal(
        signal_type="STATE_MISMATCH",
        device_id=telemetry["device_id"],
        region=telemetry["region"],
        trigger_trace_id=telemetry["trace_id"],
        triggered_at=triggered_at,
        severity="high",
        metadata={"expected": "operational", "actual": state_value},
    )


# ---------------------------------------------------------------------------
# Public evaluate_signal — evaluates ALL five signals
# ---------------------------------------------------------------------------

_EVALUATORS = [
    _evaluate_overload,
    _evaluate_device_failure,
    _evaluate_demand_spike,
    _evaluate_sensor_drift,
    _evaluate_state_mismatch,
]


def evaluate_signal(telemetry: dict, triggered_at: str) -> Optional[Signal]:
    """
    Evaluate all SHAKTI signals against the given telemetry record.

    Pure function — no side effects, no I/O, no logging.
    Returns the first matching Signal, or None if no signal fires.

    Args:
        telemetry: Normalized telemetry record dict.
        triggered_at: ISO-8601 timestamp injected by the caller.

    Returns:
        Signal dataclass or None.
    """
    for evaluator in _EVALUATORS:
        result = evaluator(telemetry, triggered_at)
        if result is not None:
            return result
    return None


def evaluate_all_signals(telemetry: dict, triggered_at: str) -> list[Signal]:
    """
    Evaluate all SHAKTI signals and return ALL that fire (not just the first).

    Args:
        telemetry: Normalized telemetry record dict.
        triggered_at: ISO-8601 timestamp injected by the caller.

    Returns:
        List of Signal dataclasses (may be empty).
    """
    results = []
    for evaluator in _EVALUATORS:
        result = evaluator(telemetry, triggered_at)
        if result is not None:
            results.append(result)
    return results
