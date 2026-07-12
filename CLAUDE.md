# Agent Flight Recorder — SigNoz Hackathon

## Mission
3 pillars ONLY: (1) OTel-instrumented LangGraph support agent →
SigNoz, (2) Counterfactual replay engine (pull trace via SigNoz API,
re-run with swapped model/temp, emit linked trace), (3) Crash
Investigator (LLM reads diff → root cause + confidence, itself
OTel-instrumented). Plus React diff UI + SigNoz dashboards/alert.
DO NOT add features beyond these. Deadline-critical.

## Stack
- Python 3.11, LangGraph, OpenTelemetry SDK, FastAPI
- LLMs: Groq (llama-3.3-70b) + Gemini free tier. NEVER OpenAI/Anthropic API (cost)
- SigNoz self-hosted via Docker Compose
- UI: React + Vite, /ui folder

## Commands
- SigNoz up: docker compose -f signoz/docker-compose.yaml up -d
- Agent: python -m agent.main
- Replay: python -m replay.engine --trace-id <id>
- UI: cd ui && npm run dev
- Tests: pytest -x

## Rules
- Every LLM call and tool call = its own OTel span with attributes:
  llm.model, llm.temperature, llm.tokens, tool.name, replay.of
- Replay traces MUST carry replay.of=<original_trace_id>
- Max 4 counterfactual runs per incident (free-tier rate limits)
- The demo failure must be DETERMINISTIC: stale KB entry + temp 0.8
- After every feature: run it, verify spans appear in SigNoz, then commit
- Prefer boring, readable code over clever code (judges read the repo)
- After every successful verifier PASS, git commit with a conventional-commit message (feat/fix/docs/chore) AND immediately git push origin main. Never leave commits local.
