"""中心协调 Agent，ReAct 加 function-calling。

自主调用专家工具，包含数据分析子 Agent、预测、What-if、异常、诊断、评论、元对话，观察结果后迭代或综合作答。
"""
from __future__ import annotations

from pathlib import Path

from agents import (anomaly_agent, data_agent, diagnose_agent, forecast_agent,
                    meta_agent, review_agent, viz_agent, whatif_agent)
from orchestration import disclaimers
from viz import charts as viz

TOOLS = [
    {"type": "function", "function": {
        "name": "query_data",
        "description": "查询 Olist 真实数据回答业务问题，覆盖销售、州、品类、配送、支付、评分等。最常用，可多次调用回答多个子问题。",
        "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "要查询的具体数据问题"}}, "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "forecast_sales",
        "description": "对任意时间序列指标做未来预测并给置信区间。target 描述要预测什么，例如全平台周度GMV、SP州月度订单量。",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "weeks": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "simulate_whatif",
        "description": "通用 What-if 反事实模拟。hypothesis 用自然语言描述假设，例如下架Top20高差评卖家、运费降低10%、SP州订单翻倍。",
        "parameters": {"type": "object", "properties": {"hypothesis": {"type": "string"}}, "required": ["hypothesis"]}}},
    {"type": "function", "function": {
        "name": "detect_anomalies",
        "description": "异常检测。target 可选，描述扫描对象，例如各州订单量、各品类差评率。省略则扫描默认的州级订单量与差评率。",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "diagnose_delivery",
        "description": "诊断配送延迟根因。多表 JOIN 下钻卖家与客户地理距离、跨州发货比例与配送时长的关系。回答为什么某些州配送慢用它。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "analyze_reviews",
        "description": "评论文本情感与高频词分析，产出词云。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "conversation_assistant",
        "description": "回答与数据分析无关的消息，例如关于本次对话或历史的元问题、能力介绍、问候闲聊。",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
]

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"

SYSTEM = (PROMPT_DIR / "supervisor_system_prompt.txt").read_text(encoding="utf-8")

LABEL = {"query_data": "数据分析", "forecast_sales": "销售预测", "simulate_whatif": "What-if 模拟",
         "detect_anomalies": "异常检测", "diagnose_delivery": "配送诊断下钻",
         "analyze_reviews": "评论洞察", "conversation_assistant": "对话助手"}


def run(question, *, history, summary, provider, model, conversation_id, emit):
    """构建初始状态并交给 LangGraph 的 ReAct 编排执行，最后对答案做强制口径声明。"""
    from orchestration.graph import get_graph

    msgs = [{"role": "system", "content": SYSTEM}]
    if summary:
        msgs.append({"role": "system", "content": f"[长期记忆 会话摘要] {summary}"})
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": question})
    init = {"messages": msgs, "question": question, "history": history, "provider": provider,
            "model": model, "conversation_id": conversation_id,
            "charts": [], "data_results": [], "queries": [], "anomalies": [], "steps": 0, "pending": []}
    config = {"configurable": {"thread_id": str(conversation_id), "emit": emit}, "recursion_limit": 40}
    final = get_graph().invoke(init, config)

    # 可视化 Agent 统一规划数据图，再与专家图合并
    data_charts = viz_agent.plan(question, final.get("data_results", []), provider=provider, model=model, emit=emit)
    answer = disclaimers.enforce(question, final.get("answer") or "未能得出结论。")
    return {"answer": answer, "charts": final.get("charts", []) + data_charts,
            "queries": final.get("queries", []), "route_decisions": final.get("queries", []),
            "anomalies": final.get("anomalies", [])}


def dispatch_tool(name, args, *, question, history, charts, data_results, queries, anomalies,
                  provider, model, conversation_id, emit):
    if name == "query_data":
        res = data_agent.run(args.get("question") or question, provider=provider, model=model,
                             conversation_id=conversation_id, emit=emit)
        # 只收集原始结果，统一交给可视化 Agent 规划，避免每条查询都出图
        seen_sql = {q["sql"] for q in queries}
        for item in res["results"]:
            data_results.append(item)
            if item["sql"] not in seen_sql:  # 反思重试会产生相同 SQL，去重
                seen_sql.add(item["sql"])
                queries.append({"sql": item["sql"], "route": item["route"], "matched_view": item["matched_view"],
                                "elapsed_ms": item["elapsed_ms"], "question": item["question"]})
        return res["summary"] or "无数据结论。"
    if name == "forecast_sales":
        text, payload, q = forecast_agent.forecast_sales(args.get("target") or question, args.get("weeks"),
                                                         provider=provider, model=model, conversation_id=conversation_id, emit=emit)
        queries.extend(q)
        if payload:
            charts.append(viz.forecast_chart(payload))
        return text
    if name == "simulate_whatif":
        text, payload, q = whatif_agent.simulate_whatif(args.get("hypothesis") or question,
                                                        provider=provider, model=model, conversation_id=conversation_id, emit=emit)
        queries.extend(q)
        if payload:
            charts.append(viz.whatif_chart(payload))
        return text
    if name == "detect_anomalies":
        text, payload, q = anomaly_agent.detect_anomalies(args.get("target") or "",
                                                          provider=provider, model=model, conversation_id=conversation_id, emit=emit)
        queries.extend(q)
        anomalies.extend(payload.get("anomalies", []))
        ch = viz.anomaly_chart(payload.get("anomalies", []))
        if ch:
            charts.append(ch)
        return text
    if name == "diagnose_delivery":
        text, payload, q = diagnose_agent.diagnose_delivery(question, provider=provider, model=model,
                                                            conversation_id=conversation_id, emit=emit)
        queries.extend(q)
        ch = viz.diagnose_chart(payload)
        if ch:
            charts.append(ch)
        return text
    if name == "analyze_reviews":
        text, payload, q = review_agent.analyze_reviews(provider=provider, model=model,
                                                        conversation_id=conversation_id, emit=emit)
        queries.extend(q)
        if payload.get("keywords"):
            charts.append(viz.wordcloud_chart(payload["keywords"]))
        return text
    if name == "conversation_assistant":
        return meta_agent.run(args.get("question") or question, history, provider=provider, model=model)
    return "未知工具。"
