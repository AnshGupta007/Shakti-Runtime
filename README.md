# SHAKTI Runtime

A deterministic telemetry ingestion, replay, and signal detection system for infrastructure monitoring.

---

## What This Project Does

SHAKTI ingests sensor, log, and operational-state telemetry from infrastructure devices, detects anomaly signals (voltage overload, device failure, demand spikes, etc.), records everything to an append-only store, and lets you replay any window of history at configurable speed.

---

## Prerequisites

- **Python 3.10+** (tested on 3.13)
- **pip** (comes with Python)

---

## 1 — Install Dependencies

Open a terminal in the project root and run:

```bash
pip install -r requirements.txt
```

This installs: `fastapi`, `uvicorn`, `pytest`, `pydantic`.

---

## 2 — Run the Tests

```bash
python -m pytest tests/ -v
```

Expected output — **35 tests, all green**:

```
tests/test_ingest.py::test_sensor_valid_payload          PASSED
tests/test_ingest.py::test_sensor_malformed_metric       PASSED
...
tests/test_signals.py::test_signal_is_deterministic      PASSED

============================= 35 passed in 0.31s ==============================
```

---

## 3 — Start the API Server

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

The API is now live at `http://localhost:8000`.

Interactive docs are auto-generated at:  
→ `http://localhost:8000/docs`

---

## 4 — Try the API Endpoints

With the server running, open a second **PowerShell** window and use the commands below.  
All commands use `Invoke-RestMethod` which is built into Windows — no extra tools needed.

> **Easiest option:** open `http://localhost:8000/docs` in your browser.  
> FastAPI generates an interactive UI where you can fill in fields and click **Execute** — no terminal commands required.

### Health check
```powershell
Invoke-RestMethod http://localhost:8000/health
```

### Ingest a sensor record (triggers OVERLOAD signal at 255V)
```powershell
$body = '{"source_type": "sensor", "payload": {"device_id": "sensor-01", "region": "north-grid", "metric": "voltage", "value": 255.0, "unit": "V"}}'
Invoke-RestMethod -Uri http://localhost:8000/ingest -Method POST -ContentType 'application/json' -Body $body
```

### View all fired signals
```powershell
Invoke-RestMethod http://localhost:8000/signals
```

### View metrics / counters
```powershell
Invoke-RestMethod http://localhost:8000/metrics
```

### Replay all stored records (instant, speed=0)
```powershell
$body = '{"from_sequence": 0, "speed": 0}'
Invoke-RestMethod -Uri http://localhost:8000/replay/start -Method POST -ContentType 'application/json' -Body $body
```

### Get last replay result
```powershell
Invoke-RestMethod http://localhost:8000/replay/status
```

---

## 5 — Run the Simulation Scripts

These scripts run independently — **no API server needed**.

### Failure injection — 3 critical fault records → 3 DEVICE_FAILURE signals
```bash
python simulation/inject_failure.py
```

### Demand spike — current values [85, 110, 145, 180, 165, 90] → 4 signals fire
```bash
python simulation/inject_spike.py
```

### Disconnect stress test — 5 malformed payloads, all rejected gracefully, 0 crashes
```bash
python simulation/inject_disconnect.py
```

---

## 6 — Run the Replay Demo

Ingests 5 sensor records, replays them at 2× speed, prints each with sequence number and trace ID:

```bash
python demo/demo_replay.py
```

---

## 7 — Run Simulations via the API

You can also trigger simulations through the API (server must be running).  
Run these in a **PowerShell** window:

```powershell
# Failure scenario
$body = '{"scenario": "failure"}'
Invoke-RestMethod -Uri http://localhost:8000/simulate -Method POST -ContentType 'application/json' -Body $body

# Spike scenario
$body = '{"scenario": "spike"}'
Invoke-RestMethod -Uri http://localhost:8000/simulate -Method POST -ContentType 'application/json' -Body $body

# Disconnect / malformed data scenario
$body = '{"scenario": "disconnect"}'
Invoke-RestMethod -Uri http://localhost:8000/simulate -Method POST -ContentType 'application/json' -Body $body
```

---

## Project Structure

```
shakti/
├── ingestion/          # Telemetry parsers (sensor, log, state)
├── replay/             # Append-only recorder + replay engine
├── signals/            # Signal detection engine + metrics counters
├── simulation/         # Runnable injection scripts
├── api/                # FastAPI routes (thin wiring only)
├── demo/               # Replay demo script
├── tests/              # pytest test suite (35 tests)
├── requirements.txt
├── README.md           ← you are here
└── REVIEW_PACKET.md    # Full proof of execution with terminal output
```

---

## Quick Reference

| Goal | Command |
|------|---------|
| Install | `pip install -r requirements.txt` |
| Test | `python -m pytest tests/ -v` |
| Start API | `uvicorn api.main:app --reload` |
| Failure sim | `python simulation/inject_failure.py` |
| Spike sim | `python simulation/inject_spike.py` |
| Disconnect sim | `python simulation/inject_disconnect.py` |
| Replay demo | `python demo/demo_replay.py` |
