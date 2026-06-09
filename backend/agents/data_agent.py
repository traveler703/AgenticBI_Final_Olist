"""数据分析 Agent：Plan-and-Execute 加 Reflect 与 Replan。"""
from __future__ import annotations

import json
from pathlib import Path
import re

from core.sql_guard import SqlGuardError
from datastore import app_db
from datastore.data_dictionary import MATERIALIZED_VIEWS
from datastore.olist_db import run_agent_sql
from datastore.schema_hint import build_schema_hint
from llm.client import chat, chat_messages

VIEW_NAMES = list(MATERIALIZED_VIEWS.keys())
MAX_STEPS = 6

TOOLS = [
    {"type": "function", "function": {
        "name": "list_views",
        "description": "列出所有可用的预聚合视图(mv_*)及其粒度、字段、适用场景。优先用视图。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "describe_view",
        "description": "查看某个视图或基础表的字段与粒度。",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": "执行一条只读 MySQL SELECT 并返回结果。优先 FROM mv_* 预聚合视图；视图无法覆盖再 JOIN 基础表。year_month 需写成 `year_month`。",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
    }},
]

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"

DATA_ANALYSIS_AGENT_PROMPT = (
    PROMPT_DIR / "data_analysis_agent_system_prompt.txt"
).read_text(encoding="utf-8")

SYSTEM = (
    DATA_ANALYSIS_AGENT_PROMPT
    + "\n\n# 数据字典\n"
    + build_schema_hint()
)

def _detect_route(sql: str):
    low = sql.lower()
    hit = [v for v in VIEW_NAMES if re.search(rf"\b{v}\b", low)]
    if hit:
        return "MV", hit[0]
    return "BASE", None


def _exec_sql(sql, question, conversation_id, emit):
    import time
    try:
        t = time.perf_counter()
        df, safe = run_agent_sql(sql)
        ms = int((time.perf_counter() - t) * 1000)
    except SqlGuardError as e:
        emit({"type": "status", "text": "SQL 被安全校验拒绝，重写中…"})
        return {"ok": False, "error": f"SQL 安全校验失败：{e}"}, None
    except Exception as e:
        emit({"type": "status", "text": "SQL 执行报错，自我修正中…"})
        return {"ok": False, "error": f"执行失败：{str(e)[:300]}"}, None
    route, view = _detect_route(safe)
    app_db.log_query_route(conversation_id, question, route, view, safe, ms)
    emit({"type": "status", "text": (f"命中视图 {view} ({ms}ms)" if route == "MV" else f"查基础表 ({ms}ms)")})
    rows = json.loads(df.head(40).to_json(orient="records", date_format="iso", force_ascii=False))
    result = {"question": question, "sql": safe, "source": view or "base", "route": route,
              "matched_view": view, "elapsed_ms": ms, "row_count": int(len(df)),
              "rows": json.loads(df.head(300).to_json(orient="records", date_format="iso", force_ascii=False)),
              "columns": list(df.columns)}
    obs = {"ok": True, "row_count": int(len(df)), "columns": list(df.columns), "rows": rows}
    return obs, result


def _act_loop(messages, *, provider, model, conversation_id, emit, results, routes, sqls, max_steps):
    """ReAct 行动循环：推理 → 调用工具 → 观察结果，反复直至模型不再调用工具。"""
    answer = ""
    for _ in range(max_steps):
        msg = chat_messages(messages, tools=TOOLS, provider=provider, model=model, temperature=0.0)
        if not msg.tool_calls:
            answer = msg.content or ""
            break
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                        for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            if name == "list_views":
                obs = build_schema_hint()
            elif name == "describe_view":
                v = MATERIALIZED_VIEWS.get(args.get("name", ""))
                obs = json.dumps(v, ensure_ascii=False) if v else "未找到该视图，请用 list_views 查看。"
            elif name == "run_sql":
                emit({"type": "status", "text": "执行 SQL 查询…"})
                obs_obj, result = _exec_sql(args.get("sql", ""), question_of(messages), conversation_id, emit)
                if result:
                    results.append(result)
                    routes.append({"route": result["route"], "matched_view": result["matched_view"],
                                   "elapsed_ms": result["elapsed_ms"], "question": question_of(messages)})
                    sqls.append(result["sql"])
                obs = json.dumps(obs_obj, ensure_ascii=False)[:4000]
            else:
                obs = "未知工具。"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})
    return answer


def question_of(messages):
    for m in messages:
        if m["role"] == "user":
            return m["content"]
    return ""


