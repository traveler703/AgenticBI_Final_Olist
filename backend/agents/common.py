"""专家 Agent 共享的 SQL 工具：让 LLM 按问题生成只读 SQL，并执行 + 写审计日志。"""
from __future__ import annotations

import re
import time

from datastore import app_db
from datastore.olist_db import run_agent_sql
from datastore.schema_hint import build_schema_hint
from llm.client import chat


def gen_sql(instruction, provider, model):
    """让 LLM 把分析意图转成一条只读 SELECT。失败返回 None。"""
    system = ("你是 Olist BI 的 SQL 生成器。只输出一条 MySQL 只读 SELECT，不要分号、不要解释、不要代码块。"
              "优先 FROM mv_* 预聚合视图。year_month 写成 `year_month`。\n数据字典：\n" + build_schema_hint())
    try:
        raw = chat(system, instruction, provider=provider, model=model, temperature=0.0)
    except Exception:
        return None
    m = re.search(r"(select|with)\b.+", raw, flags=re.I | re.S)
    return m.group(0).strip().rstrip(";") if m else None


def run_logged(sql, question, conversation_id):
    """经 sql_guard 执行只读 SQL，写一行 query_route_log。返回 (df, meta)，失败返回 (None, None)。"""
    try:
        t = time.perf_counter()
        df, safe = run_agent_sql(sql)
        ms = int((time.perf_counter() - t) * 1000)
    except Exception:
        return None, None
    view = next((v for v in re.findall(r"mv_\w+", safe.lower())), None)
    route = "MV" if view else "BASE"
    app_db.log_query_route(conversation_id, question, route, view, safe, ms)
    meta = {"sql": safe, "route": route, "matched_view": view, "elapsed_ms": ms, "question": question}
    return df, meta
