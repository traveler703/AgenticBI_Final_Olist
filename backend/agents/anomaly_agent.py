"""异常检测 Agent：通用序列扫描。

让 LLM 按问题生成 实体-时间-指标 序列，对每个实体做环比与 z-score 检测。
未指定目标或生成失败时，回退到内置的州级订单量与差评率扫描。
"""
from __future__ import annotations

import pandas as pd

from agents.common import gen_sql, run_logged

MOM_THRESHOLD = 0.35
Z_THRESHOLD = 2.5

STATE_ORDERS_SQL = "SELECT customer_state, `year_month` ym, total_orders FROM mv_state_sales ORDER BY customer_state, `year_month`"
STATE_NEG_SQL = ("SELECT customer_state, `year_month` ym, "
                 "SUM(negative_review_rate*review_count)/NULLIF(SUM(review_count),0) neg "
                 "FROM mv_review_quality GROUP BY customer_state, `year_month` ORDER BY customer_state, `year_month`")


def _scan_series(df):
    """df 形如 实体, 时间, 指标。对每个实体按时间排序，检测末期环比与离群。value 为环比幅度供画图。"""
    out, cols = [], list(df.columns)
    if len(cols) >= 3:
        ent, per, met = cols[0], cols[1], cols[2]
    else:
        per, met = cols[0], cols[1]
        df = df.assign(_all="全局"); ent = "_all"
    for name, part in df.groupby(ent):
        part = part.sort_values(per)
        vals = pd.to_numeric(part[met], errors="coerce").astype(float)
        if len(vals) < 3:
            continue
        scope = f"{name} {part[per].iloc[-1]}" if ent != "_all" else f"{part[per].iloc[-1]}"
        mom = vals.pct_change().iloc[-1]
        if pd.notna(mom) and abs(mom) >= MOM_THRESHOLD:
            out.append({"type": f"{met} 异动", "scope": scope, "detail": f"环比 {mom:+.1%}",
                        "value": round(float(mom) * 100, 1), "severity": "high" if abs(mom) >= 0.6 else "medium"})
        if len(vals) >= 5:
            z = (vals - vals.mean()) / (vals.std() or 1)
            if abs(z.iloc[-1]) >= Z_THRESHOLD:
                out.append({"type": f"{met} 离群", "scope": scope, "detail": f"z={z.iloc[-1]:.1f}",
                            "value": round(float(z.iloc[-1]), 1), "severity": "medium"})
    return out


def detect_anomalies(question="", *, provider=None, model=None, conversation_id=None, emit=lambda e: None):
    emit({"type": "status", "text": "异常检测：扫描序列…"})
    anomalies, queries = [], []
    if question:
        sql = gen_sql("为异常检测返回序列。列依次为 实体维度如 customer_state 或 payment_type 可省略、"
                      f"时间升序、数值指标。问题：{question}", provider, model)
        if sql:
            df, meta = run_logged(sql, question, conversation_id)
            if meta:
                queries.append(meta)
            if df is not None and len(df) >= 3 and df.shape[1] >= 2:
                anomalies = _scan_series(df)

    if not anomalies:  # 回退到内置两类扫描，同样走 run_logged 以便展示实际 SQL
        s, m1 = run_logged(STATE_ORDERS_SQL, "州级订单量异常扫描", conversation_id)
        rq, m2 = run_logged(STATE_NEG_SQL, "州级差评率异常扫描", conversation_id)
        queries += [m for m in (m1, m2) if m]
        if s is not None:
            anomalies += _scan_series(s.rename(columns={"customer_state": "e", "ym": "p", "total_orders": "订单量"}))
        if rq is not None:
            anomalies += _scan_series(rq.rename(columns={"customer_state": "e", "ym": "p", "neg": "差评率"}))

    anomalies = anomalies[:10]
    if not anomalies:
        return "未发现明显异常。阈值为环比 ±35% 或 |z|≥2.5。", {"anomalies": []}, queries
    text = "异常预警：" + "；".join(f"{a['scope']} {a['type']} {a['detail']}" for a in anomalies[:6]) + "。"
    from agents import reflection
    rn = reflection.note(question or "异常扫描", text, provider=provider, model=model, emit=emit)
    if rn:
        text += f"\n反思：{rn}"
    return text, {"anomalies": anomalies}, queries
