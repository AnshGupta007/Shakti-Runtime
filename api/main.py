"""
main.py — SHAKTI FastAPI Surface

Seven thin route handlers. All business logic lives in the modules.
Routes are wiring + validation + response formatting ONLY.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ingestion import sensor_ingest, log_ingest, state_ingest
from replay.recorder import Recorder
from replay import replay_engine as replay_mod
from signals import signal_engine, metrics

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SHAKTI Runtime API",
    version="1.0",
    description="Deterministic telemetry ingestion, replay, and signal detection."
)

# Shared recorder instance (single SQLite file for the API lifetime)
_recorder = Recorder()

# Stores the most recent ReplayResult for GET /replay/status
_last_replay_result: Optional[replay_mod.ReplayResult] = None

# Accumulates all signals fired since startup
_all_signals: deque = deque(maxlen=1000)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    source_type: str
    payload: dict


class ReplayStartRequest(BaseModel):
    from_sequence: int = 0
    to_sequence: Optional[int] = None
    speed: float = 1.0


class SimulateRequest(BaseModel):
    scenario: str  # "failure" | "spike" | "disconnect"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ingest_router(source_type: str, payload: dict, ts: str) -> dict:
    """Route to the correct ingest module and return normalized record."""
    if source_type == "sensor":
        return sensor_ingest.ingest(payload, ingestion_timestamp=ts)
    elif source_type == "log":
        return log_ingest.ingest(payload, ingestion_timestamp=ts)
    elif source_type == "state":
        return state_ingest.ingest(payload, ingestion_timestamp=ts)
    else:
        raise ValueError(f"Unknown source_type: '{source_type}'")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Return API health status."""
    return {
        "status": "ok",
        "version": "1.0",
        "timestamp": _now_iso(),
    }


@app.post("/ingest")
def ingest(request: IngestRequest):
    """
    Ingest a telemetry record. Evaluates all signals.
    Returns normalized telemetry + any signals fired.
    """
    ts = _now_iso()

    try:
        telemetry = _ingest_router(request.source_type, request.payload, ts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Record to store
    _recorder.record(telemetry)

    # Update metrics
    metrics.record_ingest(telemetry["validation_status"])

    # Evaluate signals
    fired_signals = signal_engine.evaluate_all_signals(telemetry, triggered_at=ts)
    signals_out = []
    for sig in fired_signals:
        sig_dict = sig.to_dict()
        metrics.record_signal(sig.signal_type, sig_dict)
        _all_signals.append(sig_dict)
        signals_out.append(sig_dict)

    return {
        "telemetry": telemetry,
        "signals_fired": signals_out,
    }


@app.post("/replay/start")
async def replay_start(request: ReplayStartRequest):
    """Start a replay run in a thread (non-blocking to the event loop)."""
    global _last_replay_result

    result = await asyncio.to_thread(
        replay_mod.replay,
        recorder=_recorder,
        from_sequence=request.from_sequence,
        to_sequence=request.to_sequence,
        speed=request.speed,
        on_event=None,
    )
    _last_replay_result = result
    metrics.record_replay(result.duration_ms)

    return {
        "total_replayed": result.total_replayed,
        "duration_ms": result.duration_ms,
        "divergences": result.divergences,
        "replay_id": result.replay_id,
    }


@app.get("/replay/status")
def replay_status():
    """Return the most recent replay result. 404 if none has run."""
    if _last_replay_result is None:
        raise HTTPException(status_code=404, detail="No replay has run yet.")
    r = _last_replay_result
    return {
        "total_replayed": r.total_replayed,
        "duration_ms": r.duration_ms,
        "divergences": r.divergences,
        "replay_id": r.replay_id,
    }


@app.get("/signals")
def get_signals(signal_type: Optional[str] = Query(default=None)):
    """
    Return all signals fired since startup.
    Optional filter: ?signal_type=OVERLOAD
    """
    if signal_type:
        filtered = [s for s in _all_signals if s["signal_type"] == signal_type.upper()]
        return {"signals": filtered, "count": len(filtered)}
    return {"signals": list(_all_signals), "count": len(_all_signals)}


@app.get("/metrics")
def get_metrics():
    """Return in-memory observability counters snapshot."""
    return metrics.snapshot()


@app.post("/simulate")
def simulate(request: SimulateRequest):
    """
    Run a simulation scenario directly (no subprocess).
    Scenario: 'failure' | 'spike' | 'disconnect'
    """
    scenario = request.scenario.lower()

    if scenario == "failure":
        from simulation.inject_failure import run_failure_injection
        result = run_failure_injection(recorder=_recorder)
    elif scenario == "spike":
        from simulation.inject_spike import run_spike_injection
        result = run_spike_injection(recorder=_recorder)
    elif scenario == "disconnect":
        from simulation.inject_disconnect import run_disconnect_injection
        result = run_disconnect_injection()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{scenario}'. Must be: failure, spike, disconnect"
        )

    return {
        "scenario": scenario,
        "records_processed": result.get("records_processed", 0),
        "signals_fired": result.get("signals_fired", 0),
        "rejections": result.get("rejections", 0),
    }
