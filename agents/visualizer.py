"""可视化 Agent：根据分析结果生成图表。"""
from __future__ import annotations

import hashlib
import re

import matplotlib.pyplot as plt
import pandas as pd

from agents.state import AgentState
from config.settings import OUTPUT_CHARTS_DIR
from models.forecast import extract_forecast_weeks, forecast_next_weeks, load_weekly_sales_history
from models.sentiment import analyze_review_texts
from utils.db import run_select

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _save_fig(filename: str) -> str:
    OUTPUT_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_CHARTS_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return str(path)


def _chart_path(filename: str) -> str:
    return str(OUTPUT_CHARTS_DIR / filename)


def _chart_monthly_sales() -> str:
    df = run_select("SELECT `year_month`, total_gmv FROM mv_monthly_sales ORDER BY `year_month`")
    plt.figure(figsize=(10, 4))
    plt.plot(df["year_month"], df["total_gmv"], marker="o", label="历史GMV")
    plt.xticks(rotation=45)
    plt.title("月度销售额趋势")
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
        SELECT payment_type, payment_installments, total_transactions AS cnt
        FROM mv_payment_installment_matrix
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
        SELECT weight_bucket, avg_weight_g, avg_freight, order_cnt
        FROM mv_weight_freight_bucket
        ORDER BY avg_weight_g
        """
    )
    plt.figure(figsize=(8, 5))
    sizes = (df["order_cnt"] / df["order_cnt"].max() * 200).clip(lower=10)
    plt.scatter(df["avg_weight_g"], df["avg_freight"], s=sizes, alpha=0.55)
    for row in df.itertuples():
        plt.annotate(row.weight_bucket, (row.avg_weight_g, row.avg_freight), fontsize=8)
    plt.title("商品重量分桶 vs 平均运费")
    plt.xlabel("avg_weight_g")
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


def _chart_state_geo_bubble() -> str:
    df = run_select(
        """
        SELECT customer_state, total_gmv, total_orders, latitude, longitude
        FROM mv_state_geo_sales
        ORDER BY total_gmv DESC
        """
    )
    plt.figure(figsize=(8, 6))
    sizes = (df["total_gmv"] / df["total_gmv"].max() * 900).clip(lower=30)
    scatter = plt.scatter(df["longitude"], df["latitude"], s=sizes, c=df["total_gmv"], alpha=0.65, cmap="viridis")
    for row in df.itertuples():
        plt.annotate(row.customer_state, (row.longitude, row.latitude), fontsize=8)
    plt.colorbar(scatter, label="total_gmv")
    plt.title("巴西州级销售额地理气泡图")
    plt.xlabel("longitude")
    plt.ylabel("latitude")
    return _save_fig("chart_state_geo_bubble.png")


def _chart_review_topics() -> str:
    result = analyze_review_texts(limit=3000)
    positive = result.get("positive_keywords", [])[:8]
    negative = result.get("negative_keywords", [])[:8]
    terms = [item["term"] for item in negative] + [item["term"] for item in positive]
    values = [-item["count"] for item in negative] + [item["count"] for item in positive]
    colors = ["#c95050"] * len(negative) + ["#2b8a6e"] * len(positive)
    plt.figure(figsize=(9, 5))
    plt.barh(terms, values, color=colors)
    plt.axvline(0, color="#333333", linewidth=0.8)
    plt.title("评论文本主题：负向 vs 正向关键词")
    plt.xlabel("负向频次 ← 0 → 正向频次")
    return _save_fig("chart_review_topics.png")


CHART_SPECS: list[tuple[str, str, str, callable]] = [
    ("monthly_sales", "月度销售额趋势", "chart_monthly_sales.png", _chart_monthly_sales),
    ("state_bar", "Top15 州销售额", "chart_state_sales_bar.png", _chart_state_bar),
    ("payment_bar", "支付方式频次", "chart_payment_bar.png", _chart_payment_bar),
    ("payment_installments_heat", "支付方式 × 分期数 热力图", "chart_payment_heatmap.png", _chart_payment_installments_heat),
    ("weight_freight_scatter", "商品重量 vs 平均运费", "chart_weight_freight_scatter.png", _chart_weight_freight_scatter),
    ("delivery_line", "准时交付率月度趋势", "chart_delivery_line.png", _chart_delivery_line),
    ("seller_review_risk", "卖家评分风险矩阵", "chart_seller_review_risk.png", _chart_review_risk),
    ("state_geo_bubble", "州级销售额地理气泡图", "chart_state_geo_bubble.png", _chart_state_geo_bubble),
    ("review_topics", "评论文本主题关键词", "chart_review_topics.png", _chart_review_topics),
]


def ensure_default_charts() -> list[str]:
    chart_paths: list[str] = []
    for _name, _title, filename, builder in CHART_SPECS:
        path = OUTPUT_CHARTS_DIR / filename
        if not path.exists() or path.stat().st_size == 0:
            builder()
        chart_paths.append(str(path))
    return chart_paths


def _safe_slug(text: str, fallback: str = "query") -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    prefix = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")[:24]
    return f"{prefix or fallback}_{digest}"


def _result_frame(item: dict) -> pd.DataFrame:
    rows = item.get("rows") or []
    columns = item.get("columns") or []
    return pd.DataFrame(rows, columns=columns or None)


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]


def _dimension_columns(df: pd.DataFrame) -> list[str]:
    numeric = set(_numeric_columns(df))
    return [column for column in df.columns if column not in numeric]


def _metric_column(df: pd.DataFrame) -> str | None:
    priority = (
        "total_gmv", "gmv", "total_orders", "orders", "transactions", "total_value",
        "on_time_rate", "delay_rate", "avg_delivery_days", "avg_freight", "avg_review_score",
        "negative_review_rate", "negative_orders", "order_cnt",
    )
    numeric = _numeric_columns(df)
    for term in priority:
        for column in numeric:
            if term in column.lower():
                return column
    return numeric[0] if numeric else None


def _question_metric_column(question: str, df: pd.DataFrame) -> str | None:
    """按问题语义从本轮查询结果中选择绘图指标。"""
    q = question.lower()
    priorities = (
        (("延迟时间", "派送时长", "配送时长", "平均配送", "交付时长"), "avg_delivery_days"),
        (("延迟订单", "延误订单"), "delayed_orders"),
        (("延迟最严重", "延迟率", "哪些州延迟"), "delay_rate_pct"),
        (("准时率", "交付率", "准时交付"), "on_time_rate_pct"),
        (("平均分期", "分期数"), "avg_installments"),
        (("最受欢迎", "支付方式"), "total_transactions"),
        (("退货率", "负面评价"), "negative_review_rate_pct"),
        (("销售额", "gmv"), "total_gmv"),
        (("订单数", "订单量"), "total_orders"),
    )
    for terms, candidate in priorities:
        if any(term in q for term in terms) and candidate in df.columns:
            return candidate
    return None


def _dimension_column(df: pd.DataFrame) -> str | None:
    priority = (
        "year_month", "customer_state", "product_category", "payment_type",
        "weight_bucket", "seller_id", "payment_installments",
    )
    dimensions = _dimension_columns(df)
    for term in priority:
        for column in dimensions:
            if term in column.lower():
                return column
    return dimensions[0] if dimensions else None


def _save_dynamic(filename: str) -> str:
    return _save_fig(f"dynamic/{filename}")


def _plot_line(df: pd.DataFrame, x: str, y: str, title: str, filename: str) -> str:
    plot_df = df[[x, y]].dropna().sort_values(x)
    plt.figure(figsize=(10, 4))
    plt.plot(plot_df[x].astype(str), plot_df[y], marker="o")
    plt.xticks(rotation=45)
    plt.title(title)
    plt.xlabel(x)
    plt.ylabel(y)
    return _save_dynamic(filename)


def _plot_grouped_line(df: pd.DataFrame, x: str, y: str, group: str, title: str, filename: str) -> str:
    plot_df = df[[x, y, group]].dropna().sort_values(x)
    plt.figure(figsize=(10, 4.8))
    for name, part in plot_df.groupby(group):
        plt.plot(part[x].astype(str), part[y], marker="o", markersize=3, label=str(name))
    plt.xticks(rotation=45)
    plt.title(title)
    plt.xlabel(x)
    plt.ylabel(y)
    plt.legend(ncol=3)
    return _save_dynamic(filename)


def _plot_bar(df: pd.DataFrame, x: str, y: str, title: str, filename: str) -> str:
    plot_df = df[[x, y]].dropna().head(20)
    plt.figure(figsize=(10, 4.8))
    plt.bar(plot_df[x].astype(str), plot_df[y])
    plt.xticks(rotation=45, ha="right")
    plt.title(title)
    plt.xlabel(x)
    plt.ylabel(y)
    return _save_dynamic(filename)


def _plot_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    filename: str,
    size: str | None = None,
    label: str | None = None,
) -> str:
    columns = [x, y] + ([size] if size else []) + ([label] if label else [])
    plot_df = df[columns].dropna().head(100)
    sizes = 60
    if size and not plot_df.empty and plot_df[size].max() > 0:
        sizes = (plot_df[size] / plot_df[size].max() * 500).clip(lower=20)
    plt.figure(figsize=(8, 5))
    plt.scatter(plot_df[x], plot_df[y], s=sizes, alpha=0.6)
    if label and len(plot_df) <= 30:
        for row in plot_df.itertuples(index=False):
            values = row._asdict()
            plt.annotate(str(values[label]), (values[x], values[y]), fontsize=8)
    plt.title(title)
    plt.xlabel(x)
    plt.ylabel(y)
    return _save_dynamic(filename)


def _plot_heatmap(df: pd.DataFrame, index: str, columns: str, value: str, title: str, filename: str) -> str:
    pivot = pd.pivot_table(df, index=index, columns=columns, values=value, aggfunc="sum", fill_value=0)
    plt.figure(figsize=(10, 4.8))
    plt.imshow(pivot.values, aspect="auto")
    plt.colorbar()
    plt.yticks(range(len(pivot.index)), pivot.index)
    plt.xticks(range(len(pivot.columns)), pivot.columns, rotation=45)
    plt.title(title)
    return _save_dynamic(filename)


def _plot_forecast(title: str, filename: str, forecast_weeks: int = 6) -> str:
    history, _excluded = load_weekly_sales_history()
    forecast = forecast_next_weeks(forecast_weeks)
    training_weeks = int(forecast.attrs.get("training_weeks", 39)) if not forecast.empty else 39
    display_history = history.tail(training_weeks)
    plt.figure(figsize=(10, 4))
    history_x = display_history["week_start"].dt.strftime("%Y-%m-%d")
    plt.plot(history_x, display_history["total_gmv"], marker="o", markersize=3, label=f"最近{len(display_history)}周历史 GMV")
    if not forecast.empty:
        forecast_x = forecast["week_start"].dt.strftime("%Y-%m-%d")
        plt.plot(forecast_x, forecast["yhat"], marker="x", linestyle="--", label=f"未来{forecast_weeks}周预测 GMV")
        plt.fill_between(forecast_x, forecast["yhat_lower"], forecast["yhat_upper"], alpha=0.2)
    tick_step = max(1, len(history_x) // 12)
    plt.xticks(range(0, len(history_x), tick_step), history_x.iloc[::tick_step], rotation=45)
    plt.title(title)
    plt.ylabel("GMV")
    plt.legend()
    return _save_dynamic(filename)


def _plot_review_topics_from_state(state: AgentState, filename: str) -> str | None:
    result = state.get("nlp_result") or {}
    positive = result.get("positive_keywords", [])[:8]
    negative = result.get("negative_keywords", [])[:8]
    if not positive and not negative:
        return None
    terms = [item["term"] for item in negative] + [item["term"] for item in positive]
    values = [-item["count"] for item in negative] + [item["count"] for item in positive]
    colors = ["#c95050"] * len(negative) + ["#2b8a6e"] * len(positive)
    plt.figure(figsize=(9, 5))
    plt.barh(terms, values, color=colors)
    plt.axvline(0, color="#333333", linewidth=0.8)
    plt.title("本轮评论文本主题：负向 vs 正向关键词")
    plt.xlabel("负向频次 ← 0 → 正向频次")
    return _save_dynamic(filename)


def _dynamic_chart_for_result(item: dict, index: int) -> tuple[str, str, str] | None:
    df = _result_frame(item)
    if df.empty:
        return None
    question = str(item.get("question") or f"问题{index}")
    source = str(item.get("source") or "")
    q = question.lower()
    base = f"{index}_{_safe_slug(question)}"

    if "review_comment_message" in df.columns:
        return None
    if len(df) == 1:
        return None

    if source == "mv_state_geo_sales" and {"longitude", "latitude", "total_gmv"}.issubset(df.columns):
        path = _plot_scatter(
            df, "longitude", "latitude", f"{question} · 州级地理气泡图",
            f"{base}_geo.png", size="total_gmv", label="customer_state",
        )
        return path, f"{question} · 州级地理气泡图", "命中州级地理预聚合，选择气泡图"

    if source == "mv_payment_installment_matrix" and {
        "payment_type", "payment_installments", "total_transactions"
    }.issubset(df.columns):
        path = _plot_heatmap(
            df, "payment_type", "payment_installments", "total_transactions",
            f"{question} · 支付分期热力图", f"{base}_heatmap.png",
        )
        return path, f"{question} · 支付分期热力图", "两个分类维度与交易频次，选择热力图"

    if source == "mv_weight_freight_bucket" and {"avg_weight_g", "avg_freight", "avg_volume_cm3"}.issubset(df.columns):
        path = _plot_scatter(
            df, "avg_weight_g", "avg_freight", f"{question} · 重量、尺寸与运费关系",
            f"{base}_scatter.png", size="avg_volume_cm3", label="weight_bucket",
        )
        return path, f"{question} · 重量、尺寸与运费关系", "横轴为重量、纵轴为运费、气泡大小为平均体积"

    if source == "mv_seller_review_risk" and {"avg_review_score", "negative_orders", "total_orders"}.issubset(df.columns):
        path = _plot_scatter(
            df, "avg_review_score", "negative_orders", f"{question} · 卖家风险矩阵",
            f"{base}_seller_risk.png", size="total_orders", label="seller_id",
        )
        return path, f"{question} · 卖家风险矩阵", "卖家评分、差评与订单量，选择风险气泡图"

    if source == "mv_review_quality" and {
        "customer_state", "product_category_english", "negative_review_rate_pct"
    }.issubset(df.columns):
        risk_df = df.copy()
        risk_df["risk_segment"] = (
            risk_df["customer_state"].astype(str) + " / " + risk_df["product_category_english"].astype(str)
        )
        path = _plot_bar(
            risk_df.sort_values("negative_review_rate_pct", ascending=False),
            "risk_segment",
            "negative_review_rate_pct",
            f"{question} · 高风险州与品类",
            f"{base}_risk_bar.png",
        )
        return path, f"{question} · 高风险州与品类", "使用有足够评论样本的州-品类负面评价率代理退货风险"

    if source == "mv_state_sales" and {"year_month", "customer_state", "total_gmv"}.issubset(df.columns) and any(
        term in q for term in ("趋势", "按月", "变化")
    ):
        path = _plot_grouped_line(
            df, "year_month", "total_gmv", "customer_state",
            f"{question} · Top州月度GMV趋势", f"{base}_grouped_line.png",
        )
        return path, f"{question} · Top州月度GMV趋势", "时间、州和GMV三维结果，选择多序列折线图"

    metric = _question_metric_column(question, df) or _metric_column(df)
    preferred_dimensions = {
        "mv_state_sales": "customer_state",
        "mv_category_sales": "product_category_english",
        "mv_payment_dist": "payment_type",
        "mv_review_quality": "product_category_english",
        "mv_delivery_perf": "year_month" if any(term in q for term in ("趋势", "按月", "变化")) else "customer_state",
    }
    preferred = preferred_dimensions.get(source)
    dimension = preferred if preferred in df.columns else _dimension_column(df)
    if not metric:
        return None
    if dimension and ("year_month" in dimension.lower() or any(term in q for term in ("趋势", "按月", "变化"))):
        path = _plot_line(df, dimension, metric, f"{question} · 趋势", f"{base}_line.png")
        return path, f"{question} · 趋势", f"时间维度 {dimension} 与指标 {metric}，选择折线图"
    if dimension:
        ordered = df.sort_values(metric, ascending=False)
        path = _plot_bar(ordered, dimension, metric, f"{question} · 对比", f"{base}_bar.png")
        return path, f"{question} · 对比", f"分类维度 {dimension} 与指标 {metric}，选择柱状图"
    numeric = _numeric_columns(df)
    if len(numeric) >= 2:
        path = _plot_scatter(df, numeric[0], numeric[1], f"{question} · 指标关系", f"{base}_scatter.png")
        return path, f"{question} · 指标关系", "两个连续指标，选择散点图"
    return None


def generate_query_charts(state: AgentState) -> tuple[list[str], list[str], str]:
    paths: list[str] = []
    titles: list[str] = []
    reasons: list[str] = []
    query = state.get("user_query", "")

    if state.get("need_forecast", False):
        forecast_weeks = state.get("forecast_weeks") or extract_forecast_weeks(query)
        path = _plot_forecast(
            f"{query} · 历史与预测",
            f"0_{_safe_slug(query)}_forecast.png",
            forecast_weeks,
        )
        paths.append(path)
        titles.append(f"{query} · 历史与预测")
        reasons.append("问题包含预测意图，选择带置信区间的时间序列图")

    for index, item in enumerate(state.get("data_results") or [], start=1):
        if state.get("need_forecast", False) and item.get("source") in {"mv_monthly_sales", "mv_weekly_sales"}:
            continue
        chart = _dynamic_chart_for_result(item, index)
        if chart:
            path, title, reason = chart
            if path not in paths:
                paths.append(path)
                titles.append(title)
                reasons.append(reason)

    if state.get("need_nlp", False):
        path = _plot_review_topics_from_state(state, f"nlp_{_safe_slug(query)}_topics.png")
        if path:
            paths.append(path)
            titles.append(f"{query} · 评论主题关键词")
            reasons.append("问题包含评论文本洞察意图，选择正负向主题对比图")

    return paths, titles, "；".join(reasons)


def visualizer_node(state: AgentState) -> AgentState:
    if not state.get("need_visualization", True):
        print("[visualizer] skipped: need_visualization=False", flush=True)
        return {}
    print("[visualizer] node start", flush=True)
    chart_paths, chart_titles, strategy = generate_query_charts(state)
    print(f"[visualizer] node done: charts={len(chart_paths)}", flush=True)
    return {
        "chart_paths": chart_paths,
        "chart_titles": chart_titles,
        "visualization_strategy": strategy or "本轮结果没有适合自动绘图的结构化数值字段。",
    }
