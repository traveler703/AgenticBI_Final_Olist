"""协调器 Agent：意图识别、任务分解、汇总回答。"""
from __future__ import annotations

from agents.state import AgentState
from models.forecast import extract_forecast_weeks


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
    need_nlp = any(k in query for k in ("评价", "评论", "差评", "低分", "评分", "满意", "情感", "主题", "关键词"))
    need_advice = any(k in query for k in ("建议", "策略", "如何", "改进", "优化"))
    need_decision = need_forecast or need_whatif or need_anomaly or need_nlp or need_advice
    plan_steps = ["数据分析"]
    if need_nlp:
        plan_steps.append("评论文本洞察")
    plan_steps.append("可视化")
    if need_whatif or need_anomaly:
        plan_steps.append("What-if / 异常检测")
    if need_decision:
        plan_steps.append("决策建议")
    return {
        "analysis_type": analysis_type,
        "plan_steps": plan_steps,
        "need_visualization": True,
        "need_forecast": need_forecast,
        "forecast_weeks": extract_forecast_weeks(query) if need_forecast else 0,
        "need_nlp": need_nlp,
        "need_whatif": need_whatif,
        "need_anomaly": need_anomaly,
        "need_decision": need_decision,
    }