def _select_final(question, answer, results, *, provider, model, emit):
    """从所有查询结果中甄别最终结论真正依据的那几条，剔除探索与被修正取代的中间查询。

    审计日志已记录全部查询，这里只决定哪些结果交给下游展示与画图，避免中间结果产生无关图表。
    """
    if len(results) <= 1:
        return results
    emit({"type": "status", "text": "甄别最终依据的查询…"})
    desc = [{"i": i, "sql": " ".join(r["sql"].split())[:160], "rows": r["row_count"], "cols": r["columns"]}
            for i, r in enumerate(results)]
    system = ("下面是为回答问题而执行的多次查询，其中含探索性的、被后续修正取代的、或重复的中间查询。"
              "只挑出最终结论真正依据的查询编号，剔除中间、重复、被取代的查询。"
              "同一分析角度若有多个版本，只保留数据最完整的一条；只有真正不同的子问题才返回多条。"
              "通常返回 1 到 3 个编号。只输出 JSON 整数数组。")
    user = f"用户问题：{question}\n最终结论：{answer[:500]}\n查询列表：{json.dumps(desc, ensure_ascii=False)}"
    try:
        raw = chat(system, user, provider=provider, model=model, temperature=0.0)
        idxs = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
        chosen = [results[i] for i in idxs if isinstance(i, int) and 0 <= i < len(results)]
        return chosen or results
    except Exception:
        return results


MAX_REPLAN = 2


def _evidence(results):
    """给反思与重规划的证据：行数、各列不同值数、以及前几行样例。

    样例行让反思与重规划看到结果实际长什么样，判断是否答到点上、下一步该查什么。
    """
    parts = []
    for r in results:
        rows = r.get("rows") or []
        card = {c: len({str(row.get(c)) for row in rows}) for c in r["columns"]}
        sample = json.dumps(rows[:3], ensure_ascii=False)[:280]
        parts.append(f"{r['question']}→{r['row_count']}行；各列不同值数 {card}；样例 {sample}")
    return "; ".join(parts)


def _execute_plan(question, plan, *, provider, model, conversation_id, emit, results, routes, sqls):
    """执行器：在计划指导下用 ReAct 写并执行 SQL，优先一条组合 SQL 完成。"""
    plan_text = json.dumps(plan, ensure_ascii=False)
    sys = SYSTEM + (f"\n\n本次执行计划，务必遵守其口径与步骤，优先用一条组合 SQL，CTE 或窗口函数 完成：\n{plan_text}")
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": question}]
    answer = _act_loop(messages, provider=provider, model=model, conversation_id=conversation_id,
                       emit=emit, results=results, routes=routes, sqls=sqls, max_steps=MAX_STEPS)
    if not answer:
        msg = chat_messages(messages + [{"role": "user", "content": "请基于以上查询结果直接给出中文数据结论。"}],
                            provider=provider, model=model, temperature=0.0)
        answer = msg.content or "未能得出结论。"
    return answer


def run(question, *, provider, model, conversation_id, emit):
    from agents import planner, reflection

    plan = planner.make_data_plan(question, provider=provider, model=model, emit=emit)
    emit({"type": "status", "text": f"计划：{plan.get('interpretation', '')[:38]}"})
    results, routes, sqls = [], [], []
    answer = ""

    # Plan → Execute → Reflect → Replan 闭环
    for rnd in range(MAX_REPLAN + 1):
        answer = _execute_plan(question, plan, provider=provider, model=model, conversation_id=conversation_id,
                               emit=emit, results=results, routes=routes, sqls=sqls)
        if not results:
            break
        evidence = _evidence(results)
        verdict = reflection.reflect(question, answer, evidence, provider=provider, model=model, emit=emit)
        if verdict["ok"]:
            break
        if rnd < MAX_REPLAN:
            emit({"type": "status", "text": f"反思发现问题，重规划：{verdict['issue'][:26]}"})
            plan = planner.replan_data(question, plan, verdict["issue"], evidence, provider=provider, model=model, emit=emit)

    # 数据 Agent 在源头甄别最终依据的结果，下游只用这些干净结果
    final_results = _select_final(question, answer, results, provider=provider, model=model, emit=emit)
    final_sqls = [r["sql"] for r in final_results]
    final_routes = [{"route": r["route"], "matched_view": r["matched_view"],
                     "elapsed_ms": r["elapsed_ms"], "question": r["question"]} for r in final_results]
    return {"summary": answer, "results": final_results, "routes": final_routes, "sqls": final_sqls}
