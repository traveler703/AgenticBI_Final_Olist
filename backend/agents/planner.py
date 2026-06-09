"""数据分析层的规划器，用于 Plan-and-Execute。

make_data_plan 把数据问题拆成显式 SQL 执行计划并写明关键口径，趋势类要求保留逐期时间序列；
反思发现计划有误时由 replan_data 修订，使组合型问题的规划更稳定、可复现。
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from datastore.schema_hint import build_schema_hint
from llm.client import chat

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"
_PLAN_RULES = PLANNER_RULES = (
    PROMPT_DIR / "planner_rules_prompt.txt"
).read_text(encoding="utf-8")


def _parse(raw):
    obj = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    return obj if isinstance(obj.get("steps"), list) and obj["steps"] else None


def make_data_plan(question, *, provider=None, model=None, emit=lambda e: None):
    emit({"type": "status", "text": "规划：分解任务并明确口径…"})
    system = ("你是 Olist BI 的数据分析规划器。" + _PLAN_RULES + "\n数据字典：\n" + build_schema_hint() +
              '\n只输出 JSON：{"interpretation":"口径与解读一句话","steps":[{"id":1,"goal":"该步要得到什么、如何查","kind":"sql"}]}')
    try:
        plan = _parse(chat(system, f"用户问题：{question}", provider=provider, model=model, temperature=0.1))
        if plan:
            return plan
    except Exception:
        pass
    return {"interpretation": "直接查询回答", "steps": [{"id": 1, "goal": question, "kind": "sql"}]}

def replan_data(question, plan, issue, evidence, *, provider=None, model=None, emit=lambda e: None):
    emit({"type": "status", "text": "重规划：根据反思修订计划…"})
    system = ("你是 Olist BI 的数据分析规划器。原计划执行后被反思发现问题，请据此修订计划使其能正确完整回答问题。"
              + _PLAN_RULES + '\n只输出 JSON 计划，结构同 {"interpretation":...,"steps":[...]}。')
    user = (f"用户问题：{question}\n原计划：{json.dumps(plan, ensure_ascii=False)}\n"
            f"反思发现的问题：{issue}\n已得到的证据：{evidence}")
    try:
        p = _parse(chat(system, user, provider=provider, model=model, temperature=0.1))
        if p:
            return p
    except Exception:
        pass
    return plan


