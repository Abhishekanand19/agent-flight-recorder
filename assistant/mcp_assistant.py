"""Natural-language incident assistant: Gemini + the official SigNoz MCP server.

Gemini is given two families of tools and orchestrates them to answer a
request in plain English:

  * SigNoz-native tools, served by the OFFICIAL SigNoz MCP server
    (signoz/signoz-mcp-server, HTTP on :8009) — list services, dashboards,
    search docs, discover fields. Only the subset that works against the
    running SigNoz version is exposed.
  * Flight Recorder tools (assistant/tools_local.py) — thin wrappers over the
    existing backend, replay engine, and investigator: find the latest failed
    incident, search traces, get incident detail, trigger replay, trigger
    investigation. No business logic is duplicated.

Usage: python -m assistant.mcp_assistant "find the latest failed incident,
       replay and investigate it, and summarise the root cause"
"""

import argparse
import asyncio
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from assistant import tools_local

MCP_URL = "http://localhost:8009/mcp"
MODEL = "gemini-2.5-flash"
MAX_TURNS = 12

# Official SigNoz MCP tools that work against this SigNoz version (probed).
MCP_TOOLS = {
    "signoz_list_services": ("List APM services with trace activity in SigNoz.", {}),
    "signoz_list_dashboards": ("List the SigNoz dashboards configured in this instance.", {}),
    "signoz_search_docs": ("Search the official SigNoz documentation.", {"query": "search text"}),
    "signoz_get_field_keys": ("Discover available field keys for a signal (traces or logs).",
                              {"signal": "one of: traces, logs"}),
}

# Flight Recorder local tools (reuse existing backend/engine/investigator).
LOCAL_TOOLS = {
    "latest_failed_incident": ("Find the newest failed support-agent incident (its trace id and error).", {}),
    "search_traces": ("List recent traces for a service from SigNoz.",
                      {"service": "service name, default support-agent", "limit": "max rows, default 5"}),
    "get_incident": ("Get full incident detail: replay matrix, divergence, investigation status.",
                     {"trace_id": "32-hex incident trace id"}),
    "trigger_replay": ("Replay an incident under the failing and fix configs via the replay engine.",
                       {"trace_id": "32-hex incident trace id"}),
    "trigger_investigation": ("Run the crash investigator on an incident and return the verdict.",
                              {"trace_id": "32-hex incident trace id"}),
}

SYSTEM = (
    "You are the Agent Flight Recorder incident assistant. You help an on-call "
    "engineer investigate AI-agent incidents by calling tools. SigNoz-native "
    "tools (signoz_*) come from the official SigNoz MCP server; Flight Recorder "
    "tools operate the replay engine and crash investigator. To investigate an "
    "incident: find the latest failed incident, trigger a replay, trigger an "
    "investigation, then summarise the root cause, the validated fix, and the "
    "confidence in clear plain English. Prefer trace ids returned by earlier "
    "tool calls. Be concise."
)


def _schema(params: dict) -> types.Schema:
    return types.Schema(
        type="OBJECT",
        properties={k: types.Schema(type="STRING", description=v) for k, v in params.items()},
        required=[k for k in params],
    )


def _declarations() -> list[types.FunctionDeclaration]:
    decls = []
    for name, (desc, params) in {**MCP_TOOLS, **LOCAL_TOOLS}.items():
        decls.append(types.FunctionDeclaration(name=name, description=desc, parameters=_schema(params)))
    return decls


async def _dispatch(session: ClientSession, name: str, args: dict) -> str:
    if name in tools_local.REGISTRY:
        return await asyncio.to_thread(lambda: tools_local.REGISTRY[name](**args))
    result = await session.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in result.content)
    return text[:4000]


async def run(prompt: str) -> None:
    load_dotenv()
    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(function_declarations=_declarations())],
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]

            for _ in range(MAX_TURNS):
                resp = await client.aio.models.generate_content(
                    model=MODEL, contents=contents, config=config
                )
                parts = resp.candidates[0].content.parts or []
                calls = [p.function_call for p in parts if p.function_call]
                if not calls:
                    print("\n" + (resp.text or "(no answer)"))
                    return
                contents.append(resp.candidates[0].content)
                responses = []
                for call in calls:
                    args = dict(call.args or {})
                    arg_str = ", ".join(f"{k}={v}" for k, v in args.items())
                    print(f"  → {call.name}({arg_str})")
                    try:
                        out = await _dispatch(session, call.name, args)
                    except Exception as exc:  # a failing tool shouldn't kill the loop
                        out = f"tool error: {exc}"
                    responses.append(types.Part.from_function_response(
                        name=call.name, response={"result": out}))
                contents.append(types.Content(role="user", parts=responses))
            print("\n(reached max turns without a final answer)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini + SigNoz MCP incident assistant.")
    parser.add_argument("prompt", nargs="*", help="natural-language request")
    args = parser.parse_args()
    prompt = " ".join(args.prompt) or "Find the latest failed incident, replay and investigate it, and summarise the root cause."
    print(f"assistant> {prompt}")
    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()
