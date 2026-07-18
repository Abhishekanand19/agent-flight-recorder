"""Small FastAPI backend for the diff UI.

Reads trace data straight from SigNoz's ClickHouse (same zero-auth
docker-exec pattern as the replay engine) and exposes the incident as one
JSON payload. The investigate endpoints wrap the Phase 3 investigator with
a file cache so repeat clicks never burn Gemini quota.

Run: uvicorn api.main:app --port 8000
"""

import json
import os
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from investigator.investigate import find_divergence, latest_run_per_config, tool_sequence
from replay.signoz import fetch_replay_runs, fetch_trace, query

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
SIGNOZ_URL = "http://localhost:8080"
SPAN_TABLE = "signoz_traces.distributed_signoz_index_v3"

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


def investigation_status(trace_id: str) -> dict:
    """Has this incident been investigated, and at what confidence?"""
    rows = query(
        "SELECT max(attributes_number['investigation.confidence']) AS confidence, "
        "count() AS n FROM " + SPAN_TABLE + " WHERE name = 'investigation' "
        f"AND attributes_string['investigation.of'] = '{trace_id}'"
    )
    investigated = bool(rows and int(rows[0]["n"]) > 0)
    return {
        "investigated": investigated,
        "confidence": float(rows[0]["confidence"]) if investigated else None,
        "verdict_cached": _cache_path(trace_id).exists(),
    }


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
        "investigation": investigation_status(trace_id),
    }


@app.get("/api/incidents")
def list_incidents():
    """Every incident the Flight Recorder knows: one row per replayed trace."""
    replays = query(
        "SELECT attributes_string['replay.of'] AS trace_id, count() AS replay_count, "
        "countIf(attributes_bool['replay.success']) AS successes, "
        "max(attributes_bool['replay.fix_applied'] AND attributes_bool['replay.success']) AS fix_validated, "
        "max(toUnixTimestamp64Nano(timestamp)) AS last_replay_ns "
        "FROM " + SPAN_TABLE + " WHERE name = 'replay_run' GROUP BY trace_id"
    )
    investigations = {
        r["trace_id"]: r
        for r in query(
            "SELECT attributes_string['investigation.of'] AS trace_id, "
            "max(attributes_number['investigation.confidence']) AS confidence, "
            "max(toUnixTimestamp64Nano(timestamp) + duration_nano) AS investigated_end_ns "
            "FROM " + SPAN_TABLE + " WHERE name = 'investigation' GROUP BY trace_id"
        )
    }
    ids = [r["trace_id"] for r in replays]
    if not ids:
        return {"incidents": []}
    id_list = ", ".join(f"'{i}'" for i in ids)
    roots = {
        r["trace_id"]: r
        for r in query(
            "SELECT trace_id, toUnixTimestamp64Nano(timestamp) AS start_ns, "
            "attributes_string['request.query'] AS request "
            "FROM " + SPAN_TABLE + f" WHERE trace_id IN ({id_list}) AND parent_span_id = ''"
        )
    }
    errors = {
        r["trace_id"]: r
        for r in query(
            "SELECT trace_id, any(status_message) AS error, "
            "min(toUnixTimestamp64Nano(timestamp)) AS error_start_ns "
            "FROM " + SPAN_TABLE + f" WHERE trace_id IN ({id_list}) "
            "AND status_code_string = 'Error' GROUP BY trace_id"
        )
    }

    incidents = []
    for rep in replays:
        tid = rep["trace_id"]
        inv = investigations.get(tid)
        err = errors.get(tid)
        verdict_path = _cache_path(tid)
        verdict = json.loads(verdict_path.read_text()) if verdict_path.exists() else None
        root_cause_seconds = None
        if inv and err:
            root_cause_seconds = (int(inv["investigated_end_ns"]) - int(err["error_start_ns"])) / 1e9
        incidents.append(
            {
                "trace_id": tid,
                "request": roots.get(tid, {}).get("request", ""),
                "started_at_ns": int(roots[tid]["start_ns"]) if tid in roots else None,
                "error": (err or {}).get("error") or None,
                "replay_count": int(rep["replay_count"]),
                "fix_validated": bool(int(rep["fix_validated"])),
                "investigated": inv is not None,
                "confidence": float(inv["confidence"]) if inv else None,
                "root_cause": verdict["root_cause"] if verdict else None,
                "root_cause_seconds": root_cause_seconds,
                "signoz_url": f"{SIGNOZ_URL}/trace/{tid}",
            }
        )
    incidents.sort(key=lambda i: i["started_at_ns"] or 0, reverse=True)
    return {"incidents": incidents}


def latest_alert() -> dict | None:
    """State of our SigNoz alert rule; None if the API isn't reachable."""
    api_key = os.getenv("SIGNOZ_API_KEY")
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            f"{SIGNOZ_URL}/api/v1/rules", headers={"SIGNOZ-API-KEY": api_key}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read()).get("data") or {}
        rules = data.get("rules") if isinstance(data, dict) else data
        for rule in rules or []:
            if rule.get("alert") == "Agent failure rate spike":
                return {"name": rule["alert"], "state": rule.get("state", "unknown")}
    except Exception:
        return None
    return None


@app.get("/api/stats")
def get_stats():
    """Fleet aggregates for the Operations Center status card and tiles."""
    activity = query(
        "SELECT uniqExactIf(trace_id, toDate(timestamp) = today()) AS traces_today, "
        "max(toUnixTimestamp64Nano(timestamp)) AS last_span_ns "
        "FROM " + SPAN_TABLE
    )[0]
    replay = query(
        "SELECT count() AS runs, countIf(attributes_bool['replay.success']) AS successes, "
        "max(toUnixTimestamp64Nano(timestamp)) AS last_replay_ns "
        "FROM " + SPAN_TABLE + " WHERE name = 'replay_run'"
    )[0]
    inv = query(
        "SELECT count() AS investigations, "
        "avg(attributes_number['investigation.confidence']) AS avg_confidence "
        "FROM " + SPAN_TABLE + " WHERE name = 'investigation'"
    )[0]

    incidents = list_incidents()["incidents"]
    now_ns = time.time_ns()
    today_start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) * 1e9
    rc_times = [i["root_cause_seconds"] for i in incidents if i["root_cause_seconds"]]
    return {
        "status": "monitoring",
        "traces_today": int(activity["traces_today"]),
        "last_span_age_s": (now_ns - int(activity["last_span_ns"])) / 1e9 if int(activity["last_span_ns"]) else None,
        "incidents_total": len(incidents),
        "incidents_today": sum(1 for i in incidents if (i["started_at_ns"] or 0) >= today_start),
        "active_incidents": sum(1 for i in incidents if not i["fix_validated"]),
        "open_investigations": sum(1 for i in incidents if not i["investigated"]),
        "investigations": int(inv["investigations"]),
        "replay_runs": int(replay["runs"]),
        "replay_success_rate": int(replay["successes"]) / int(replay["runs"]) if int(replay["runs"]) else None,
        "last_replay_age_s": (now_ns - int(replay["last_replay_ns"])) / 1e9 if int(replay["last_replay_ns"]) else None,
        "avg_confidence": float(inv["avg_confidence"]) if int(inv["investigations"]) else None,
        "avg_root_cause_s": sum(rc_times) / len(rc_times) if rc_times else None,
        "alert": latest_alert(),
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
