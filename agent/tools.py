"""The three support-agent tools. Every tool call gets its own OTel span
with a tool.name attribute (per CLAUDE.md span rules).

Plain functions hold the logic (easy to unit-test); the @tool wrappers
add tracing and are what the LangGraph agent binds to.
"""

import json

from langchain_core.tools import tool
from opentelemetry.trace import Status, StatusCode

from agent import kb
from agent.telemetry import get_logger, get_tracer

log = get_logger("agent")

ORDERS = {
    "123": {"order_id": "123", "status": "delivered", "item": "Mechanical keyboard", "total_usd": 89.00},
    "456": {"order_id": "456", "status": "in_transit", "item": "USB-C dock", "total_usd": 129.00},
}

# refund_api_v1 was decommissioned; the KB still recommends it (stale entry
# kb-001), which is the deterministic root cause of the demo failure.
DECOMMISSIONED_METHODS = {"refund_api_v1"}
SUPPORTED_METHODS = {"refund_api_v2"}


def do_search_kb(query: str) -> str:
    hits = kb.search(query)
    if not hits:
        return "No knowledge base entries matched."
    return json.dumps(hits)


def do_check_order(order_id: str) -> str:
    order = ORDERS.get(order_id.strip().lstrip("#"))
    if order is None:
        return f"ERROR: order {order_id} not found."
    return json.dumps(order)


def do_issue_refund(order_id: str, method: str) -> str:
    order = ORDERS.get(order_id.strip().lstrip("#"))
    if order is None:
        raise ValueError(f"order {order_id} not found")
    if order["status"] != "delivered":
        raise ValueError(f"order {order_id} is not delivered yet; refunds require delivery")
    if method in DECOMMISSIONED_METHODS:
        raise ValueError(
            f"{method} was decommissioned; refunds require refund_api_v2 with an approval token"
        )
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"unknown refund method '{method}'; supported: {sorted(SUPPORTED_METHODS)}")
    return f"Refund of ${order['total_usd']:.2f} issued for order {order['order_id']} via {method}."


@tool
def search_kb(query: str) -> str:
    """Search the internal knowledge base for policies and procedures."""
    with get_tracer().start_as_current_span("tool.search_kb") as span:
        span.set_attribute("tool.name", "search_kb")
        span.set_attribute("tool.input", query)
        log.info("knowledge base searched", extra={
            "event": "tool.invoked", "tool.name": "search_kb", "tool.input": query})
        return do_search_kb(query)


@tool
def check_order(order_id: str) -> str:
    """Look up an order by id and return its status and details."""
    with get_tracer().start_as_current_span("tool.check_order") as span:
        span.set_attribute("tool.name", "check_order")
        span.set_attribute("tool.input", order_id)
        log.info("order looked up", extra={
            "event": "tool.invoked", "tool.name": "check_order", "tool.input": order_id})
        return do_check_order(order_id)


@tool
def issue_refund(order_id: str, method: str) -> str:
    """Issue a refund for an order. Requires the order id and the refund method
    named in the refund policy."""
    with get_tracer().start_as_current_span("tool.issue_refund") as span:
        span.set_attribute("tool.name", "issue_refund")
        span.set_attribute("tool.input", json.dumps({"order_id": order_id, "method": method}))
        log.info("refund requested", extra={
            "event": "tool.invoked", "tool.name": "issue_refund",
            "order.id": order_id, "refund.method": method})
        try:
            result = do_issue_refund(order_id, method)
            log.info("refund issued", extra={
                "event": "tool.succeeded", "tool.name": "issue_refund", "order.id": order_id})
            return result
        except ValueError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            log.error("refund failed", exc_info=exc, extra={
                "event": "tool.error", "tool.name": "issue_refund",
                "order.id": order_id, "refund.method": method, "error.component": "agent"})
            return f"ERROR: refund failed: {exc}"
