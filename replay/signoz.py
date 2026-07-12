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
    timestamp
FROM signoz_traces.distributed_signoz_index_v3
WHERE trace_id = '{trace_id}'
ORDER BY timestamp
FORMAT JSONEachRow
"""


def fetch_trace(trace_id: str) -> list[dict]:
    """Return the trace's spans as dicts, oldest first. Raises if not found."""
    if not all(c in "0123456789abcdef" for c in trace_id) or len(trace_id) != 32:
        raise ValueError(f"trace id must be 32 hex chars, got: {trace_id!r}")
    result = subprocess.run(
        ["docker", "exec", CLICKHOUSE_CONTAINER, "clickhouse-client", "-q",
         _QUERY.format(trace_id=trace_id)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"clickhouse query failed: {result.stderr.strip()}")
    spans = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if not spans:
        raise LookupError(f"no spans found in SigNoz for trace_id {trace_id}")
    return spans
