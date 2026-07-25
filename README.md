<!-- TODO: Replace this comment with the Hero Banner image, e.g. ![Agent Flight Recorder](docs/hero-banner.png) -->

<div align="center">

# ✈️ Agent Flight Recorder

### A flight recorder for AI agents — record the crash, replay the counterfactuals, name the root cause.

OpenTelemetry-native incident investigation for LLM agents, built for the **SigNoz AI Observability Hackathon**.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-instrumented-425CC7?logo=opentelemetry&logoColor=white)
![SigNoz](https://img.shields.io/badge/SigNoz-observability-E75A3B)
![License](https://img.shields.io/badge/License-MIT-3DA639)

**[🌐 Live Demo](https://agent-flight-recorder-pink.vercel.app/)** · **[▶️ Watch the Demo](https://www.youtube.com/watch?v=CaW0NiiKbjc)** · [Quick Start](#-quick-start) · [Architecture](#️-architecture)

</div>

---

## 🎬 Demo

<!-- TODO: Replace this comment with the product workflow GIF, e.g. ![Product demo](docs/demo.gif) -->

<div align="center">

[![Watch the demo](https://img.youtube.com/vi/CaW0NiiKbjc/maxresdefault.jpg)](https://www.youtube.com/watch?v=CaW0NiiKbjc)

▶️ **[Watch the 3-minute walkthrough on YouTube →](https://www.youtube.com/watch?v=CaW0NiiKbjc)**

</div>

---

## ❌ The Problem

Traditional observability answers one question: **"what failed?"** — a red span, a stack trace, a 500.

For AI agents, that is not enough. Agents fail **silently** and **non-reproducibly**: a support agent refuses a valid refund at 2 a.m., and "the span errored" tells you nothing about **why the model made a bad decision**, whether a different model or temperature would have avoided it, or what the minimal fix is.

> You can see the crash. You still can't explain it, reproduce it, or prove your fix works.

---

## ✅ The Solution

**Agent Flight Recorder** treats every agent run like an aircraft flight — everything is recorded, any incident can be **replayed under counterfactual conditions**, and an AI **investigator** reads the evidence and names the root cause. The investigator is itself on the recorder.

```mermaid
flowchart LR
    A["👤 Customer<br/>request"] --> B["🤖 AI Support<br/>Agent"]
    B --> C["❌ Agent calls a<br/>deprecated tool"]
    C --> D[("📡 SigNoz<br/>traces · logs · metrics")]
    D --> E["✈️ Flight Recorder<br/>detects incident"]
    E --> F["⚙️ Replay Engine<br/>reproduces failure"]
    F --> G["🔀 Counterfactual<br/>replay validates fix"]
    G --> H["🔍 AI Investigator<br/>finds root cause"]
    H --> I["🛠️ Engineer exports<br/>validated fix"]
```

---

## ✨ Key Features

| | Feature | What it does |
|---|---|---|
| 📡 | **Full OTel Recording** | Every LLM call and tool call is its own span with `llm.model`, `llm.tokens`, `tool.name`; structured logs correlate to traces in SigNoz. |
| ⚙️ | **Counterfactual Replay** | Pulls a failed trace from SigNoz and re-runs it across models × temperatures × a structural fix — 4 fail, 1 passes. |
| 🔀 | **Delta Impact** | Quantifies the validated fix: latency, token, execution-time and cost savings vs. the original failure. |
| 🔍 | **AI Crash Investigator** | One Gemini call reads the structured diff and returns a root cause + evidence scorecard. It is **itself traced** (`service.name=crash-investigator`). |
| 🧠 | **Incident Knowledge Base** | Learns from every investigation and surfaces similar past incidents automatically. |
| ⚡ | **One-Click Simulate Crash** | Reproduces the full lifecycle — crash → replay → investigation → validated fix — with no manual steps. |
| 🛠️ | **Engineer Action Center** | Exports a production-ready incident report (Markdown/PDF) and a pre-filled GitHub issue. |
| 🤖 | **SigNoz MCP + Gemini** | Natural-language incident assistant over the **official SigNoz MCP server** + the replay/investigator tools. |

---

## 🖥️ Product Preview

### Operations Center

![Operations Center dashboard](docs/screenshot-dashboard.png)

*Fleet view — live incident queue with real customer requests, replay cost broken down by model, top failing tools, replay success rate, and Mean Time To Root Cause.*

### Incident Investigation

![Incident investigation](docs/screenshot-investigation.png)

*One incident end-to-end — request/service/model/tool context, a 5-run counterfactual matrix (each failing for a distinct technical reason), delta impact, and an evidence-backed root-cause verdict with a confidence scorecard.*

### SigNoz — traces, logs & metrics

<!-- TODO: add docs/screenshot-signoz.png (SigNoz UI at http://localhost:8080 requires your admin login to capture) -->

*The agent, replay engine and investigator all emit OpenTelemetry spans and structured logs into SigNoz. A provisioned dashboard tracks token cost per step, agent failure rate, the replay success matrix, and investigator confidence over time.*

---

## 🏗️ Architecture

```mermaid
flowchart TB
    subgraph AGENT["🤖 Instrumented Agent"]
        LG["LangGraph support agent<br/>Groq · Llama 3.3 70B"]
    end
    subgraph OBS["📡 Observability (SigNoz)"]
        OT["OpenTelemetry SDK<br/>OTLP :4317"]
        CH[("ClickHouse<br/>traces · logs · metrics")]
    end
    subgraph FR["✈️ Flight Recorder"]
        RE["⚙️ Replay Engine<br/>counterfactuals + fix"]
        CI["🔍 Crash Investigator<br/>Gemini 2.5 · meta-traced"]
        KB["🧠 Incident Knowledge Base"]
    end
    subgraph WEB["🖥️ Web"]
        API["FastAPI backend"]
        RUI["React Operations Center"]
    end
    MCP["🤖 SigNoz MCP + Gemini assistant"]

    LG -->|OTLP spans + logs| OT --> CH
    CH -->|pull failed trace| RE -->|linked replay traces| CH
    RE --> CI -->|investigation spans| CH
    CI --> KB
    CH -->|zero-auth query| API --> RUI
    MCP -->|official MCP tools| CH
    MCP --> API
```

Everything links back: replay traces carry `replay.of=<original>`, investigations carry `investigation.of` — isolated traces become one incident narrative.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| **Agent** | LangGraph · LangChain · Groq (Llama 3.3 70B) |
| **Investigator** | Google Gemini 2.5 Flash |
| **Observability** | OpenTelemetry SDK · **SigNoz** (self-hosted) · ClickHouse |
| **Backend** | FastAPI · Uvicorn · Python 3.12 |
| **Frontend** | React 18 · Vite |
| **AI Assistant** | Official SigNoz MCP Server · MCP Python SDK · google-genai |
| **Deployment** | Railway (backend) · Vercel (frontend) |

---

## 🚀 Quick Start

> Windows PowerShell shown; chain commands with `;` (not `&&`).

```bash
# 1. Start self-hosted SigNoz (first visit http://localhost:8080 creates the admin account)
docker compose -f signoz/docker-compose.yaml up -d

# 2. Python env + secrets
python -m venv .venv ; .venv/Scripts/pip install -r requirements.txt
cp .env.example .env        # add GROQ_API_KEY, GEMINI_API_KEY, SIGNOZ_API_KEY

# 3. Record an incident (deterministic failure — prints a trace id)
python -m agent.main

# 4. Replay it under counterfactual configs
python -m replay.engine --trace-id <id>

# 5. Investigate the crash
python -m investigator.investigate --trace-id <id>

# 6. Web app
python -m uvicorn api.main:app --port 8000      # terminal A
cd ui ; npm install ; npm run dev               # terminal B → http://localhost:5173

# 7. Provision SigNoz dashboard + alert
python -m scripts.provision_signoz
```

**Judging online?** The deployed app runs in **Demo Mode** (`DEMO_MODE=1`) — it serves real captured incidents, so a clean Operations Center comes alive on the first **⚡ Simulate Crash** click, no local stack required.

---

## 📁 Project Structure

```
agent-flight-recorder/
├── agent/           # OTel-instrumented LangGraph support agent + stale-KB failure
├── replay/          # Counterfactual replay engine + zero-auth ClickHouse access
├── investigator/    # Crash investigator (meta-observed) + incident knowledge base
├── api/             # FastAPI backend (+ Demo Mode for the cloud)
├── assistant/       # Gemini + SigNoz MCP natural-language incident assistant
├── ui/              # React Operations Center (Vite)
├── signoz/          # Self-hosted SigNoz stack + dashboard/alert as code
├── scripts/         # Provisioning, demo-data capture, failure storm
└── demo_data/       # Captured incidents served in Demo Mode
```

---

## 📡 How SigNoz Powers the Project

SigNoz is the flight recorder's black box — every signal flows through it.

| Signal | Role in Agent Flight Recorder |
|---|---|
| **Traces** | Every LLM call and tool call is a span (`llm.model`, `llm.temperature`, `llm.tokens`, `tool.name`). Replays link back via `replay.of`; the investigator is traced under `crash-investigator`. |
| **Logs** | Structured, trace-correlated backend events ("Received support request", "Calling refund_api_v1", "issue_refund failed — refund API deprecated") — click a log, jump to its trace. |
| **Metrics** | A provisioned dashboard tracks token cost per step, agent failure rate, the replay success matrix, and investigator confidence over time. |
| **Exceptions** | Tool failures are captured as span errors with `exception.type` / `exception.message` and an alert on the refund failure-rate spike. |

The AI assistant reaches SigNoz through the **official SigNoz MCP server**, so Gemini can query services, dashboards and docs in natural language.

---

## 👥 Contributors & License

| | |
|---|---|
| **Author** | Abhishek Anand ([@Abhishekanand19](https://github.com/Abhishekanand19)) |
| **Repository** | [github.com/Abhishekanand19/agent-flight-recorder](https://github.com/Abhishekanand19/agent-flight-recorder) |
| **License** | [MIT](LICENSE) |

<div align="center">

*Traditional observability ends at the alert. **Agent Flight Recorder starts there.***

</div>
