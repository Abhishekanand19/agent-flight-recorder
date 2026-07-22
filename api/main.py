"""Small FastAPI backend for the diff UI.

Reads trace data straight from SigNoz's ClickHouse (same zero-auth
docker-exec pattern as the replay engine) and exposes the incident as one
JSON payload. The investigate endpoints wrap the Phase 3 investigator with
a file cache so repeat clicks never burn Gemini quota.

Run: uvicorn api.main:app --port 8000
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.telemetry import get_logger, init_telemetry
from investigator.investigate import find_divergence, latest_run_per_config, tool_sequence
from replay.signoz import fetch_replay_runs, fetch_trace, query

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
init_telemetry(service_name="flight-recorder-api")
log = get_logger("api")

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
REPO_ROOT = Path(__file__).resolve().parent.parent
SIGNOZ_URL = "http://localhost:8080"
SPAN_TABLE = "signoz_traces.distributed_signoz_index_v3"

# Auto-investigations replay only the minimal contrast pair — one failing
# config and the fix config — to protect free-tier quota. The full matrix
# stays available via the CLI.
AUTO_REPLAY_CONFIGS = ["cf-1", "cf-5"]

# Live pipeline state for the UI progress strip. Single-process uvicorn,
# so a module-level dict is enough.
ACTIVE: dict = {"stage": "idle"}

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
                "auto": bool(verdict and verdict.get("triggered_by") == "alert"),
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


@app.get("/api/replay-cost")
def replay_cost():
    """Cost & resource analysis over replay_run spans (metrics stamped at
    replay time). Aggregate totals plus a per-model breakdown."""
    filt = ("WHERE name = 'replay_run' AND mapContains(attributes_number, 'replay.cost_usd')")
    agg = query(
        "SELECT count() AS replays, "
        "sum(attributes_number['replay.tokens']) AS tokens, "
        "sum(attributes_number['replay.cost_usd']) AS cost, "
        "avg(attributes_number['replay.duration_ms']) AS avg_duration_ms, "
        "avg(attributes_number['replay.avg_latency_ms']) AS avg_latency_ms "
        "FROM " + SPAN_TABLE + " " + filt
    )[0]
    by_model = query(
        "SELECT attributes_string['replay.model'] AS model, count() AS replays, "
        "sum(attributes_number['replay.tokens']) AS tokens, "
        "sum(attributes_number['replay.cost_usd']) AS cost, "
        "avg(attributes_number['replay.duration_ms']) AS avg_duration_ms "
        "FROM " + SPAN_TABLE + " " + filt + " GROUP BY model ORDER BY cost DESC"
    )
    replays = int(agg["replays"])
    total_tokens = int(float(agg["tokens"])) if agg["tokens"] else 0
    return {
        "replay_count": replays,
        "total_tokens": total_tokens,
        "total_cost_usd": float(agg["cost"]) if agg["cost"] else 0.0,
        "avg_tokens": total_tokens / replays if replays else 0,
        "avg_duration_ms": float(agg["avg_duration_ms"]) if agg["avg_duration_ms"] else 0.0,
        "avg_latency_ms": float(agg["avg_latency_ms"]) if agg["avg_latency_ms"] else 0.0,
        "by_model": [
            {
                "model": m["model"],
                "replays": int(m["replays"]),
                "tokens": int(float(m["tokens"])) if m["tokens"] else 0,
                "cost_usd": float(m["cost"]) if m["cost"] else 0.0,
                "avg_duration_ms": float(m["avg_duration_ms"]) if m["avg_duration_ms"] else 0.0,
            }
            for m in by_model
        ],
    }


@app.get("/api/failing-tools")
def failing_tools():
    """Which agent tools fail most, from the tool.* spans already in SigNoz.
    Returns per-tool failure count, call count, failure rate, and each tool's
    share of all failures — ranked most-failing first."""
    rows = query(
        "SELECT attributes_string['tool.name'] AS tool, "
        "countIf(status_code_string = 'Error') AS failures, count() AS calls "
        "FROM " + SPAN_TABLE + " WHERE name LIKE 'tool.%' "
        "AND attributes_string['tool.name'] != '' "
        "GROUP BY tool ORDER BY failures DESC, calls DESC"
    )
    total_failures = sum(int(r["failures"]) for r in rows)
    tools = [
        {
            "tool": r["tool"],
            "failures": int(r["failures"]),
            "calls": int(r["calls"]),
            "failure_rate": int(r["failures"]) / int(r["calls"]) if int(r["calls"]) else 0.0,
            "share": int(r["failures"]) / total_failures if total_failures else 0.0,
        }
        for r in rows
    ]
    return {"tools": tools, "total_failures": total_failures}


def _cache_path(trace_id: str) -> Path:
    return CACHE_DIR / f"verdict-{trace_id}.json"


@app.get("/api/investigation/{trace_id}")
def get_investigation(trace_id: str):
    path = _cache_path(trace_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="no investigation cached for this trace")
    return json.loads(path.read_text())


_TRACE_RE = re.compile(r"trace_id:\s*([0-9a-f]{32})")


def _run_cli(args: list[str]) -> str:
    """Run one of our CLIs as a subprocess so its spans carry the right
    service.name (support-agent / replay-engine / crash-investigator), not
    the API's. Returns stdout."""
    result = subprocess.run(
        [sys.executable, "-m", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=900
    )
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()[-400:]}")
    return result.stdout


