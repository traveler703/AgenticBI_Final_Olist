"""LangGraph StateGraph 装配。

ReAct 编排：agent 节点(LLM function-calling 决策) ↔ tools 节点(执行专家工具)，
条件边按是否产生工具调用路由；MemorySaver 作 checkpointer（按 conversation 持久化图状态）。
跨会话的持久记忆由 agentic_app.messages 承担，二者互补。
"""
from __future__ import annotations

import json
from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from orchestration import supervisor as S
from orchestration.state import GState
from llm.client import chat_messages

MAX_STEPS = 8


def _agent_node(state: GState, config) -> dict:
    emit = config["configurable"].get("emit", lambda e: None)
    msgs = state["messages"]
    steps = state.get("steps", 0)
    if steps == 0:
        emit({"type": "status", "text": "协调器规划中…"})
    if steps >= MAX_STEPS:
        m = chat_messages(msgs + [{"role": "user", "content": "请基于以上结果给出最终中文结论。"}],
                          provider=state.get("provider"), model=state.get("model"), temperature=0.2)
        return {"answer": m.content or "", "_route": "end"}

    msg = chat_messages(msgs, tools=S.TOOLS, provider=state.get("provider"), model=state.get("model"), temperature=0.1)
    if not msg.tool_calls:
        return {"messages": msgs + [{"role": "assistant", "content": msg.content or ""}],
                "answer": msg.content or "", "_route": "end"}
    asst = {"role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                           for tc in msg.tool_calls]}
    pending = [{"id": tc.id, "name": tc.function.name, "args": tc.function.arguments} for tc in msg.tool_calls]
    return {"messages": msgs + [asst], "pending": pending, "steps": steps + 1, "_route": "tools"}


def _tools_node(state: GState, config) -> dict:
    emit = config["configurable"].get("emit", lambda e: None)
    msgs = list(state["messages"])
    charts = list(state.get("charts", []))
    data_results = list(state.get("data_results", []))
    queries = list(state.get("queries", []))
    anomalies = list(state.get("anomalies", []))
    for p in state.get("pending", []):
        try:
            args = json.loads(p["args"] or "{}")
        except Exception:
            args = {}
        emit({"type": "status", "text": f"调用 {S.LABEL.get(p['name'], p['name'])} …"})
        obs = S.dispatch_tool(p["name"], args, question=state["question"], history=state.get("history", []),
                              charts=charts, data_results=data_results, queries=queries, anomalies=anomalies,
                              provider=state.get("provider"), model=state.get("model"),
                              conversation_id=state.get("conversation_id"), emit=emit)
        msgs.append({"role": "tool", "tool_call_id": p["id"], "content": str(obs)[:4000]})
    return {"messages": msgs, "charts": charts, "data_results": data_results,
            "queries": queries, "anomalies": anomalies, "pending": []}


def _route(state: GState) -> str:
    return END if state.get("_route") == "end" else "tools"


@lru_cache
def get_graph():
    g = StateGraph(GState)
    g.add_node("agent", _agent_node)
    g.add_node("tools", _tools_node)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", _route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=MemorySaver())
