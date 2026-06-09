"""可视化 Agent。

拿到用户问题与本轮所有数据集，由它决定哪些数据值得画图、用什么图表类型、如何编码、起什么标题。
与问题无关、中间过程、单值或不适合可视化的数据集会被跳过。绘图工具按决策确定性渲染并校验，
专家图，预测、What-if、词云、诊断，由各专家直接产出，不在此规划。
"""
from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd

from llm.client import chat
from viz import charts

MAX_CHARTS = 4


PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"
SYSTEM = (
    PROMPT_DIR / "visualization_planner_prompt.txt"
).read_text(encoding="utf-8")


def _col_kind(s):
    if pd.api.types.is_numeric_dtype(s):
        return "number"
    if charts.is_time(s.name):
        return "time"
    return "category"


def _features(df):
    return [{"col": c, "kind": _col_kind(df[c]), "nunique": int(df[c].nunique()),
             "sample": [str(v) for v in df[c].dropna().head(3)]} for c in df.columns]


def _decide(question, datasets, provider, model):
    user = f"用户问题：{question}\n数据集：{json.dumps(datasets, ensure_ascii=False)}"
    raw = chat(SYSTEM, user, provider=provider, model=model, temperature=0.1)
    return json.loads(re.search(r"\[.*\]", raw, re.S).group(0))


def _fallback(frames):
    """LLM 不可用时的最小决策：时间列做折线，否则分类列做柱状。"""
    out = []
    for i, df in enumerate(frames):
        if df.empty or len(df) < 2:
            continue
        nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        cats = [c for c in df.columns if c not in nums]
        times = [c for c in df.columns if charts.is_time(c)]
        if not nums or not cats:
            continue
        if times:
            grp = [c for c in cats if c not in times]
            if grp:
                out.append({"i": i, "make_chart": True, "type": "grouped_line", "x": times[0], "y": nums[0], "series": grp[0], "title": "趋势"})
            else:
                out.append({"i": i, "make_chart": True, "type": "line", "x": times[0], "y": nums[0], "title": "趋势"})
        else:
            out.append({"i": i, "make_chart": True, "type": "bar", "x": cats[0], "y": nums[0], "title": "对比"})
    return out


def plan(question, data_results, *, provider=None, model=None, emit=lambda e: None):
    frames = [charts.frame(it) for it in data_results]
    datasets = []
    for i, df in enumerate(frames):
        if df.empty or len(df) < 2 or "review_comment_message" in df.columns:
            continue
        datasets.append({"i": i, "n_rows": int(len(df)), "columns": _features(df)})
    if not datasets:
        return []

    emit({"type": "status", "text": "可视化：选择图表与起名…"})
    try:
        decisions = _decide(question, datasets, provider, model)
    except Exception:
        decisions = _fallback(frames)

    out, seen = [], set()
    for d in decisions:
        if not d.get("make_chart"):
            continue
        i = d.get("i")
        if not isinstance(i, int) or i < 0 or i >= len(frames):
            continue
        title = (d.get("title") or "图表").strip()[:24]
        option = charts.build(d.get("type"), frames[i], d, title)
        if not option:
            continue
        spec = charts.make_spec(data_results[i], i + 1, d.get("type"), title, option)
        sig = charts.chart_signature(spec)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(spec)

    # 兜底：LLM 认为都不该画但确有可用数据时，对信息量最大的一个数据集启发式出图，避免空白
    if not out:
        best = max(range(len(frames)), key=lambda i: 0 if frames[i].empty else len(frames[i]) * len(frames[i].columns))
        for d in _fallback([frames[best]]):
            title = d.get("title") or "图表"
            option = charts.build(d.get("type"), frames[best], {**d, "i": best}, title)
            if option:
                out.append(charts.make_spec(data_results[best], best + 1, d["type"], title, option))
                break
    return out[:MAX_CHARTS]
