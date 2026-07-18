# Demo Script — Agent Flight Recorder (3 minutes)

## Pre-demo checklist (run 10 minutes before)

- [ ] Docker Desktop running; SigNoz up: `docker compose -f signoz/docker-compose.yaml up -d`
- [ ] SigNoz UI answering at http://localhost:8080 (logged in)
- [ ] Backend: `.venv\Scripts\Activate.ps1; python -m uvicorn api.main:app --port 8000`
- [ ] UI: `cd ui; npm run dev` → http://localhost:5173 loads the incident
- [ ] Verdict cache warm (`.cache/verdict-f809ade2....json` exists) so the card renders instantly
- [ ] Nothing else on ports 5173/8000 (`Get-NetTCPConnection -LocalPort 5173,8000`)
- [ ] Fallback ready: `docs/demo.gif` opens if anything breaks live

## The 3 minutes

**0:00 — The crash (SigNoz).**
"This is a LangGraph support agent, fully instrumented — every LLM call and
tool call is a span." Show the failing trace in SigNoz (service
`support-agent`, red `tool.issue_refund` span): *"A customer asked for a
refund. The agent failed. Traditional observability stops here — a red span."*

**0:40 — The replay (UI, matrix).**
Open http://localhost:5173. "The Flight Recorder pulled that trace from
SigNoz and re-ran the incident under four counterfactual configs — two
models, two temperatures." Point at the matrix: *"All four fail identically.
It's not the model. It's not the temperature."*

**1:20 — The fix proof (waterfalls).**
"Config five applies one structural fix — a corrected knowledge-base entry —
same model, same hot temperature." Point at the two waterfalls, the red
DIVERGES badge: *"Same trace shape, one divergent span: refund_api_v1 fails,
refund_api_v2 passes. The bug was the data."*

**2:00 — The verdict (card).**
"The Crash Investigator diffed those traces and made exactly one Gemini
call." Read the card: root cause, 100% confidence, suggested fix, evidence.
*"And the investigator is itself on the recorder — service
`crash-investigator` in SigNoz. The debugger is debugged."* (Flash the
meta-observability trace.)

**2:40 — Close.**
Show the dashboard (token cost, failure rate, matrix panel, confidence).

> **"Traditional observability ends at the alert. Flight Recorder starts there."**

## If something breaks

1. UI dead → play `docs/demo.gif`, narrate over it.
2. SigNoz dead → the UI still serves cached data; lead with the UI.
3. Groq/Gemini quota → everything shown is cached/pre-recorded; nothing in
   the 3 minutes needs a live LLM call.
