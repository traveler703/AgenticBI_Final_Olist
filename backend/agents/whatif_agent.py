"""What-if Agent：通用反事实模拟。

让 LLM 把用户假设拆成基线 SQL 与反事实 SQL，各返回同口径的单个标量指标，
执行后对比前后差异。失败时回退到下架 Top20 高差评卖家的默认场景。
"""
from __future__ import annotations

import json
import re

import pandas as pd

from agents.common import run_logged
from datastore.schema_hint import build_schema_hint
from llm.client import chat


FALLBACK_SQL = """WITH bad AS (
                    SELECT seller_id FROM mv_seller_review_risk WHERE total_orders>=20
                    ORDER BY avg_review_score ASC, negative_orders DESC LIMIT 20
                ),
                reviewed_orders AS (
                    SELECT order_id, AVG(review_score) review_score
                    FROM order_reviews
                    WHERE review_score IS NOT NULL
                    GROUP BY order_id
                ),
                warehouse_orders AS (
                    SELECT DISTINCT order_id FROM fact_order_items
                ),
                excluded_orders AS (
                    SELECT DISTINCT order_id FROM fact_order_items
                    WHERE seller_id IN (SELECT seller_id FROM bad)
                )
        SELECT (SELECT AVG(r.review_score)
                FROM reviewed_orders r JOIN warehouse_orders w ON r.order_id=w.order_id) cur,
               (SELECT AVG(r.review_score)
                FROM reviewed_orders r JOIN warehouse_orders w ON r.order_id=w.order_id
                WHERE r.order_id NOT IN (SELECT order_id FROM excluded_orders)) sim"""


def simulate_whatif(hypothesis="", *, provider=None, model=None, conversation_id=None, emit=lambda e: None):
    emit({"type": "status", "text": "What-if：构造反事实…"})
    queries = []
    if hypothesis:
        system = ("你是 Olist BI 的反事实模拟器。把用户假设转成两条 MySQL 只读 SELECT。"
                  "baseline_sql 算现状，scenario_sql 算假设成立后，二者各返回同一口径的单行单列数值。"
                  '只输出 JSON：{"metric":"指标名","baseline_sql":"SELECT ...","scenario_sql":"SELECT ..."}。'
                  "优先 mv_*。year_month 写成 `year_month`。\n数据字典：\n" + build_schema_hint())
        try:
            raw = chat(system, hypothesis, provider=provider, model=model, temperature=0.0)
            obj = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            b, mb = run_logged(obj["baseline_sql"], hypothesis, conversation_id)
            s, ms = run_logged(obj["scenario_sql"], hypothesis, conversation_id)
            queries += [m for m in (mb, ms) if m]
            if b is not None and s is not None and b.size and s.size:
                cur = float(pd.to_numeric(b.iloc[:, 0], errors="coerce").iloc[0])
                sim = float(pd.to_numeric(s.iloc[:, 0], errors="coerce").iloc[0])
                metric = obj.get("metric", "指标")
                delta = sim - cur
                pct = (delta / cur) if cur else 0.0
                text = (f"What-if 假设「{hypothesis}」：{metric} 由 {cur:,.2f} 变为 {sim:,.2f}，"
                        f"变化 {delta:+,.2f}，{pct:+.2%}。口径为只读反事实估算，非实际结果。")
                from agents import reflection
                rn = reflection.note(hypothesis, text, provider=provider, model=model, emit=emit)
                if rn:
                    text += f"\n反思：{rn}"
                return text, {"label": metric, "cur": cur, "sim": sim}, queries
        except Exception:
            pass

    df, meta = run_logged(FALLBACK_SQL, "下架Top20高差评卖家的反事实", conversation_id)
    if meta:
        queries.append(meta)
    if df is None or df.empty:
        return "What-if 无结果。", {}, queries
    cur, sim = float(df.iloc[0]["cur"]), float(df.iloc[0]["sim"])
    text = (f"What-if 默认场景：下架 Top20 高差评卖家后平台平均评分 {cur:.3f} 提升到 {sim:.3f}，"
            f"提升 {sim-cur:.3f} 分。也可直接描述其它假设，例如运费降低10%对GMV的影响。")
    return text, {"label": "平台平均评分", "cur": cur, "sim": sim}, queries
