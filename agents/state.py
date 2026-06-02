"""LangGraph 共享状态。"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_query: str
    resolved_query: str
    context_note: str
    plan_steps: list[str]
    analysis_type: str  # descriptive | diagnostic | predictive | prescriptive
    sql_queries: list[str]
    data_summary: str
    query_strategy: str
    chart_paths: list[str]
    forecast_result: dict[str, Any]
    nlp_insights: str
    whatif_insights: str
    anomaly_insights: str
    final_answer: str
    data_rows: list[dict[str, Any]]
    data_columns: list[str]
    data_results: list[dict[str, Any]]
    data_row_count: int
    need_visualization: bool
    need_forecast: bool
    need_decision: bool
    need_whatif: bool
    need_anomaly: bool