def _wait_for_trace(trace_id: str, timeout: float = 45.0) -> None:
    """Block until the trace's root span is queryable in ClickHouse — the
    agent subprocess has exited but OTLP ingestion lags a few seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            spans = fetch_trace(trace_id)
            if any(not s["parent_span_id"] and s["attributes_string"].get("request.query") for s in spans):
                return
        except LookupError:
            pass
        time.sleep(2)
    raise RuntimeError(f"trace {trace_id} did not appear in SigNoz within {timeout:.0f}s")


def _investigate_to_cache(trace_id: str, triggered_by: str) -> dict:
    """Run the investigator CLI (own service.name=crash-investigator) and
    cache its verdict tagged with what triggered it."""
    json_out = CACHE_DIR / f"verdict-{trace_id}.tmp.json"
    CACHE_DIR.mkdir(exist_ok=True)
    _run_cli(["investigator.investigate", "--trace-id", trace_id,
              "--triggered-by", triggered_by, "--json-out", str(json_out)])
    verdict = json.loads(json_out.read_text())
    verdict["triggered_by"] = triggered_by
    _cache_path(trace_id).write_text(json.dumps(verdict, indent=1))
    json_out.unlink(missing_ok=True)
    return verdict


def auto_investigate_pipeline(trace_id: str) -> None:
    """The closed loop: replay the minimal contrast pair, then investigate.
    Every stage is visible to the UI via /api/investigations/active."""
    global ACTIVE
    try:
        ACTIVE = {"stage": "replaying", "trace_id": trace_id, "started_at": time.time(),
                  "triggered_by": "alert"}
        log.info("auto-investigation replaying", extra={
            "event": "pipeline.replaying", "incident.trace_id": trace_id})
        for config in AUTO_REPLAY_CONFIGS:
            _run_cli(["replay.engine", "--trace-id", trace_id, "--config", config])

        ACTIVE = {**ACTIVE, "stage": "investigating"}
        log.info("auto-investigation investigating", extra={
            "event": "pipeline.investigating", "incident.trace_id": trace_id})
        verdict = _investigate_to_cache(trace_id, "alert")

        ACTIVE = {**ACTIVE, "stage": "done", "finished_at": time.time()}
        log.info("auto-investigation complete", extra={
            "event": "pipeline.done", "incident.trace_id": trace_id,
            "investigation.confidence": verdict.get("confidence_pct")})
    except Exception as exc:
        ACTIVE = {**ACTIVE, "stage": "failed", "error": str(exc)[-300:]}
        log.error("auto-investigation failed", exc_info=exc, extra={
            "event": "pipeline.failed", "incident.trace_id": trace_id,
            "error.component": "flight-recorder-api"})


def latest_failing_trace() -> str | None:
    rows = query(
        "SELECT trace_id FROM " + SPAN_TABLE + " WHERE name = 'tool.issue_refund' "
        "AND status_code_string = 'Error' "
        "AND `resource_string_service$$name` = 'support-agent' "
        "ORDER BY timestamp DESC LIMIT 1"
    )
    return rows[0]["trace_id"] if rows else None


@app.post("/api/alert-hook")
@app.post("/api/webhook/alert")
def webhook_alert(background: BackgroundTasks, payload: dict | None = None):
    """SigNoz alert webhook: find the most recent failing trace and
    auto-investigate it. Idempotent: cached incidents are never re-run.
    The channel also posts resolved notifications; those are ignored."""
    log.info("alert webhook received", extra={"event": "alert.received"})
    if payload and payload.get("status") == "resolved":
        return {"status": "ignored_resolved_notification"}
    trace_id = latest_failing_trace()
    if trace_id is None:
        log.warning("alert fired but no failing trace found", extra={"event": "alert.no_trace"})
        return {"status": "no_failing_trace_found"}
    if _cache_path(trace_id).exists():
        log.info("incident already investigated, skipping", extra={
            "event": "alert.already_investigated", "incident.trace_id": trace_id})
        return {"status": "already_investigated", "trace_id": trace_id}
    if ACTIVE.get("stage") in ("generating", "replaying", "investigating"):
        log.info("pipeline busy, skipping", extra={"event": "alert.pipeline_busy"})
        return {"status": "pipeline_busy", "active": ACTIVE}
    log.info("dispatching auto-investigation", extra={
        "event": "alert.dispatched", "incident.trace_id": trace_id})
    background.add_task(auto_investigate_pipeline, trace_id)
    return {"status": "investigation_started", "trace_id": trace_id}


def simulate_crash_pipeline() -> None:
    """One-click demo: generate a fresh deterministic failure, then run the
    exact same closed loop an alert would (reuses auto_investigate_pipeline)."""
    global ACTIVE
    try:
        ACTIVE = {"stage": "generating", "started_at": time.time(), "triggered_by": "alert"}
        log.info("simulate: generating incident", extra={"event": "simulate.generating"})
        out = _run_cli(["agent.main"])  # support-agent service, deterministic failure
        match = _TRACE_RE.search(out)
        if not match:
            raise RuntimeError("agent run did not print a trace_id")
        trace_id = match.group(1)
        ACTIVE = {**ACTIVE, "trace_id": trace_id}
        _wait_for_trace(trace_id)
        log.info("simulate: incident captured", extra={
            "event": "simulate.captured", "incident.trace_id": trace_id})
        # Hand off to the same replay -> investigate loop the webhook uses.
        auto_investigate_pipeline(trace_id)
    except Exception as exc:
        ACTIVE = {**ACTIVE, "stage": "failed", "error": str(exc)[-300:]}
        log.error("simulate crash failed", exc_info=exc, extra={
            "event": "simulate.failed", "error.component": "flight-recorder-api"})


@app.post("/api/simulate-crash")
def simulate_crash(background: BackgroundTasks):
    """Trigger the whole incident lifecycle with one click: generate a
    failing trace, replay counterfactuals, investigate. Non-blocking; the UI
    follows along via /api/investigations/active."""
    if ACTIVE.get("stage") in ("generating", "replaying", "investigating"):
        return {"status": "pipeline_busy", "active": ACTIVE}
    log.info("simulate crash requested", extra={"event": "simulate.requested"})
    background.add_task(simulate_crash_pipeline)
    return {"status": "simulation_started"}


@app.get("/api/investigations/active")
def investigations_active():
    return ACTIVE


@app.post("/api/investigate/{trace_id}")
def post_investigate(trace_id: str):
    path = _cache_path(trace_id)
    if path.exists():  # never burn Gemini quota twice for the same trace
        return json.loads(path.read_text())
    log.info("manual investigation requested", extra={
        "event": "investigate.manual", "incident.trace_id": trace_id})
    try:
        # Runs as a subprocess so the investigation keeps service.name=
        # crash-investigator, exactly like the alert-triggered path.
        return _investigate_to_cache(trace_id, "manual")
    except RuntimeError as exc:
        log.error("manual investigation failed", exc_info=exc, extra={
            "event": "investigate.error", "incident.trace_id": trace_id,
            "error.component": "flight-recorder-api"})
        raise HTTPException(status_code=502, detail=str(exc))
