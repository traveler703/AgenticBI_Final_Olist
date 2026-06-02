"""决策智能 Agent：规范性分析与商业建议。"""
from __future__ import annotations

from agents.state import AgentState
from models.forecast import forecast_next_6_periods
from models.sentiment import review_sentiment_proxy_top_categories


def decision_node(state: AgentState) -> AgentState:
    if not state.get("need_decision", False):
        return {}

    query = state.get("user_query", "")
    analysis_type = state.get("analysis_type", "")
    need_forecast = any(k in query for k in ("预测", "未来6周", "未来"))
    need_senti = any(k in query for k in ("评价", "差评", "低分", "评分", "满意", "风险品类"))
    need_advice = any(k in query for k in ("建议", "策略", "如何", "改进", "优化"))

    forecast_text = ""
    forecast_rows = 0
    if need_forecast:
        forecast_df = forecast_next_6_periods()
        forecast_rows = len(forecast_df)
        if not forecast_df.empty:
            last = forecast_df.iloc[-1]
            forecast_text = (
                f"未来6期末预计GMV约 {last['yhat']:.2f}（区间 {last['yhat_lower']:.2f}~{last['yhat_upper']:.2f}）。"
            )
        else:
            forecast_text = "无可用预测结果。"

    senti_text = ""
    if need_senti:
        senti_df = review_sentiment_proxy_top_categories(limit=5)
        if not senti_df.empty:
            top = senti_df.iloc[0]
            senti_text = (
                f"低分风险最高品类为 {top['product_category_english']}，低分占比 {top['low_score_rate']:.2%}。"
            )
        else:
            senti_text = "暂无评价洞察。"

    whatif_text = state.get("whatif_insights", "")
    anomaly_text = state.get("anomaly_insights", "")

    advice = ""
    if need_advice:
        advice = state.get("decision_advice", "")
    final = "\n".join(
        part
        for part in [
            state.get("data_summary", ""),
            forecast_text,
            senti_text,
            whatif_text,
            anomaly_text,
            f"建议：{advice}" if advice else "",
        ]
        if part
    )
    return {"final_answer": final, "forecast_result": {"rows": forecast_rows}}
