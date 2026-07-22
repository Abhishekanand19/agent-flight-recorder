"""Groq LLM wrapper. Every LLM invocation gets its own OTel span with
llm.model / llm.temperature / llm.tokens attributes (per CLAUDE.md).

Reliability notes (llama-3.3 on Groq, worse at temperature 0.8):
- The model sometimes emits its tool call as a raw `<function=name{json}>`
  tag. Groq's parser rejects the generation with code tool_use_failed.
- parallel_tool_calls=False reduces how often this happens.
- When it still happens, we recover the tool call ourselves by parsing the
  `failed_generation` Groq returns; if that fails too, we re-roll the call
  up to MAX_ATTEMPTS times.
"""

import contextvars
import json
import os
import re
import time
import uuid

from groq import BadRequestError
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq

from agent.telemetry import get_logger, get_tracer

log = get_logger("llm")

# Per-run token/latency accounting. A caller (e.g. the replay engine) opts in
# with reset_usage() and reads get_usage() afterwards; when unset, invoke_llm's
# accounting is a no-op, so the agent and investigator paths are unaffected.
_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar("llm_usage", default=None)


def reset_usage() -> None:
    _usage.set({"tokens": 0, "calls": 0, "latency_ms": 0.0})


def get_usage() -> dict:
    return _usage.get() or {"tokens": 0, "calls": 0, "latency_ms": 0.0}


def _account(tokens: int, latency_ms: float) -> None:
    u = _usage.get()
    if u is not None:
        u["tokens"] += tokens
        u["calls"] += 1
        u["latency_ms"] += latency_ms

MODEL = "llama-3.3-70b-versatile"
TEMPERATURE = 0.8
MAX_ATTEMPTS = 4

_FUNCTION_TAG = re.compile(r"<function=(\w+)\s*(\{.*?\})", re.DOTALL)
_RETRY_DELAY = re.compile(r"[Rr]etry(?:Delay'?:? '?| in )(\d+(?:\.\d+)?)s")


def _rate_limit_delay(exc: Exception) -> float | None:
    """If exc is a provider rate limit (429), return seconds to wait."""
    text = str(exc)
    if "429" not in text and "RESOURCE_EXHAUSTED" not in text and "rate limit" not in text.lower():
        return None
    match = _RETRY_DELAY.search(text)
    return float(match.group(1)) + 2 if match else 60.0


def make_llm(tools: list, model: str = MODEL, temperature: float = TEMPERATURE):
    if model.startswith("gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=model, temperature=temperature, api_key=os.getenv("GEMINI_API_KEY")
        )
        return llm.bind_tools(tools)
    llm = ChatGroq(model=model, temperature=temperature)
    return llm.bind_tools(tools).bind(parallel_tool_calls=False)


def _recover_tool_calls(exc: BadRequestError) -> AIMessage | None:
    """Parse Groq's rejected generation back into a proper tool-call message."""
    body = getattr(exc, "body", None) or {}
    failed = body.get("error", {}).get("failed_generation", "") if isinstance(body, dict) else ""
    matches = _FUNCTION_TAG.findall(failed)
    if not matches:
        return None
    tool_calls = []
    for name, raw_args in matches:
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            return None
        tool_calls.append({"name": name, "args": args, "id": f"recovered_{uuid.uuid4().hex[:8]}"})
    return AIMessage(content="", tool_calls=tool_calls)


def invoke_llm(llm, messages, model: str = MODEL, temperature: float = TEMPERATURE) -> AIMessage:
    with get_tracer().start_as_current_span("llm.chat") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.temperature", temperature)
        log.info("llm request", extra={
            "event": "llm.request", "llm.model": model, "llm.temperature": temperature})
        response = None
        elapsed_ms = 0.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                start = time.perf_counter()
                response = llm.invoke(messages)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                break
            except BadRequestError as exc:
                if "tool_use_failed" not in str(exc):
                    raise
                recovered = _recover_tool_calls(exc)
                if recovered is not None:
                    span.add_event("recovered_tool_call_from_failed_generation", {"attempt": attempt})
                    span.set_attribute("llm.tokens", 0)
                    log.warning("recovered malformed tool call from failed_generation", extra={
                        "event": "llm.tool_use_recovered", "llm.model": model, "llm.attempt": attempt})
                    return recovered
                if attempt == MAX_ATTEMPTS:
                    raise
                span.add_event("groq_tool_use_failed_retry", {"attempt": attempt})
                log.warning("tool_use_failed, re-rolling", extra={
                    "event": "llm.tool_use_failed", "llm.model": model, "llm.attempt": attempt})
            except Exception as exc:
                delay = _rate_limit_delay(exc)
                if delay is None or attempt == MAX_ATTEMPTS:
                    raise
                span.add_event("rate_limited_waiting", {"attempt": attempt, "delay_s": delay})
                log.warning("rate limited, backing off", extra={
                    "event": "llm.rate_limited", "llm.model": model,
                    "llm.attempt": attempt, "llm.retry_delay_s": delay})
                time.sleep(delay)
        usage = response.usage_metadata or {}
        tokens = usage.get("total_tokens", 0)
        span.set_attribute("llm.tokens", tokens)
        span.set_attribute("llm.latency_ms", elapsed_ms)
        _account(tokens, elapsed_ms)
        log.info("llm response", extra={
            "event": "llm.response", "llm.model": model,
            "llm.tokens": tokens, "llm.latency_ms": round(elapsed_ms, 1)})
        return response
