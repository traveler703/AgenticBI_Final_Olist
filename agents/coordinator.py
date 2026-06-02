"""协调器 Agent：意图识别、任务分解、汇总回答。"""
from __future__ import annotations

from agents.state import AgentState


def _analysis_type(query: str) -> str:
    if any(k in query for k in ("what-if", "what if", "模拟", "如果", "下架")):
        return "prescriptive"
    if any(k in query for k in ("异常", "预警", "骤降", "突升")):
        return "diagnostic"
    if any(k in query for k in ("预测", "未来", "下周", "趋势")):
        return "predictive"
    if any(k in query for k in ("为什么", "原因", "诊断", "异常")):
        return "diagnostic"
    if any(k in query for k in ("建议", "策略", "如何", "优化", "改进")):
        return "prescriptive"
    return "descriptive"


def coordinator_node(state: AgentState) -> AgentState:
    query = state.get("user_query", "").strip()
    analysis_type = _analysis_type(query)
    need_forecast = any(k in query for k in ("预测", "未来6周", "未来"))
    need_whatif = any(k in query for k in ("what-if", "what if", "模拟", "如果", "下架"))
    need_anomaly = any(k in query for k in ("异常", "预警", "骤降", "突升", "扫描"))
    need_senti = any(k in query for k in ("评价", "差评", "低分", "评分", "满意", "风险品类"))
    need_advice = any(k in query for k in ("建议", "策略", "如何", "改进", "优化"))
    need_decision = need_forecast or need_whatif or need_anomaly or need_senti or need_advice
    return {
        "analysis_type": analysis_type,
        "need_visualization": True,
        "need_forecast": need_forecast,
        "need_whatif": need_whatif,
        "need_anomaly": need_anomaly,
        "need_decision": need_decision,
    }
