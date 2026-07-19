"""Crash Investigator.

Pulls the original failing trace and its linked counterfactual replays from
SigNoz, computes a structured diff (what the failing configs did vs the
fix-applied config), asks Gemini ONCE for a root-cause verdict as strict
JSON, and prints a plain-English verdict card.

Meta-observability: the investigator is itself OTel-instrumented under
service.name=crash-investigator — the debugger is also on the flight
recorder.

Usage: python -m investigator.investigate --trace-id <original-trace-id>
"""

import argparse
import json
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from agent.llm import invoke_llm
from agent.telemetry import get_tracer, init_telemetry, shutdown_telemetry

INVESTIGATOR_MODEL = "gemini-2.5-flash"
INVESTIGATOR_TEMPERATURE = 0.0

FALLBACK_VERDICT = {
    "root_cause": "investigation inconclusive (LLM returned unparseable output)",
    "confidence_pct": 0,
    "suggested_fix": "re-run the investigation",
    "supporting_evidence": [],
}

PROMPT_TEMPLATE = """You are a crash investigator for an LLM support agent.
An incident occurred and was replayed under several counterfactual configs.
Below is the structured evidence: the original failure and, per config, the
model, temperature, whether a structural fix was applied, whether it
succeeded, and its tool-call sequence.

{diff_json}

Determine the root cause of the original failure. Respond with ONLY a valid
JSON object, no code fences, no other text, with exactly these keys:
- "root_cause": one or two sentences naming the underlying cause
- "confidence_pct": integer 0-100
- "suggested_fix": one sentence, the concrete fix
- "supporting_evidence": array of short strings citing the evidence above
"""


def tool_sequence(spans: list[dict]) -> list[dict]:
    """Extract the ordered tool calls (tool, input, error) from a trace's spans."""
    sequence = []
    for span in spans:
        if not span["name"].startswith("tool."):
            continue
        sequence.append(
            {
                "tool": span["attributes_string"].get("tool.name", span["name"]),
                "input": span["attributes_string"].get("tool.input", ""),
                "error": span["status_message"] if span["status_code_string"] == "Error" else None,
            }
        )
    return sequence


def latest_run_per_config(replay_runs: list[dict]) -> list[dict]:
    """Replays may have been run more than once; keep the newest per config_id."""
    by_config: dict[str, dict] = {}
    for run in replay_runs:  # oldest first, so later entries win
        by_config[run["config_id"]] = run
    return sorted(by_config.values(), key=lambda r: r["config_id"])


def find_divergence(configs: list[dict]) -> dict | None:
    """First tool call where the successful config differs from a failing one."""
    succeeded = [c for c in configs if c["success"]]
    failed = [c for c in configs if not c["success"]]
    if not succeeded or not failed:
        return None
    fix_seq = succeeded[0]["tool_sequence"]
    fail_seq = failed[0]["tool_sequence"]
    for i, fix_step in enumerate(fix_seq):
        fail_step = fail_seq[i] if i < len(fail_seq) else None
        if fail_step is None or (fix_step["tool"], fix_step["input"]) != (
            fail_step["tool"],
            fail_step["input"],
        ):
            return {
                "position": i,
                "tool": fix_step["tool"],
                "successful_config_did": fix_step,
                "failing_config_did": fail_step,
            }
    return None


def build_diff(original_spans: list[dict], replay_runs: list[dict], replay_spans: dict) -> dict:
    """Structured evidence for the LLM: original failure + per-config outcomes."""
    original_errors = [
        {"span": s["name"], "error": s["status_message"]}
        for s in original_spans
        if s["status_code_string"] == "Error"
    ]
    root = next((s for s in original_spans if not s["parent_span_id"]), {})
    configs = []
    for run in latest_run_per_config(replay_runs):
        configs.append(
            {
                "config_id": run["config_id"],
                "model": run["model"],
                "temperature": run["temperature"],
                "fix_applied": bool(run["fix_applied"]),
                "success": bool(run["success"]),
                "tool_sequence": tool_sequence(replay_spans[run["trace_id"]]),
            }
        )
    return {
        "original_request": root.get("attributes_string", {}).get("request.query", ""),
        "original_errors": original_errors,
        "original_tool_sequence": tool_sequence(original_spans),
        "configs": configs,
        "succeeded_configs": [c["config_id"] for c in configs if c["success"]],
        "failed_configs": [c["config_id"] for c in configs if not c["success"]],
        "divergence": find_divergence(configs),
    }


