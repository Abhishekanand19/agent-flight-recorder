# MCP Assistant — Gemini + the official SigNoz MCP server

A natural-language incident assistant. Gemini orchestrates two families of
tools to investigate an incident and answer in plain English:

- **SigNoz-native tools** served by the **official SigNoz MCP server**
  (`signoz/signoz-mcp-server`) — `signoz_list_services`,
  `signoz_list_dashboards`, `signoz_search_docs`, `signoz_get_field_keys`.
  Only the subset that works against the running SigNoz version is exposed.
- **Flight Recorder tools** (`assistant/tools_local.py`) — thin wrappers over
  the existing backend, replay engine, and investigator:
  `latest_failed_incident`, `search_traces`, `get_incident`,
  `trigger_replay`, `trigger_investigation`. No business logic is duplicated.

```
You (natural language)
   │
   ▼  Gemini 2.5-flash (function calling loop, assistant/mcp_assistant.py)
   ├── SigNoz MCP server (HTTP :8009) ─▶ SigNoz (services, dashboards, docs, fields)
   └── local tools ─▶ ClickHouse / FastAPI :8000 / replay.engine / investigator
```

## Prerequisites (one-time)

1. SigNoz up, FastAPI backend on :8000, and `GEMINI_API_KEY` + `SIGNOZ_API_KEY`
   in `.env` (already used by the rest of the project — nothing new).
2. Install deps: `pip install google-genai mcp` (in requirements.txt).
3. Run the official SigNoz MCP server (Docker) on port 8009, joined to the
   SigNoz network so it can reach SigNoz internally:

   ```powershell
   $key = ((Get-Content .env | Where-Object { $_ -match '^SIGNOZ_API_KEY=' }) -split '=',2)[1]
   docker run -d --name signoz-mcp --network signoz-net -p 8009:8009 `
     -e TRANSPORT_MODE=http -e MCP_SERVER_PORT=8009 `
     -e SIGNOZ_URL=http://signoz:8080 -e SIGNOZ_API_KEY=$key `
     signoz/signoz-mcp-server:latest
   ```

> Version note: the running SigNoz is v0.99.0. The MCP server's newer
> query-API tools (raw trace/log search, metrics) return 500 against it, so
> those are not exposed; the working SigNoz-native tools above are, and the
> Flight Recorder local tools cover incident/trace retrieval reliably.

## Run

```bash
python -m assistant.mcp_assistant "find the latest failed incident, replay and investigate it, and summarise the root cause"
```
