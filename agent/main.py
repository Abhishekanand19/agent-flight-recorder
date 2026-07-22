"""Run the demo support request: refund order #123.

This fails deterministically: the KB's refund policy (kb-001) is stale and
points at the decommissioned refund_api_v1, so issue_refund always errors.
"""

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from agent.graph import build_graph
from agent.telemetry import get_logger, get_tracer, init_telemetry, shutdown_telemetry

log = get_logger("agent")

DEMO_QUERY = "Please refund order #123."


def run_request(query: str) -> tuple[str, str]:
    """Run one support request under a root span. Returns (trace_id, answer)."""
    graph = build_graph()
    with get_tracer().start_as_current_span("support_request") as span:
        span.set_attribute("request.query", query)
        trace_id = format(span.get_span_context().trace_id, "032x")
        log.info("support request received", extra={
            "event": "request.received", "request.query": query})
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(query)]},
                config={"recursion_limit": 12},
            )
            answer = result["messages"][-1].content
            log.info("support request completed", extra={"event": "request.completed"})
        except GraphRecursionError:
            answer = "Agent gave up: recursion limit reached without a final answer."
            log.warning("agent hit recursion limit", extra={"event": "request.recursion_limit"})
    return trace_id, answer


def main() -> None:
    load_dotenv()
    init_telemetry()
    trace_id, answer = run_request(DEMO_QUERY)
    print(f"trace_id: {trace_id}")
    print(f"answer: {answer}")
    shutdown_telemetry()


if __name__ == "__main__":
    main()
