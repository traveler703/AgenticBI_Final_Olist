"""可视化 Agent：根据分析结果生成图表。"""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from agents.state import AgentState
from config.settings import OUTPUT_CHARTS_DIR
from models.forecast import forecast_next_6_periods
from utils.db import run_select

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _save_fig(filename: str) -> str:
    OUTPUT_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_CHARTS_DIR / filename
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return str(path)


def _chart_path(filename: str) -> str:
    return str(OUTPUT_CHARTS_DIR / filename)


def _chart_monthly_sales() -> str:
    df = run_select("SELECT `year_month`, total_gmv FROM mv_monthly_sales ORDER BY `year_month`")
    forecast_df = forecast_next_6_periods()
    plt.figure(figsize=(10, 4))
    plt.plot(df["year_month"], df["total_gmv"], marker="o", label="历史GMV")
    if not forecast_df.empty:
        plt.plot(forecast_df["year_month"], forecast_df["yhat"], marker="x", linestyle="--", label="预测GMV")
        plt.fill_between(forecast_df["year_month"], forecast_df["yhat_lower"], forecast_df["yhat_upper"], alpha=0.2)
    plt.xticks(rotation=45)
    plt.title("月度销售额趋势（含预测）")
    plt.legend()
    return _save_fig("chart_monthly_sales.png")


def _chart_state_bar() -> str:
    df = run_select(
        """
        SELECT customer_state, SUM(total_gmv) AS total_gmv
        FROM mv_state_sales
        GROUP BY customer_state
        ORDER BY total_gmv DESC
        LIMIT 15
        """
    )
    plt.figure(figsize=(10, 4))
    plt.bar(df["customer_state"], df["total_gmv"])
    plt.title("Top15 州销售额")
    plt.xticks(rotation=45)
    return _save_fig("chart_state_sales_bar.png")


def _chart_payment_bar() -> str:
    df = run_select(
        """
        SELECT payment_type, SUM(total_transactions) AS tx_cnt
        FROM mv_payment_dist
        GROUP BY payment_type
        ORDER BY tx_cnt DESC
        """
    )
    plt.figure(figsize=(8, 4))
    plt.bar(df["payment_type"], df["tx_cnt"])
    plt.title("支付方式频次")
    plt.xticks(rotation=20)
    return _save_fig("chart_payment_bar.png")


def _chart_payment_installments_heat() -> str:
    df = run_select(
        """
        SELECT payment_type, payment_installments, COUNT(*) AS cnt
        FROM order_payments
        GROUP BY payment_type, payment_installments
        """
    )
    pivot = pd.pivot_table(
        df, index="payment_type", columns="payment_installments", values="cnt", aggfunc="sum", fill_value=0
    )
    plt.figure(figsize=(10, 4))
    plt.imshow(pivot.values, aspect="auto")
    plt.colorbar()
    plt.yticks(range(len(pivot.index)), pivot.index)
    plt.xticks(range(len(pivot.columns)), pivot.columns, rotation=45)
    plt.title("支付方式 × 分期数 热力图")
    return _save_fig("chart_payment_heatmap.png")


def _chart_weight_freight_scatter() -> str:
    df = run_select(
        """
        SELECT product_weight_g, AVG(freight_value) AS avg_freight, COUNT(*) AS order_cnt
        FROM fact_order_items
        WHERE product_weight_g IS NOT NULL
        GROUP BY product_weight_g
        HAVING order_cnt >= 5
        ORDER BY order_cnt DESC
        LIMIT 400
        """
    )
    plt.figure(figsize=(8, 5))
    sizes = (df["order_cnt"] / df["order_cnt"].max() * 200).clip(lower=10)
    plt.scatter(df["product_weight_g"], df["avg_freight"], s=sizes, alpha=0.5)
    plt.title("商品重量 vs 平均运费")
    plt.xlabel("product_weight_g")
    plt.ylabel("avg_freight")
    return _save_fig("chart_weight_freight_scatter.png")


def _chart_delivery_line() -> str:
    df = run_select(
        """
        SELECT `year_month`, AVG(on_time_rate) AS on_time_rate
        FROM mv_delivery_perf
        GROUP BY `year_month`
        ORDER BY `year_month`
        """
    )
    plt.figure(figsize=(10, 4))
    plt.plot(df["year_month"], df["on_time_rate"], marker="o")
    plt.xticks(rotation=45)
    plt.title("准时交付率月度趋势")
    return _save_fig("chart_delivery_line.png")


def _chart_review_risk() -> str:
    df = run_select(
        """
        SELECT seller_id, total_orders, avg_review_score, negative_orders
        FROM mv_seller_review_risk
        WHERE total_orders >= 3 AND avg_review_score IS NOT NULL
        ORDER BY avg_review_score ASC, negative_orders DESC
        LIMIT 80
        """
    )
    plt.figure(figsize=(8, 5))
    sizes = (df["total_orders"] / df["total_orders"].max() * 180).clip(lower=12)
    plt.scatter(df["avg_review_score"], df["negative_orders"], s=sizes, alpha=0.55)
    plt.title("卖家评分风险矩阵")
    plt.xlabel("avg_review_score")
    plt.ylabel("negative_orders")
    return _save_fig("chart_seller_review_risk.png")


CHART_SPECS: list[tuple[str, str, str, callable]] = [
    ("monthly_sales", "月度销售额趋势（含预测）", "chart_monthly_sales.png", _chart_monthly_sales),
    ("state_bar", "Top15 州销售额", "chart_state_sales_bar.png", _chart_state_bar),
    ("payment_bar", "支付方式频次", "chart_payment_bar.png", _chart_payment_bar),
    ("payment_installments_heat", "支付方式 × 分期数 热力图", "chart_payment_heatmap.png", _chart_payment_installments_heat),
    ("weight_freight_scatter", "商品重量 vs 平均运费", "chart_weight_freight_scatter.png", _chart_weight_freight_scatter),
    ("delivery_line", "准时交付率月度趋势", "chart_delivery_line.png", _chart_delivery_line),
    ("seller_review_risk", "卖家评分风险矩阵", "chart_seller_review_risk.png", _chart_review_risk),
]


def ensure_default_charts() -> list[str]:
    chart_paths: list[str] = []
    for _name, _title, filename, builder in CHART_SPECS:
        path = OUTPUT_CHARTS_DIR / filename
        if not path.exists() or path.stat().st_size == 0:
            builder()
        chart_paths.append(str(path))
    return chart_paths


def visualizer_node(state: AgentState) -> AgentState:
    if not state.get("need_visualization", True):
        print("[visualizer] skipped: need_visualization=False", flush=True)
        return {}
    print("[visualizer] node start", flush=True)
    chart_paths = ensure_default_charts()
    print(f"[visualizer] node done: charts={len(chart_paths)}", flush=True)
    return {"chart_paths": chart_paths}
