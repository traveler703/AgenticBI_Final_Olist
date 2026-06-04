"""评论洞察 Agent：分析评论正文的情感极性、主观性与主题关键词。"""
from __future__ import annotations

from agents.state import AgentState
from models.sentiment import analyze_review_texts


def nlp_insights_node(state: AgentState) -> AgentState:
    if not state.get("need_nlp", False):
        return {}

    result = analyze_review_texts(limit=3000)
    if not result.get("comment_count"):
        return {
            "nlp_insights": "评论文本洞察：没有可分析的评论正文。",
            "nlp_result": result,
        }

    positive = "、".join(item["term"] for item in result.get("positive_keywords", [])[:5]) or "暂无"
    negative = "、".join(item["term"] for item in result.get("negative_keywords", [])[:5]) or "暂无"
    insights = (
        f"评论文本洞察：分析 {result['comment_count']:,} 条评论正文，"
        f"正向文本占比 {result['positive_rate']:.1%}，负向文本占比 {result['negative_rate']:.1%}，"
        f"主观性均值 {result['avg_subjectivity']:.2f}。"
        f"正向高频主题：{positive}；负向高频主题：{negative}。"
    )
    return {"nlp_insights": insights, "nlp_result": result}
