"""Fetch a trace's spans from SigNoz's ClickHouse.

The SigNoz MCP server and Query API both need auth tokens; the ClickHouse
container does not, so we query it directly through docker exec. This is
the same path the verifier agent uses.
"""

import json
import subprocess

CLICKHOUSE_CONTAINER = "signoz-clickhouse"

_QUERY = """
SELECT
    trace_id,
    span_id,
    parent_span_id,
    name,
    attributes_string,
    attributes_number,
    status_code_string,
    status_message,
    timestamp,
    toUnixTimestamp64Nano(timestamp) AS start_ns,
    duration_nano
FROM signoz_traces.distributed_signoz_index_v3
WHERE trace_id = '{trace_id}'
ORDER BY timestamp
FORMAT JSONEachRow
"""


_REPLAY_RUNS_QUERY = """
SELECT
    trace_id,
    timestamp,
    attributes_string['replay.config_id'] AS config_id,
    attributes_string['replay.model'] AS model,
    attributes_number['replay.temperature'] AS temperature,
    attributes_bool['replay.fix_applied'] AS fix_applied,
    attributes_bool['replay.success'] AS success
FROM signoz_traces.distributed_signoz_index_v3
WHERE name = 'replay_run' AND attributes_string['replay.of'] = '{trace_id}'
ORDER BY timestamp
FORMAT JSONEachRow
"""


def _clickhouse(query: str) -> list[dict]:
    result = subprocess.run(
        ["docker", "exec", CLICKHOUSE_CONTAINER, "clickhouse-client", "-q", query],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"clickhouse query failed: {result.stderr.strip()}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _validate_trace_id(trace_id: str) -> None:
    if not all(c in "0123456789abcdef" for c in trace_id) or len(trace_id) != 32:
        raise ValueError(f"trace id must be 32 hex chars, got: {trace_id!r}")


def query(sql: str) -> list[dict]:
    """Run any read-only SQL against SigNoz's ClickHouse, rows as dicts."""
    return _clickhouse(f"{sql} FORMAT JSONEachRow")


def fetch_trace(trace_id: str) -> list[dict]:
    """Return the trace's spans as dicts, oldest first. Raises if not found."""
    _validate_trace_id(trace_id)
    spans = _clickhouse(_QUERY.format(trace_id=trace_id))
    if not spans:
        raise LookupError(f"no spans found in SigNoz for trace_id {trace_id}")
    return spans


def fetch_replay_runs(original_trace_id: str) -> list[dict]:
    """Return replay_run root spans linked to the original trace via replay.of,
    oldest first: config_id, model, temperature, fix_applied, success, trace_id."""
    _validate_trace_id(original_trace_id)
    return _clickhouse(_REPLAY_RUNS_QUERY.format(trace_id=original_trace_id))
