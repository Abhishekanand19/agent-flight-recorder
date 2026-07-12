"""Small FastAPI backend for the diff UI.

Reads trace data straight from SigNoz's ClickHouse (same zero-auth
docker-exec pattern as the replay engine) and exposes the incident as one
JSON payload. The investigate endpoints wrap the Phase 3 investigator with
a file cache so repeat clicks never burn Gemini quota.

Run: uvicorn api.main:app --port 8000
"""

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from investigator.investigate import find_divergence, latest_run_per_config, tool_sequence
from replay.signoz import fetch_replay_runs, fetch_trace

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

app = FastAPI(title="Agent Flight Recorder API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def waterfall_spans(spans: list[dict]) -> list[dict]:
    """Convert raw ClickHouse spans into waterfall-ready dicts (relative ms)."""
    trace_start = min(int(s["start_ns"]) for s in spans)
    out = []
    for s in spans:
        attrs = s["attributes_string"]
        out.append(
            {
                "span_id": s["span_id"],
                "parent_span_id": s["parent_span_id"],
                "name": s["name"],
                "start_ms": (int(s["start_ns"]) - trace_start) / 1e6,
                "duration_ms": int(s["duration_nano"]) / 1e6,
                "error": s["status_code_string"] == "Error",
                "error_message": s["status_message"] or None,
                "tool_name": attrs.get("tool.name"),
                "tool_input": attrs.get("tool.input"),
                "llm_model": attrs.get("llm.model"),
            }
        )
    return out


@app.get("/api/incident/{trace_id}")
def get_incident(trace_id: str):
    try:
        original_spans = fetch_trace(trace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    runs = latest_run_per_config(fetch_replay_runs(trace_id))
    replay_spans = {run["trace_id"]: fetch_trace(run["trace_id"]) for run in runs}

    matrix = [
        {
            "config_id": run["config_id"],
            "model": run["model"],
            "temperature": run["temperature"],
            "fix_applied": bool(run["fix_applied"]),
            "success": bool(run["success"]),
            "trace_id": run["trace_id"],
        }
        for run in runs
    ]
    configs = [
        {**m, "tool_sequence": tool_sequence(replay_spans[m["trace_id"]])} for m in matrix
    ]

    fix = next((m for m in matrix if m["success"] and m["fix_applied"]), None)
    return {
        "original": {"trace_id": trace_id, "spans": waterfall_spans(original_spans)},
        "fix": (
            {"trace_id": fix["trace_id"], "config_id": fix["config_id"],
             "spans": waterfall_spans(replay_spans[fix["trace_id"]])}
            if fix
            else None
        ),
        "matrix": matrix,
        "divergence": find_divergence(configs),
    }


def _cache_path(trace_id: str) -> Path:
    return CACHE_DIR / f"verdict-{trace_id}.json"


@app.get("/api/investigation/{trace_id}")
def get_investigation(trace_id: str):
    path = _cache_path(trace_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="no investigation cached for this trace")
    return json.loads(path.read_text())


@app.post("/api/investigate/{trace_id}")
def post_investigate(trace_id: str):
    path = _cache_path(trace_id)
    if path.exists():  # never burn Gemini quota twice for the same trace
        return json.loads(path.read_text())

    load_dotenv()
    from agent.telemetry import init_telemetry
    from investigator.investigate import investigate

    init_telemetry(service_name="crash-investigator")
    try:
        verdict = investigate(trace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(verdict, indent=1))
    return verdict
