"""决策智能 Agent：规范性分析与商业建议。"""
from __future__ import annotations

from agents.state import AgentState
from models.forecast import extract_forecast_weeks, forecast_next_weeks
from utils.llm import deepseek_chat


def _fallback_advice(state: AgentState) -> str:
    actions = [
        "1. 物流：按州监控准时率与平均配送时长，对延迟率最高区域设置周度整改目标，并优先替换高延迟线路。",
        "2. 卖家：对低评分、高差评且高延迟卖家实施分级治理；先限流整改，再根据 What-if 结果决定下架。",
        "3. 商品与客户：围绕负向评论高频主题优化质检、包装和售后话术，并按月复盘差评率与复购影响。",
    ]
    if (state.get("forecast_result") or {}).get("rows", 0) > 0:
        weeks = (state.get("forecast_result") or {}).get("forecast_weeks", 6)
        actions.append(f"4. 资源配置：根据未来 {weeks} 周销售预测的上下界制定库存和履约容量的基准、保守与高峰方案。")
    return "\n".join(actions)


def _generate_advice(state: AgentState) -> tuple[str, str]:
    system = (
        "你是 Olist 电商平台的决策智能顾问。请根据提供的分析证据输出具体、可执行、可衡量的运营建议。"
        "必须分为物流、卖家、商品/客户三个部分；每部分包含目标对象、动作、指标和复盘周期。"
        "只可引用输入证据中明确出现的对象和数字，不要假设品类、卖家分层、客户分层、退货率或目标基线。"
        "不得把某个州或品类与具体问题原因直接关联，除非输入证据明确提供该原因；证据不足时应建议先诊断验证。"
        "证据不足时应提出建立监控或试点验证，不得编造具体事实。使用简体中文，控制在 350 字以内。"
    )
    user = "\n".join(
        [
            f"用户问题：{state.get('user_query', '')}",
            f"分析类型：{state.get('analysis_type', '')}",
            f"数据摘要：{state.get('data_summary', '')}",
            f"评论洞察：{state.get('nlp_insights', '')}",
            f"预测结果：{state.get('forecast_result', '')}",
            f"What-if：{state.get('whatif_insights', '')}",
            f"异常检测：{state.get('anomaly_insights', '')}",
        ]
    )
    try:
        advice = deepseek_chat(system, user, temperature=0.1).strip()
        return (advice, "LLM") if advice else (_fallback_advice(state), "规则兜底")
    except Exception:
        return _fallback_advice(state), "规则兜底"


def decision_node(state: AgentState) -> AgentState:
    if not state.get("need_decision", False):
        return {}

    query = state.get("user_query", "")
    need_forecast = any(k in query for k in ("预测", "未来6周", "未来"))
    forecast_weeks = state.get("forecast_weeks") or extract_forecast_weeks(query)
    need_advice = state.get("need_decision", False)

    forecast_text = ""
    forecast_rows = 0
    if need_forecast:
        forecast_df = forecast_next_weeks(forecast_weeks)
        forecast_rows = len(forecast_df)
        if not forecast_df.empty:
            total = float(forecast_df["yhat"].sum())
            total_lower = float(forecast_df["yhat_lower"].sum())
            total_upper = float(forecast_df["yhat_upper"].sum())
            weekly_min = float(forecast_df["yhat"].min())
            weekly_max = float(forecast_df["yhat"].max())
            trend_description = str(forecast_df.attrs.get("trend_description", "短期趋势"))
            change_rate = float(forecast_df.attrs.get("forecast_change_rate", 0.0))
            forecast_text = (
                f"模型预测未来{forecast_weeks}周 GMV 合计约 {total:,.0f}，"
                f"合计区间约 {total_lower:,.0f}~{total_upper:,.0f}；"
                f"单周预测约 {weekly_min:,.0f}~{weekly_max:,.0f}。"
                f"点预测显示{trend_description}（首周至末周变化 {change_rate:+.1%}），"
                "实际波动风险主要由预测区间表达。"
            )
        else:
            forecast_text = "无可用预测结果。"

    whatif_text = state.get("whatif_insights", "")
    anomaly_text = state.get("anomaly_insights", "")

    forecast_result = {"rows": forecast_rows, "forecast_weeks": forecast_weeks}
    if need_forecast and forecast_rows:
        forecast_result.update(
            {
                "forecast_total": total,
                "forecast_lower": total_lower,
                "forecast_upper": total_upper,
                "weekly_min": weekly_min,
                "weekly_max": weekly_max,
                "trend_description": trend_description,
                "forecast_change_rate": change_rate,
            }
        )
    advice, advice_source = (
        _generate_advice({**state, "forecast_result": forecast_result}) if need_advice else ("", "")
    )
    provenance_text = ""
    if need_forecast:
        provenance_text = (
            f"生成说明：预测数值与区间由时间序列模型计算；运营建议由{advice_source}基于模型结果生成。"
        )
    final = "\n".join(
        part
        for part in [
            state.get("data_summary", ""),
            forecast_text,
            provenance_text,
            state.get("nlp_insights", ""),
            whatif_text,
            anomaly_text,
            f"建议：{advice}" if advice else "",
        ]
        if part
    )
    return {
        "final_answer": final,
        "forecast_result": forecast_result,
        "decision_advice": advice,
        "advice_source": advice_source,
    }
