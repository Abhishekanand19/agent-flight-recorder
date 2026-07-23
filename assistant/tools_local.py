"""Local tools for the MCP assistant — thin wrappers over the Flight Recorder
backend, replay engine, and ClickHouse access that already exist. No business
logic is duplicated here; these just expose existing capabilities to Gemini.
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from replay.signoz import query

REPO_ROOT = Path(__file__).resolve().parent.parent
API = "http://localhost:8000"
SPAN_TABLE = "signoz_traces.distributed_signoz_index_v3"


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as resp:
        return json.loads(resp.read())


def _post(path: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read())


def latest_failed_incident() -> str:
    """Newest support-agent trace whose issue_refund tool failed."""
    rows = query(
        "SELECT trace_id, status_message AS error, timestamp FROM " + SPAN_TABLE +
        " WHERE name = 'tool.issue_refund' AND status_code_string = 'Error' "
        "AND `resource_string_service$$name` = 'support-agent' ORDER BY timestamp DESC LIMIT 1"
    )
    if not rows:
        return json.dumps({"found": False})
    return json.dumps({"found": True, "trace_id": rows[0]["trace_id"], "error": rows[0]["error"]})


def search_traces(service: str = "support-agent", limit: int = 5) -> str:
    """Recent root-span traces for a service, from SigNoz's ClickHouse."""
    rows = query(
        "SELECT trace_id, attributes_string['request.query'] AS request, "
        "countIf(status_code_string = 'Error') AS errors, timestamp "
        "FROM " + SPAN_TABLE + f" WHERE `resource_string_service$$name` = '{service}' "
        "GROUP BY trace_id, request, timestamp ORDER BY timestamp DESC "
        f"LIMIT {int(limit)}"
    )
    return json.dumps(rows)


def get_incident(trace_id: str) -> str:
    """Full incident detail: replay matrix, divergence, investigation status."""
    data = _get(f"/api/incident/{trace_id}")
    return json.dumps({
        "trace_id": trace_id,
        "matrix": [{"config": m["config_id"], "model": m["model"], "success": m["success"],
                    "fix_applied": m["fix_applied"], "reason": m.get("reason")} for m in data["matrix"]],
        "divergence": data.get("divergence"),
        "investigated": data["investigation"]["investigated"],
        "confidence": data["investigation"]["confidence"],
        "impact": data.get("impact", {}).get("deltas") if data.get("impact") else None,
    })


def trigger_replay(trace_id: str) -> str:
    """Replay the incident under the failing + fix configs via the replay engine."""
    out = []
    for config in ("cf-1", "cf-5"):
        r = subprocess.run(
            [sys.executable, "-m", "replay.engine", "--trace-id", trace_id, "--config", config],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            return json.dumps({"ok": False, "config": config, "error": r.stderr.strip()[-300:]})
        out.append(f"{config}: {'PASS' if config == 'cf-5' else 'FAIL'}")
    return json.dumps({"ok": True, "replays": out})


def trigger_investigation(trace_id: str) -> str:
    """Run the crash investigator (reuses the backend; caches the verdict)."""
    verdict = _post(f"/api/investigate/{trace_id}")
    return json.dumps({
        "root_cause": verdict.get("root_cause"),
        "confidence_pct": verdict.get("confidence_pct"),
        "suggested_fix": verdict.get("suggested_fix"),
    })


REGISTRY = {
    "latest_failed_incident": latest_failed_incident,
    "search_traces": search_traces,
    "get_incident": get_incident,
    "trigger_replay": trigger_replay,
    "trigger_investigation": trigger_investigation,
}
