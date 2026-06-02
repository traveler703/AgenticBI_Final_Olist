"""What-if 模拟与异常检测 Agent。"""
from __future__ import annotations

import pandas as pd

from agents.state import AgentState
from utils.db import run_select


def _whatif_remove_top_bad_sellers(top_n: int = 20) -> str:
    sql = f"""
    WITH top_bad AS (
        SELECT seller_id
        FROM mv_seller_review_risk
        WHERE total_orders >= 20
        ORDER BY avg_review_score ASC, negative_orders DESC
        LIMIT {int(top_n)}
    )
    SELECT
        (SELECT AVG(r.review_score)
         FROM fact_order_items f JOIN order_reviews r ON f.order_id = r.order_id) AS current_avg_score,
        (SELECT AVG(r.review_score)
         FROM fact_order_items f JOIN order_reviews r ON f.order_id = r.order_id
         WHERE f.seller_id NOT IN (SELECT seller_id FROM top_bad)) AS simulated_avg_score,
        (SELECT COUNT(*) FROM top_bad) AS removed_sellers
    """
    df = run_select(sql)
    if df.empty:
        return "What-if 模拟暂无结果。"
    row = df.iloc[0]
    current = float(row["current_avg_score"])
    simulated = float(row["simulated_avg_score"])
    uplift = simulated - current
    return (
        f"What-if：若下架 Top {int(row['removed_sellers'])} 高差评卖家，"
        f"平台平均评分预计从 {current:.3f} 提升到 {simulated:.3f}，提升 {uplift:.3f} 分。"
    )


def _detect_state_sales_anomaly() -> str:
    df = run_select(
        """
        SELECT `year_month`, customer_state, total_orders, total_gmv
        FROM mv_state_sales
        ORDER BY customer_state, `year_month`
        """
    )
    if df.empty:
        return "异常检测暂无数据。"

    alerts: list[str] = []
    for state, part in df.groupby("customer_state"):
        part = part.sort_values("year_month").copy()
        if len(part) < 3:
            continue
        part["mom_orders"] = part["total_orders"].pct_change()
        recent = part.iloc[-1]
        if pd.notna(recent["mom_orders"]) and recent["mom_orders"] <= -0.35:
            alerts.append(f"{state} 最近月订单量环比下降 {recent['mom_orders']:.1%}")

    if not alerts:
        return "异常检测：未发现明显州级订单骤降（阈值：最近月环比下降超过 35%）。"
    return "异常检测预警：" + "；".join(alerts[:5]) + "。"


def whatif_anomaly_node(state: AgentState) -> AgentState:
    result: dict[str, str] = {}
    if state.get("need_whatif", False):
        result["whatif_insights"] = _whatif_remove_top_bad_sellers()
    if state.get("need_anomaly", False):
        result["anomaly_insights"] = _detect_state_sales_anomaly()
    return result
