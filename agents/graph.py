"""LangGraph StateGraph 编排。"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.coordinator import coordinator_node
from agents.data_analyst import data_analyst_node
from agents.decision import decision_node
from agents.nlp_insights import nlp_insights_node
from agents.state import AgentState
from agents.visualizer import visualizer_node
from agents.whatif_anomaly import whatif_anomaly_node


def _route_after_coordinator(state: AgentState) -> str:
    return "data_analyst"


def _route_after_data(state: AgentState) -> str:
    if state.get("need_nlp", False):
        return "nlp_insights"
    if state.get("need_visualization", True):
        return "visualizer"
    if state.get("need_decision", False):
        return "decision"
    return END


def _route_after_nlp(state: AgentState) -> str:
    if state.get("need_visualization", True):
        return "visualizer"
    if state.get("need_decision", False):
        return "decision"
    return END


def _route_after_visualizer(state: AgentState) -> str:
    if state.get("need_whatif", False) or state.get("need_anomaly", False):
        return "whatif_anomaly"
    if state.get("need_decision", False):
        return "decision"
    return END


def _route_after_whatif_anomaly(state: AgentState) -> str:
    if state.get("need_decision", False):
        return "decision"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("data_analyst", data_analyst_node)
    graph.add_node("nlp_insights", nlp_insights_node)
    graph.add_node("visualizer", visualizer_node)
    graph.add_node("whatif_anomaly", whatif_anomaly_node)
    graph.add_node("decision", decision_node)

    graph.set_entry_point("coordinator")
    graph.add_conditional_edges(
        "coordinator",
        _route_after_coordinator,
        {"data_analyst": "data_analyst"},
    )
    graph.add_conditional_edges(
        "data_analyst",
        _route_after_data,
        {"nlp_insights": "nlp_insights", "visualizer": "visualizer", "decision": "decision", END: END},
    )
    graph.add_conditional_edges(
        "nlp_insights",
        _route_after_nlp,
        {"visualizer": "visualizer", "decision": "decision", END: END},
    )
    graph.add_conditional_edges(
        "visualizer",
        _route_after_visualizer,
        {"whatif_anomaly": "whatif_anomaly", "decision": "decision", END: END},
    )
    graph.add_conditional_edges(
        "whatif_anomaly",
        _route_after_whatif_anomaly,
        {"decision": "decision", END: END},
    )
    graph.add_edge("decision", END)

    return graph.compile()
