# Agent Flight Recorder — SigNoz Hackathon

## Mission
3 pillars ONLY: (1) OTel-instrumented LangGraph support agent → SigNoz,
(2) Counterfactual replay engine, (3) Crash Investigator with
meta-observability. Plus React diff UI + SigNoz dashboards/alert + README.
DO NOT add features beyond the plan in PHASES.md. Deadline-critical.

## How to run phases
When I say "run Phase N": read PHASES.md, do ONLY that phase, follow the
Definition of Done, then STOP for my review. Never start the next phase
unprocessed.

## Status
- Phase 1: DONE (agent + SigNoz + deterministic failing trace f809ade2...)
- Phase 2: DONE (replay engine, 4 configs). NOTE: all 4 FAIL identically
  (stale-KB trap). A fix-config cf-5 with replay.success=true and
  replay.fix_applied=true must exist to give the demo contrast — verify
  this before Phase 3 depends on it.
- Phase 3,4,5: TODO (see PHASES.md)

## Stack
- Python 3.11, LangGraph, OpenTelemetry SDK, FastAPI
- LLMs: Groq (llama-3.3-70b) + Gemini 2.5-flash, free tiers ONLY.
  NEVER OpenAI/Anthropic API (cost).
- SigNoz self-hosted, Docker. UI http://localhost:8080 (NOT 3301).
  OTLP ingestion localhost:4317. Traces pulled via docker exec into
  ClickHouse (zero-auth, reliable).
- UI: React + Vite in /ui

## Commands
- SigNoz up: docker compose -f signoz/docker-compose.yaml up -d
- Agent: python -m agent.main
- Replay: python -m replay.engine --trace-id <id>
- Investigate: python -m investigator.investigate --trace-id <id>
- UI: cd ui && npm run dev
- Tests: pytest -x

## Rules
- Every LLM call and tool call = its own OTel span with attributes:
  llm.model, llm.temperature, llm.tokens, tool.name; replay traces carry
  replay.of=<original_trace_id>.
- Max 4-5 counterfactual runs per incident (free-tier rate limits).
  Respect Gemini 5 req/min: sleep on advertised retryDelay, 60s pause
  before Gemini configs. Never re-run passing configs to save quota.
- The demo failure must stay DETERMINISTIC.
- Prefer boring, readable code over clever code (judges read the repo).
- After each phase passes: invoke the verifier agent; only on PASS make a
  conventional commit (feat/fix/docs/chore) AND immediately
  git push origin main. Never leave commits local.
