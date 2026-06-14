"""预测 Agent：通用时间序列预测。

让 LLM 按问题生成一条时间序列查询，对任意指标与分段做对数尺度阻尼趋势预测，
给出点预测与置信区间。生成失败时回退到周度 GMV 序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from agents.common import gen_sql, run_logged
from models.forecaster import extract_forecast_weeks, fit_forecast, load_weekly_sales_history


def forecast_sales(question="", weeks=None, *, provider=None, model=None, conversation_id=None, emit=lambda e: None):
    periods = weeks or extract_forecast_weeks(question or "")
    emit({"type": "status", "text": "预测：构建时间序列…"})
    label, hx, hy, queries = "目标指标", None, None, []

    sql = gen_sql(
        "为下面的预测目标返回一条时间序列。两列：第1列时间，year_month 或 week_start，升序；"
        f"第2列数值指标。只取一个指标、一个序列。目标：{question}", provider, model)
    if sql:
        df, meta = run_logged(sql, question, conversation_id)
        if meta:
            queries.append(meta)
        if df is not None and len(df) >= 8 and df.shape[1] >= 2:
            df = df.dropna()
            hx = [str(v) for v in df.iloc[:, 0]]
            hy = [float(v) for v in pd.to_numeric(df.iloc[:, 1], errors="coerce").fillna(0)]
            label = str(df.columns[1])

    if hy is None:  # 回退到周度 GMV 序列
        hist, _ = load_weekly_sales_history()
        hx = [d.strftime("%Y-%m-%d") for d in hist["week_start"]]
        hy = [float(v) for v in hist["total_gmv"]]
        label = "周度 GMV"

    # 裁掉尾部不完整周期，值远低于中位数的边界月或周会把趋势拉崩
    arr = np.array([v for v in hy if v > 0], dtype=float)
    if len(arr) >= 8:
        thr = max(1.0, float(np.median(arr)) * 0.2)
        while len(hy) >= 10 and hy[-1] < thr:
            hy.pop(); hx.pop()

    fit = fit_forecast(hy, periods)
    if not fit:
        return "历史序列过短，无法预测。", {}, queries
    yhat, lo, hi = fit
    fx = [f"未来{i+1}" for i in range(periods)]
    total = sum(yhat)
    change = (yhat[-1] / yhat[0] - 1) if yhat[0] else 0.0
    trend = "基本稳定" if abs(change) < 0.03 else ("上行" if change > 0 else "下行")
    text = (f"对 {label} 预测未来 {periods} 期：合计约 {total:,.0f}，区间 {sum(lo):,.0f}~{sum(hi):,.0f}；"
            f"趋势{trend}，首末期变化 {change:+.1%}。基于 {len(hy)} 期历史。")
    from agents import reflection
    r = reflection.note(question, text, provider=provider, model=model, emit=emit)
    if r:
        text += f"\n反思：{r}"
    payload = {"label": label, "hx": hx[-26:], "hy": [round(v, 2) for v in hy[-26:]],
               "fx": fx, "yhat": yhat, "lo": lo, "hi": hi}
    return text, payload, queries
