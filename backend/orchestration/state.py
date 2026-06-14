"""LangGraph 共享状态（Agent 间通过它传递中间结果）。"""
from __future__ import annotations

from typing import Any, TypedDict


class GState(TypedDict, total=False):
    messages: list[dict]            # ReAct 对话消息（含 tool_calls / tool 结果）
    question: str
    history: list[dict]
    provider: str | None
    model: str | None
    conversation_id: int
    charts: list[dict[str, Any]]        # 专家直接产出的图，预测/What-if/词云/诊断
    data_results: list[dict[str, Any]]  # 数据查询原始结果，供可视化 Agent 统一规划
    queries: list[dict[str, Any]]       # 本轮 SQL / 命中表 / 耗时
    anomalies: list[dict[str, Any]]
    answer: str
    steps: int
    pending: list[dict]             # 待执行的工具调用
    _route: str                     # 条件边路由信号：tools | end
