"""Demo Mode — serve real captured data from demo_data/ snapshots.

Enabled with DEMO_MODE=1 (set on Railway). Local development leaves it unset
and keeps querying live SigNoz/ClickHouse. The snapshots are produced by
scripts/export_demo_data.py from the running system, so everything a judge
sees is genuine captured output, just static.
"""

import json
import os
import time
from pathlib import Path

DEMO_MODE = os.getenv("DEMO_MODE") == "1"
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_data"


def _load(name: str):
    path = DEMO_DIR / name
    return json.loads(path.read_text()) if path.exists() else None


def _manifest() -> dict:
    return _load("manifest.json") or {}


def incidents():
    return _load("incidents.json") or {"incidents": []}


def stats():
    return _load("stats.json") or {}


def failing_tools():
    return _load("failing-tools.json") or {"tools": [], "total_failures": 0}


def replay_cost():
    return _load("replay-cost.json") or {"replay_count": 0, "by_model": []}


def knowledge_base():
    return _load("knowledge-base.json") or {"incidents": []}


def incident(trace_id: str):
    return _load(f"incident-{trace_id}.json")


def investigation(trace_id: str):
    return _load(f"verdict-{trace_id}.json")


def primary_incident_id() -> str | None:
    return _manifest().get("primary")


# The Simulate Crash demo advances these stages on a timer, then reveals the
# primary captured incident — same UX as the live pipeline, no LLM needed.
_SIM_STAGES = [("generating", 3), ("replaying", 5), ("investigating", 5)]


def run_simulation(active_setter) -> None:
    tid = primary_incident_id()
    for stage, wait in _SIM_STAGES:
        active_setter({"stage": stage, "trace_id": None if stage == "generating" else tid,
                       "triggered_by": "alert", "demo": True})
        time.sleep(wait)
    active_setter({"stage": "done", "trace_id": tid, "triggered_by": "alert",
                   "demo": True, "finished_at": time.time()})
