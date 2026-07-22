"""Counterfactual replay engine.

Pulls an original trace from SigNoz, reconstructs the incident, then re-runs
the support agent under 4 counterfactual configs (model x temperature),
each emitting its own OTel trace linked back via replay.of.

Usage: python -m replay.engine --trace-id <32-hex-id>
"""

import argparse
import json
import time

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from opentelemetry.trace import Status, StatusCode

from agent import kb
from agent.graph import build_graph
from agent.telemetry import get_logger, get_tracer, init_telemetry, shutdown_telemetry
from agent.tools import DECOMMISSIONED_METHODS

log = get_logger("replay")

# Max 4 counterfactual runs per incident (CLAUDE.md rule / free-tier limits),
# plus cf-5: the fix-validation run. It uses the SAME model and temperature as
# the original incident, with the corrected KB entry applied — so the only
# changed variable is the structural fix.
CONFIGS = [
    {"config_id": "cf-1", "model": "llama-3.3-70b-versatile", "temperature": 0.8},
    {"config_id": "cf-2", "model": "llama-3.3-70b-versatile", "temperature": 0.0},
    {"config_id": "cf-3", "model": "gemini-2.5-flash", "temperature": 0.8},
    {"config_id": "cf-4", "model": "gemini-2.5-flash", "temperature": 0.0},
    {"config_id": "cf-5", "model": "llama-3.3-70b-versatile", "temperature": 0.8, "fix_applied": True},
]

SECONDS_BETWEEN_RUNS = 5
# Gemini free tier allows 5 requests/min and one agent loop uses ~5, so a
# Gemini run needs a fresh minute of quota before it starts.
SECONDS_BEFORE_GEMINI = 60
CORRECT_ORDER_ID = "123"


def reconstruct_incident(spans: list[dict]) -> dict:
    """Rebuild the original request, tool history, and KB context from spans."""
    root = next((s for s in spans if not s["parent_span_id"]), None)
    if root is None or "request.query" not in root["attributes_string"]:
        raise ValueError("trace has no root span with a request.query attribute")
    request = root["attributes_string"]["request.query"]

    tool_history = []
    kb_context = []
    for span in spans:
        if not span["name"].startswith("tool."):
            continue
        tool_input = span["attributes_string"].get("tool.input", "")
        tool_history.append(
            {
                "tool": span["attributes_string"].get("tool.name", span["name"]),
                "input": tool_input,
                "error": span["status_message"] if span["status_code_string"] == "Error" else None,
            }
        )
        if span["name"] == "tool.search_kb":
            # KB is deterministic in-process data: re-running the recorded
            # query reproduces exactly what the agent saw.
            kb_context.extend(e for e in kb.search(tool_input) if e not in kb_context)

    return {"request": request, "tool_history": tool_history, "kb_context": kb_context}


def classify_success(messages: list) -> bool:
    """replay.success: acted on the correct order and avoided the wrong refund.

    True iff the agent (a) called check_order/issue_refund for order 123 and
    for no other order, and (b) never tried a decommissioned refund method.
    """
    acted_on_correct_order = False
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            args = call["args"]
            if call["name"] in ("check_order", "issue_refund"):
                order_id = str(args.get("order_id", "")).strip().lstrip("#")
                if order_id == CORRECT_ORDER_ID:
                    acted_on_correct_order = True
                else:
                    return False
            if call["name"] == "issue_refund" and args.get("method") in DECOMMISSIONED_METHODS:
                return False
    return acted_on_correct_order


def run_replay(config: dict, request: str, original_trace_id: str) -> dict:
    """Run one counterfactual config under its own linked trace."""
    fix_applied = bool(config.get("fix_applied"))
    with get_tracer().start_as_current_span("replay_run") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        span.set_attribute("replay.of", original_trace_id)
        span.set_attribute("replay.config_id", config["config_id"])
        span.set_attribute("replay.model", config["model"])
        span.set_attribute("replay.temperature", config["temperature"])
        span.set_attribute("replay.fix_applied", fix_applied)
        log.info("replay started", extra={
            "event": "replay.started", "replay.of": original_trace_id,
            "replay.config_id": config["config_id"], "replay.model": config["model"],
            "replay.temperature": config["temperature"], "replay.fix_applied": fix_applied})
        success = False
        error = None
        if fix_applied:
            kb.set_entries(kb.FIXED_ENTRIES)
        try:
            graph = build_graph(model=config["model"], temperature=config["temperature"])
            result = graph.invoke(
                {"messages": [HumanMessage(request)]},
                config={"recursion_limit": 12},
            )
            success = classify_success(result["messages"])
        except GraphRecursionError:
            error = "recursion limit reached"
        except Exception as exc:  # keep going: remaining configs must still run
            error = f"{type(exc).__name__}: {exc}"
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            log.error("replay errored", exc_info=exc, extra={
                "event": "replay.error", "replay.config_id": config["config_id"],
                "replay.of": original_trace_id, "error.component": "replay"})
        finally:
            if fix_applied:
                kb.set_entries(kb.ENTRIES)
        span.set_attribute("replay.success", success)
        log.info("replay finished", extra={
            "event": "replay.finished", "replay.config_id": config["config_id"],
            "replay.of": original_trace_id, "replay.success": success,
            "replay.trace_id": trace_id})
    return {**config, "success": success, "trace_id": trace_id, "error": error}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a SigNoz trace under counterfactual configs.")
    parser.add_argument("--trace-id", required=True, help="original trace id (32 hex chars)")
    parser.add_argument(
        "--config",
        choices=[c["config_id"] for c in CONFIGS],
        help="run only this config (default: all)",
    )
    args = parser.parse_args()

    load_dotenv()
    init_telemetry(service_name="replay-engine")

    from replay.signoz import fetch_trace  # after dotenv, keeps import cheap for tests

    spans = fetch_trace(args.trace_id)
    incident = reconstruct_incident(spans)

    print(f"original trace: {args.trace_id} ({len(spans)} spans)")
    print(f"request: {incident['request']}")
    print("tool history:")
    for entry in incident["tool_history"]:
        outcome = f"ERROR: {entry['error']}" if entry["error"] else "ok"
        print(f"  - {entry['tool']}({entry['input']}) -> {outcome}")
    print(f"kb context: {json.dumps([e['id'] for e in incident['kb_context']])}")
    print()

    configs = [c for c in CONFIGS if args.config is None or c["config_id"] == args.config]
    results = []
    for i, config in enumerate(configs):
        fix_note = " [fix applied]" if config.get("fix_applied") else ""
        print(f"replaying {config['config_id']}: {config['model']} @ temp={config['temperature']}{fix_note} ...")
        results.append(run_replay(config, incident["request"], args.trace_id))
        if i < len(configs) - 1:
            next_is_gemini = configs[i + 1]["model"].startswith("gemini")
            time.sleep(SECONDS_BEFORE_GEMINI if next_is_gemini else SECONDS_BETWEEN_RUNS)

    print()
    print(f"{'config':<7} {'model':<24} {'temp':<5} {'fix':<5} {'result':<7} replay trace_id")
    for r in results:
        verdict = "ERROR" if r["error"] else ("PASS" if r["success"] else "FAIL")
        fix = "yes" if r.get("fix_applied") else "no"
        print(f"{r['config_id']:<7} {r['model']:<24} {r['temperature']:<5} {fix:<5} {verdict:<7} {r['trace_id']}")
        if r["error"]:
            print(f"        error: {r['error']}")

    shutdown_telemetry()


if __name__ == "__main__":
    main()
