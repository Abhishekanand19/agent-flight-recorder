"""Demo Mode — a clean, self-contained state for the deployed app.

Enabled with DEMO_MODE=1 (set on Railway). The Operations Center starts
EMPTY: no incidents, zeroed stats, empty panels. Each "Simulate Crash"
reveals one REAL captured incident from demo_data/catalog.json (produced by
scripts/reset_demo_data.py from genuine system output), so the first click
naturally generates the first incident and everything a judge sees is real,
just replayed statically. All aggregates are computed from what has been
revealed so far.

Local development leaves DEMO_MODE unset and keeps querying live SigNoz.
Revealed state is in-memory, so a fresh process (or redeploy) starts clean.
"""

import json
import os
import time
from pathlib import Path

DEMO_MODE = os.getenv("DEMO_MODE") == "1"
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_data"

_SIM_STAGES = [("generating", 3), ("replaying", 5), ("investigating", 5)]

# Incidents revealed so far (trace_ids, oldest first). Starts empty.
_revealed: list[str] = []


def _load(name: str):
    path = DEMO_DIR / name
    return json.loads(path.read_text()) if path.exists() else None


def _catalog() -> list[dict]:
    return (_load("catalog.json") or {}).get("seeds", [])


def _seed(trace_id: str) -> dict | None:
    return next((s for s in _catalog() if s["trace_id"] == trace_id), None)


def _revealed_seeds() -> list[dict]:
    by_id = {s["trace_id"]: s for s in _catalog()}
    return [by_id[t] for t in _revealed if t in by_id]


# ----- endpoint payloads, derived from revealed incidents -----

def incidents():
    return {"incidents": [s["row"] for s in reversed(_revealed_seeds())]}


def stats():
    seeds = _revealed_seeds()
    n = len(seeds)
    replay_runs = sum(s["contribution"]["replay"]["count"] for s in seeds)
    successes = sum(s["contribution"]["replay"]["successes"] for s in seeds)
    confs = [s["row"].get("confidence") for s in seeds if s["row"].get("confidence") is not None]
    rcs = [s["row"].get("root_cause_seconds") for s in seeds if s["row"].get("root_cause_seconds")]
    return {
        "status": "monitoring",
        "traces_today": replay_runs + n,
        "last_span_age_s": 25.0 if n else None,
        "incidents_total": n,
        "incidents_today": n,
        "active_incidents": sum(1 for s in seeds if not s["row"].get("fix_validated")),
        "open_investigations": sum(1 for s in seeds if not s["row"].get("investigated")),
        "investigations": sum(1 for s in seeds if s["row"].get("investigated")),
        "replay_runs": replay_runs,
        "replay_success_rate": (successes / replay_runs) if replay_runs else None,
        "last_replay_age_s": 25.0 if n else None,
        "avg_confidence": (sum(confs) / len(confs)) if confs else None,
        "avg_root_cause_s": (sum(rcs) / len(rcs)) if rcs else None,
        "alert": {"name": "Agent failure rate spike", "state": "inactive"},
    }


def failing_tools():
    totals: dict[str, dict] = {}
    for s in _revealed_seeds():
        for tool, c in s["contribution"]["tools"].items():
            t = totals.setdefault(tool, {"failures": 0, "calls": 0})
            t["failures"] += c["failures"]
            t["calls"] += c["calls"]
    total_failures = sum(t["failures"] for t in totals.values())
    tools = [
        {"tool": tool, "failures": t["failures"], "calls": t["calls"],
         "failure_rate": (t["failures"] / t["calls"]) if t["calls"] else 0.0,
         "share": (t["failures"] / total_failures) if total_failures else 0.0}
        for tool, t in sorted(totals.items(), key=lambda kv: -kv[1]["failures"])
    ]
    return {"tools": tools, "total_failures": total_failures}


def replay_cost():
    seeds = _revealed_seeds()
    runs = sum(s["contribution"]["replay"]["count"] for s in seeds)
    tokens = sum(s["contribution"]["replay"]["tokens"] for s in seeds)
    cost = sum(s["contribution"]["replay"]["cost_usd"] for s in seeds)
    durs = [s["contribution"]["replay"]["avg_duration_ms"] for s in seeds]
    lats = [s["contribution"]["replay"]["avg_latency_ms"] for s in seeds]

    by_model: dict[str, dict] = {}
    for s in seeds:
        for m in s["contribution"]["replay"].get("by_model", []):
            agg = by_model.setdefault(m["model"], {"replays": 0, "tokens": 0, "cost_usd": 0.0,
                                                   "_durs": []})
            agg["replays"] += m["replays"]
            agg["tokens"] += m["tokens"]
            agg["cost_usd"] += m["cost_usd"]
            agg["_durs"].append(m.get("avg_duration_ms", 0.0))
    by_model_list = [
        {"model": name, "replays": a["replays"], "tokens": a["tokens"], "cost_usd": a["cost_usd"],
         "avg_duration_ms": (sum(a["_durs"]) / len(a["_durs"])) if a["_durs"] else 0.0}
        for name, a in sorted(by_model.items(), key=lambda kv: -kv[1]["cost_usd"])
    ]
    return {
        "replay_count": runs,
        "total_tokens": tokens,
        "total_cost_usd": cost,
        "avg_tokens": (tokens / runs) if runs else 0,
        "avg_duration_ms": (sum(durs) / len(durs)) if durs else 0.0,
        "avg_latency_ms": (sum(lats) / len(lats)) if lats else 0.0,
        "by_model": by_model_list,
    }


def knowledge_base():
    entries = []
    for s in _revealed_seeds():
        v = investigation(s["trace_id"]) or {}
        entries.append({
            "incident_id": s["trace_id"],
            "root_cause": v.get("root_cause", s["row"].get("root_cause", "")),
            "supporting_evidence": v.get("supporting_evidence", []),
            "suggested_fix": v.get("suggested_fix", ""),
            "confidence_pct": v.get("confidence_pct", s["row"].get("confidence")),
            "timestamp": v.get("timestamp"),
            "triggered_by": "alert",
        })
    return {"incidents": list(reversed(entries))}


def incident(trace_id: str):
    return _load(f"incident-{trace_id}.json")


def investigation(trace_id: str):
    return _load(f"verdict-{trace_id}.json")


def primary_incident_id() -> str | None:
    cat = _catalog()
    return cat[0]["trace_id"] if cat else None


def _next_seed() -> dict | None:
    for s in _catalog():
        if s["trace_id"] not in _revealed:
            return s
    cat = _catalog()
    return cat[-1] if cat else None  # all revealed — reuse the last one


def run_simulation(active_setter) -> None:
    """Animate the pipeline, then reveal the next captured incident."""
    seed = _next_seed()
    if seed is None:
        active_setter({"stage": "idle"})
        return
    tid = seed["trace_id"]
    for stage, wait in _SIM_STAGES:
        active_setter({"stage": stage, "trace_id": None if stage == "generating" else tid,
                       "triggered_by": "alert", "demo": True})
        time.sleep(wait)
    if tid not in _revealed:
        _revealed.append(tid)  # the incident now exists in the fleet
    active_setter({"stage": "done", "trace_id": tid, "triggered_by": "alert",
                   "demo": True, "finished_at": time.time()})