def parse_verdict(text: str) -> dict:
    """Parse the LLM's verdict defensively; fall back rather than crash."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return dict(FALLBACK_VERDICT)
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return dict(FALLBACK_VERDICT)
    if not all(k in raw for k in ("root_cause", "confidence_pct", "suggested_fix", "supporting_evidence")):
        return dict(FALLBACK_VERDICT)
    try:
        confidence = max(0, min(100, int(raw["confidence_pct"])))
    except (TypeError, ValueError):
        confidence = 0
    evidence = raw["supporting_evidence"]
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    return {
        "root_cause": str(raw["root_cause"]),
        "confidence_pct": confidence,
        "suggested_fix": str(raw["suggested_fix"]),
        "supporting_evidence": [str(e) for e in evidence],
    }


def print_verdict_card(verdict: dict, diff: dict) -> None:
    line = "=" * 72
    print(line)
    print("CRASH INVESTIGATION VERDICT")
    print(line)
    print(f"Root cause:    {verdict['root_cause']}")
    print(f"Confidence:    {verdict['confidence_pct']}%")
    print(f"Suggested fix: {verdict['suggested_fix']}")
    if verdict["supporting_evidence"]:
        print("Evidence:")
        for item in verdict["supporting_evidence"]:
            print(f"  - {item}")
    n_failed = len(diff["failed_configs"])
    n_total = len(diff["configs"])
    fixed = ", ".join(diff["succeeded_configs"]) or "none"
    print(line)
    print(f"Replay summary: {n_failed}/{n_total} configs failed; fix-applied config(s) that "
          f"succeeded: {fixed}")
    print(line)


def investigate(original_trace_id: str, triggered_by: str = "manual") -> dict:
    """Run the full investigation under its own trace. Returns the verdict."""
    from replay.signoz import fetch_replay_runs, fetch_trace

    tracer = get_tracer()
    with tracer.start_as_current_span("investigation") as span:
        investigation_trace_id = format(span.get_span_context().trace_id, "032x")
        span.set_attribute("investigation.of", original_trace_id)
        span.set_attribute("investigation.triggered_by", triggered_by)

        with tracer.start_as_current_span("fetch.traces") as fetch_span:
            original_spans = fetch_trace(original_trace_id)
            replay_runs = fetch_replay_runs(original_trace_id)
            replay_spans = {run["trace_id"]: fetch_trace(run["trace_id"]) for run in replay_runs}
            fetch_span.set_attribute("fetch.replay_count", len(replay_runs))

        diff = build_diff(original_spans, replay_runs, replay_spans)

        from langchain_google_genai import ChatGoogleGenerativeAI
        import os

        llm = ChatGoogleGenerativeAI(
            model=INVESTIGATOR_MODEL,
            temperature=INVESTIGATOR_TEMPERATURE,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        prompt = PROMPT_TEMPLATE.format(diff_json=json.dumps(diff, indent=1))
        response = invoke_llm(
            llm,
            [HumanMessage(prompt)],
            model=INVESTIGATOR_MODEL,
            temperature=INVESTIGATOR_TEMPERATURE,
        )
        verdict = parse_verdict(response.content if isinstance(response.content, str) else str(response.content))
        span.set_attribute("investigation.confidence", verdict["confidence_pct"])

    print(f"investigation trace: {investigation_trace_id}")
    print_verdict_card(verdict, diff)
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate a failing trace via its replays.")
    parser.add_argument("--trace-id", required=True, help="original trace id (32 hex chars)")
    parser.add_argument("--triggered-by", default="manual", help="what initiated this (manual/alert)")
    parser.add_argument("--json-out", default=None, help="also write the verdict JSON to this path")
    args = parser.parse_args()

    load_dotenv()
    init_telemetry(service_name="crash-investigator")
    verdict = investigate(args.trace_id, triggered_by=args.triggered_by)
    if args.json_out:
        from pathlib import Path

        Path(args.json_out).write_text(json.dumps(verdict, indent=1))
    shutdown_telemetry()


if __name__ == "__main__":
    main()
