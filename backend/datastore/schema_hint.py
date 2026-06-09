"""生成给 LLM 的 schema 提示文本（NL→SQL 与路由决策共用）。"""
from __future__ import annotations

from datastore.data_dictionary import (
    BASE_TABLES,
    MATERIALIZED_VIEWS,
    METRIC_DEFINITIONS,
    NAMING_NOTE,
    question_dimensions_hint,
)


def build_schema_hint() -> str:
    metric_lines = "\n".join(f"- {k}：{v}" for k, v in METRIC_DEFINITIONS.items())
    base_lines = []
    for name, meta in BASE_TABLES.items():
        if "key_fields" in meta:
            base_lines.append(f"- {name}({', '.join(meta['key_fields'])})")
        else:
            base_lines.append(f"- {name}（{meta.get('description') or meta.get('note') or meta.get('pk','')}）")
    return f"""【预聚合视图（优先命中，加速路径）】
{question_dimensions_hint()}

【回退基础表（视图无法覆盖时）】
{chr(10).join(base_lines)}

【口径定义（必须遵守）】
{metric_lines}

【聚合口径铁律（极重要，违反会得到错误结论）】
预聚合视图里的「率/均值」列是在更细粒度上算好的，跨行汇总时必须按对应数量列【加权】，禁止直接 AVG()：
  正确：SUM(率 * 数量) / SUM(数量)        错误：AVG(率)
数量列对应关系：
  - mv_delivery_perf.on_time_rate / avg_delivery_days  → 权重 total_orders
  - mv_review_quality.negative_review_rate / avg_review_score → 权重 review_count
  - mv_payment_dist.avg_installments → 权重 total_transactions
  - mv_category_sales.avg_price → 权重 total_orders
例：某州整体准时率 = SUM(on_time_rate*total_orders)/SUM(total_orders)，不是 AVG(on_time_rate)。

【约定】
{NAMING_NOTE}
"""


def list_view_names() -> list[str]:
    return list(MATERIALIZED_VIEWS.keys())
