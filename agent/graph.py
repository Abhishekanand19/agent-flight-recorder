"""LangGraph customer-support agent: standard ReAct loop
(agent node <-> tool node), capped by the recursion_limit set in main.py.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agent.llm import invoke_llm, make_llm
from agent.tools import check_order, issue_refund, search_kb

# Phrasing note: telling llama-3.3 about "tools" in the system prompt makes it
# emit raw <function=...> tags that Groq rejects (tool_use_failed). Keep this
# prompt about *behavior* only and let the tools param speak for itself.
SYSTEM_PROMPT = (
    "You are a customer support agent for Acme Gadgets. "
    "Before taking any action, look up the relevant policy in the knowledge "
    "base and follow it exactly. Verify an order before acting on it. "
    "If an action fails, explain to the customer what went wrong rather than "
    "attempting the same action again."
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph():
    tools = [search_kb, check_order, issue_refund]
    llm = make_llm(tools)

    def agent_node(state: AgentState) -> AgentState:
        messages = [SystemMessage(SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [invoke_llm(llm, messages)]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
