"""评论洞察 Agent：对评论正文做情感与高频词分析，输出词云数据。"""
from __future__ import annotations

import time

from datastore import app_db
from models.review_nlp import analyze_review_texts


def analyze_reviews(*, provider=None, model=None, conversation_id=None, emit=lambda e: None):
    emit({"type": "status", "text": "评论洞察：情感与主题…"})
    t = time.perf_counter()
    r = analyze_review_texts(limit=3000)
    ms = int((time.perf_counter() - t) * 1000)
    if not r.get("comment_count"):
        return "无可分析评论正文。", {}, []
    # 抽取评论正文也是一条真实查询，写审计并在面板透出，和其它专家一致
    queries = []
    if r.get("sql"):
        question = "抽取评论正文做情感与高频词"
        app_db.log_query_route(conversation_id, question, "BASE", None, r["sql"], ms)
        queries.append({"sql": r["sql"], "route": "BASE", "matched_view": None, "elapsed_ms": ms, "question": question})
    pos = "、".join(i["term"] for i in r.get("positive_keywords", [])[:5]) or "暂无"
    neg = "、".join(i["term"] for i in r.get("negative_keywords", [])[:5]) or "暂无"
    text = (f"分析 {r['comment_count']:,} 条评论：正向占比 {r['positive_rate']:.1%}，负向占比 {r['negative_rate']:.1%}。"
            f"正向高频词 {pos}；负向高频词 {neg}。")
    # 给词云按情感标色：正向、负向、主题词分别上不同颜色
    kw = ([{**k, "sentiment": "pos"} for k in r.get("positive_keywords", [])[:12]]
          + [{**k, "sentiment": "neg"} for k in r.get("negative_keywords", [])[:12]]
          + [{**k, "sentiment": "topic"} for k in r.get("topic_keywords", [])[:36]])
    return text, {"keywords": kw[:60]}, queries
