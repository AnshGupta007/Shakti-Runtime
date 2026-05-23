"""
metrics.py — SHAKTI In-Memory Observability Counters

Maintains runtime counters. Resets on process restart (intentional).
All counters are updated via explicit calls from the API layer.
The snapshot() function returns a point-in-time dict of all metrics.
"""

import time
from typing import Any

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

_events_ingested: int = 0
_events_rejected: int = 0
_signals_fired: dict[str, int] = {}
_replay_duration_ms: list[int] = []
_active_signals: list[dict] = []   # signals fired with their epoch timestamp

# Seconds window for "active" signals
_ACTIVE_WINDOW_SECONDS: int = 60


# ---------------------------------------------------------------------------
# Mutators (called from API layer, never from signal engine)
# ---------------------------------------------------------------------------

def record_ingest(validation_status: str) -> None:
    """Call once per ingest — increments ingested and rejected counters."""
    global _events_ingested, _events_rejected
    _events_ingested += 1
    if validation_status == "rejected":
        _events_rejected += 1


def record_signal(signal_type: str, signal_dict: dict) -> None:
    """Call once per fired signal."""
    global _signals_fired
    _signals_fired[signal_type] = _signals_fired.get(signal_type, 0) + 1
    _active_signals.append({
        "signal": signal_dict,
        "_fired_epoch": time.monotonic(),
    })


def record_replay(duration_ms: int) -> None:
    """Call once per replay run with its duration."""
    _replay_duration_ms.append(duration_ms)


def reset() -> None:
    """Reset all counters. Useful for test isolation."""
    global _events_ingested, _events_rejected, _signals_fired
    global _replay_duration_ms, _active_signals
    _events_ingested = 0
    _events_rejected = 0
    _signals_fired = {}
    _replay_duration_ms = []
    _active_signals = []


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def snapshot() -> dict[str, Any]:
    """
    Return a point-in-time snapshot of all metrics.
    Prunes _active_signals to signals fired within the last 60 seconds.
    """
    now = time.monotonic()
    recent = [
        entry["signal"]
        for entry in _active_signals
        if (now - entry["_fired_epoch"]) <= _ACTIVE_WINDOW_SECONDS
    ]

    return {
        "events_ingested": _events_ingested,
        "events_rejected": _events_rejected,
        "signals_fired": dict(_signals_fired),
        "replay_duration_ms": list(_replay_duration_ms),
        "active_signals_last_60s": recent,
        "total_active_signals": len(recent),
    }
