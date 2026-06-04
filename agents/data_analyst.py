"""数据分析 Agent：NL→SQL，优先预聚合视图。"""
from __future__ import annotations

import json
import re
import textwrap

import pandas as pd

from agents.state import AgentState
from utils.llm import deepseek_chat
from utils.db import run_select

MV_TABLES = [
    "mv_monthly_sales",
    "mv_weekly_sales",
    "mv_state_sales",
    "mv_category_sales",
    "mv_delivery_perf",
    "mv_payment_dist",
    "mv_payment_installment_matrix",
    "mv_weight_freight_bucket",
    "mv_state_geo_sales",
    "mv_review_quality",
    "mv_seller_review_risk",
]

DATA_DICTIONARY = """
预聚合视图优先：
- mv_monthly_sales(`year_month`, total_gmv, total_orders, avg_basket, total_freight)
- mv_weekly_sales(week_start, total_gmv, total_orders, avg_basket, total_freight)
- mv_state_sales(`year_month`, customer_state, total_gmv, total_orders, unique_customers)
- mv_category_sales(`year_month`, product_category_english, total_gmv, total_orders, avg_price)
- mv_delivery_perf(`year_month`, customer_state, avg_delivery_days, on_time_rate, delayed_orders, total_orders)
- mv_payment_dist(`year_month`, payment_type, total_transactions, avg_installments, total_value)
- mv_payment_installment_matrix(payment_type, payment_installments, total_transactions, total_value)
- mv_weight_freight_bucket(weight_bucket, avg_weight_g, avg_length_cm, avg_height_cm, avg_width_cm, avg_volume_cm3, avg_freight, avg_delivery_days, order_cnt)
- mv_state_geo_sales(customer_state, total_gmv, total_orders, latitude, longitude)
- mv_review_quality(`year_month`, customer_state, product_category_english, avg_review_score, negative_review_rate, review_count)
- mv_seller_review_risk(seller_id, total_orders, total_gmv, avg_review_score, negative_orders, delay_rate)
回退表：
- fact_order_items(order_id, order_item_id, product_id, seller_id, price, freight_value, item_gmv,
  `year_month`, customer_state, seller_state, product_category_english, product_weight_g,
  is_on_time, shipping_duration_days)
- order_reviews(order_id, review_score, review_comment_message)
重要：字段 year_month 必须写成 `year_month`。
重要：只能返回一条 SELECT，禁止用分号拼接多条 SQL。
"""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("LLM 未返回 JSON。")
    return json.loads(match.group(0))


def _normalize_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    sql = re.sub(r"\byear_month\b", "`year_month`", sql, flags=re.I)
    sql = sql.replace("``year_month``", "`year_month`")
    if ";" in sql:
        raise ValueError("不允许返回多条 SQL。")
    if not re.match(r"^\s*select\b", sql, flags=re.I):
        raise ValueError("只允许 SELECT SQL。")
    if not re.search(r"\blimit\b", sql, flags=re.I):
        sql = f"{sql} LIMIT 300"
    return sql


def _split_compound_questions(query: str) -> list[str]:
    """把一次输入中的多个业务问句拆开，保留短上下文短语。"""
    parts = [part.strip(" ，,；;") for part in re.split(r"[?？]+", query) if part.strip(" ，,；;")]
    if len(parts) <= 1:
        return [query.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and re.match(r"^(请)?给出|^请制定|^并给出", part):
            merged[-1] = f"{merged[-1]}？{part}"
        else:
            merged.append(part)
    year_match = re.search(r"(20\d{2})\s*年", query)
    if year_match:
        year_prefix = f"{year_match.group(1)}年"
        merged = [part if re.search(r"20\d{2}\s*年", part) else f"{year_prefix}{part}" for part in merged]
    return merged[:5]


def generate_sql_with_deepseek(query: str) -> tuple[str, str, str]:
    print(f"[data_analyst] DeepSeek SQL generation start: query={query[:120]}", flush=True)
    system = (
        "你是 Olist 电商 BI 数据分析 Agent。"
        "请把中文业务问题转换为 MySQL SELECT。必须优先使用 mv_* 预聚合视图，"
        "无法覆盖时才回退 fact_order_items 或基础表。"
        "只能返回一条 SQL，不要使用分号，不要返回解释文字，只输出 JSON。"
    )
    user = f"""
数据字典：
{DATA_DICTIONARY}


用户问题：{query}

输出 JSON 格式：
{{"sql": "SELECT ...", "source": "mv_monthly_sales|mv_weekly_sales|mv_state_sales|mv_category_sales|mv_delivery_perf|mv_payment_dist|mv_payment_installment_matrix|mv_weight_freight_bucket|mv_state_geo_sales|mv_review_quality|mv_seller_review_risk|fact_order_items|base", "reason": "命中原因"}}
"""
    raw = deepseek_chat(system, user)
    payload = _extract_json(raw)
    sql = _normalize_sql(payload["sql"])
    source = payload.get("source", "llm")
    reason = payload.get("reason", "DeepSeek 生成")
    print(f"[data_analyst] DeepSeek SQL generation done: source={source}; sql={sql[:180]}", flush=True)
    return sql, source, reason


def _serializable_preview(df, limit: int = 300) -> tuple[list[dict], list[str], int]:
    """DataFrame 不能进入 LangGraph checkpoint，转成 msgpack 友好的结构。"""
    preview = df.head(limit).copy()
    rows = json.loads(preview.to_json(orient="records", date_format="iso", force_ascii=False))
    return rows, list(df.columns), int(len(df))


def _fmt(value, digits: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 10000:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _should_use_template(query: str) -> bool:
    """高频验收题优先走确定性 SQL，避免 LLM 生成多语句或缺字段。"""
    q = query.lower()
    keywords = (
        "gmv", "销售额", "排名", "趋势", "准时", "延迟", "配送", "交付", "交付率",
        "支付", "分期", "重量", "尺寸", "运费", "预测", "未来", "优先改进策略",
        "退货率", "东北部",
    )
    return any(k in q for k in keywords)


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]


def _dimension_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in _numeric_columns(df)]


def _preferred_metric_column(df: pd.DataFrame) -> str | None:
    numeric_cols = _numeric_columns(df)
    if not numeric_cols:
        return None
    priority_terms = (
        "total_gmv",
        "gmv",
        "sales",
        "value",
        "revenue",
        "orders",
        "transactions",
        "rate",
        "score",
        "days",
        "freight",
        "price",
    )
    lowered = {col: col.lower() for col in numeric_cols}
    for term in priority_terms:
        for col, low in lowered.items():
            if term in low:
                return col
    return numeric_cols[0]


def _preferred_dimension_column(df: pd.DataFrame) -> str | None:
    dim_cols = _dimension_columns(df)
    if not dim_cols:
        return None
    priority_terms = ("state", "category", "payment", "seller", "customer", "year_month", "month", "city", "type")
    lowered = {col: col.lower() for col in dim_cols}
    for term in priority_terms:
        for col, low in lowered.items():
            if term in low:
                return col
    return dim_cols[0]


def _resolve_context_from_rows(query: str, rows: list[dict], columns: list[str]) -> tuple[str, str]:
    """基于同一轮前序结果解析当前问句中的指代。"""
    if not rows or not columns:
        return query, ""

    q = query.lower()
    trigger_terms = ("这个", "该", "上述", "上面", "刚才", "排名第一", "第一名", "这些", "它们", "该州", "这个州")
    implicit_state_followup = "customer_state" in columns and any(
        term in q for term in ("交付", "准时", "延迟", "配送", "支付")
    )
    if not any(term in q for term in trigger_terms) and not implicit_state_followup:
        return query, ""

    df = pd.DataFrame(rows, columns=columns)
    dim_col = _preferred_dimension_column(df)
    metric_col = _preferred_metric_column(df)
    if not dim_col:
        return query, ""

    context_items: list[str] = []
    if "排名第一" in q or "第一名" in q or "这个" in q or "该" in q or implicit_state_followup:
        ranked = df
        if metric_col:
            ranked = df.sort_values(metric_col, ascending=False)
        top_value = ranked.iloc[0][dim_col]
        context_items.append(f"{dim_col}={top_value}")

    if "这些" in q or "它们" in q or "上述" in q or "上面" in q:
        values = [str(v) for v in df[dim_col].dropna().head(5).tolist()]
        if values:
            context_items.append(f"{dim_col} in ({', '.join(values)})")

    if not context_items:
        return query, ""

    note = "；".join(context_items)
    resolved = f"{query}（结合上一轮分析结果：{note}）"
    return resolved, note


def _select_sql_for_query(query: str) -> tuple[str, str, str]:
    reason = "规则兜底"
    if _should_use_template(query):
        print("[data_analyst] using template SQL", flush=True)
        sql, source = choose_sql(query)
        reason = "命中高频业务问题模板，优先使用稳定 SQL。"
    else:
        try:
            sql, source, reason = generate_sql_with_deepseek(query)
        except Exception as exc:  # noqa: BLE001
            print(f"[data_analyst] DeepSeek failed, fallback to template: {exc}", flush=True)
            sql, source = choose_sql(query)
            reason = f"DeepSeek 不可用，使用规则兜底：{exc}"
    return sql, source, reason


def _execute_sql_with_fallback(query: str, sql: str, source: str, reason: str) -> tuple[pd.DataFrame, str, str, str]:
    try:
        print(f"[data_analyst] SQL execute start: source={source}; sql={sql[:180]}", flush=True)
        df = run_select(sql)
        print(f"[data_analyst] SQL execute done: rows={len(df)}, columns={list(df.columns)}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[data_analyst] SQL execute failed, fallback start: {exc}", flush=True)
        fallback_sql, fallback_source = choose_sql(query)
        df = run_select(fallback_sql)
        sql = fallback_sql
        source = fallback_source
        reason = f"DeepSeek SQL 执行失败，已自动回退到内置安全查询：{exc}"
        print(f"[data_analyst] fallback SQL execute done: rows={len(df)}, source={source}", flush=True)
    return df, sql, source, reason


def _heuristic_business_summary(query: str, df: pd.DataFrame) -> str:
    if df.empty:
        return "未查询到结果，请检查筛选条件。"

    lines: list[str] = []

    metric_col = _preferred_metric_column(df)
    dim_col = _preferred_dimension_column(df)
    q = query.lower()

    if "overall_on_time_rate_pct" in df.columns:
        latest_month = df["year_month"].dropna().iloc[0] if "year_month" in df.columns else "最近月份"
        lines.append(f"平台在 {latest_month} 的整体准时交付率约为 {_fmt(df['overall_on_time_rate_pct'].dropna().iloc[0])}%。")
    elif "on_time_rate" in df.columns:
        rate = df["on_time_rate"].dropna().mean()
        rate = rate * 100 if rate <= 1 else rate
        lines.append(f"平台整体准时交付率约为 {_fmt(rate)}%。")

    if {"customer_state", "delay_rate_pct", "delayed_orders"}.issubset(df.columns):
        worst = df.sort_values(["delay_rate_pct", "delayed_orders"], ascending=[False, False]).head(5)
        items = [
            f"{row.customer_state}（延迟率 {_fmt(row.delay_rate_pct)}%，延迟订单 {int(row.delayed_orders):,}）"
            for row in worst.itertuples()
        ]
        lines.append("延迟最严重的州包括：" + "、".join(items) + "。")

    if dim_col and metric_col:
        ascending = any(term in q for term in ("最低", "最少", "延迟最严重", "延迟最高")) and "delay" not in metric_col.lower()
        ranked = df.sort_values(metric_col, ascending=ascending).head(5)
        label = "最低" if ascending else "最高"
        if any(term in q for term in ("排名", "排行", "哪些", "哪个", "最高", "最低", "最严重", "top")):
            items = [f"{row[dim_col]}（{metric_col}={_fmt(row[metric_col])}）" for _, row in ranked.iterrows()]
            lines.append(f"按 {metric_col} {label}排序，前 5 项为：" + "、".join(items) + "。")
        else:
            top = ranked.iloc[0]
            lines.append(f"{dim_col} 中 {label}的是 {top[dim_col]}，{metric_col} 为 {_fmt(top[metric_col])}。")

    if metric_col:
        total_like = any(term in metric_col.lower() for term in ("total", "gmv", "sales", "value", "orders", "transactions"))
        if total_like:
            lines.append(f"结果范围内 {metric_col} 合计约为 {_fmt(df[metric_col].sum())}。")
        else:
            lines.append(f"结果范围内 {metric_col} 平均约为 {_fmt(df[metric_col].mean())}。")

    if not lines:
        lines.append(f"查询返回 {len(df)} 行，但结果缺少可直接解释的数值字段；请查看数据预览获取明细。")

    return "\n".join(lines)


def _llm_business_summary(query: str, df: pd.DataFrame) -> str:
    sample_limit = 60
    sample = df.head(sample_limit).to_json(orient="records", force_ascii=False, date_format="iso")
    system = (
        "你是电商 BI 分析顾问。根据用户问题和 SQL 查询结果表，直接给业务答案。"
        "必须给出具体数字、排名或关键对象，不要只描述字段，不要输出查询策略。"
        "如果是排名问题，列出前5名及数值；如果是比例问题，给出百分比。"
        "严格区分数据中真实存在的指标和代理指标；若使用负面评价率近似退货风险，必须明确说明它不是实际退货率。"
        "不得从极少样本推断整体规律，不得编造 SQL 结果中不存在的具体数字或原因。"
        "当结果总行数大于提供的样例行数时，不得声称样例覆盖全部月份或全部对象。"
        "金额不要自行添加美元、人民币等币种单位；可直接称为GMV或金额。"
        "回答使用简体中文，控制在3-6句话。"
    )
    user = f"""
用户问题：{query}
结果总行数：{len(df)}
字段：{list(df.columns)}
结果样例（最多{sample_limit}行，已按SQL排序）：{sample}
"""
    return deepseek_chat(system, user, temperature=0.0).strip()


def _build_business_summary(query: str, df: pd.DataFrame) -> str:
    if any(k in query for k in ("预测", "未来6周", "未来 6 周")):
        if df.empty or "week_start" not in df.columns:
            return "预测输入序列不可用。"
        ordered = df.sort_values("week_start")
        return (
            f"预测查询获得周度预聚合序列，共 {len(ordered)} 周，"
            f"覆盖 {ordered.iloc[0]['week_start']} 至 {ordered.iloc[-1]['week_start']}。"
            "模型会自动选择连续历史并排除不完整边界周；最终预测值由稳健时间序列模型计算，不由 LLM 根据历史数据猜测。"
        )
    if any(k in query for k in ("重量", "尺寸", "运费")) and {
        "avg_weight_g", "avg_volume_cm3", "avg_freight"
    }.issubset(df.columns):
        ordered = df.sort_values("avg_weight_g")
        light = ordered.iloc[0]
        heavy = ordered.iloc[-1]
        return (
            "按重量分桶结果显示，商品重量和体积越大，平均运费总体越高。"
            f"最轻档 {light['weight_bucket']} 的平均重量约 {_fmt(light['avg_weight_g'])}g、"
            f"平均体积约 {_fmt(light['avg_volume_cm3'])}cm³、平均运费约 {_fmt(light['avg_freight'])}；"
            f"最重档 {heavy['weight_bucket']} 的平均重量约 {_fmt(heavy['avg_weight_g'])}g、"
            f"平均体积约 {_fmt(heavy['avg_volume_cm3'])}cm³、平均运费约 {_fmt(heavy['avg_freight'])}。"
            "该结果说明重量与尺寸均与运费相关，但分桶聚合只能说明关联，不能单独证明因果。"
        )
    if "退货率" in query and {
        "customer_state", "product_category_english", "negative_review_rate_pct", "review_count"
    }.issubset(df.columns):
        top = df.sort_values(["negative_review_rate_pct", "review_count"], ascending=[False, False]).head(5)
        items = [
            f"{row.customer_state}/{row.product_category_english}"
            f"（负面评价率 {_fmt(row.negative_review_rate_pct)}%，评价 {int(row.review_count)} 条）"
            for row in top.itertuples()
        ]
        return (
            "口径说明：Olist 当前数据没有实际退货/退款字段，以下使用低评分与负面评价率作为退货风险代理，"
            "不能等同于真实退货率。\n"
            "在评价数不少于20条的东北部州-品类组合中，风险代理指标最高的包括："
            + "、".join(items)
            + "。聚合数据尚不能判断高风险由商品质量、描述、物流或售后中的哪一项造成；"
              "应优先抽取这些组合的差评文本与订单履约明细，再针对高频原因开展整改。"
        )
    if "为什么" in query and "配送" in query and {
        "customer_state", "avg_delivery_days", "delay_rate_pct", "national_avg_delivery_days"
    }.issubset(df.columns):
        top = df.sort_values("avg_delivery_days", ascending=False).head(5)
        national = float(top.iloc[0]["national_avg_delivery_days"])
        items = [
            f"{row.customer_state}（平均 {_fmt(row.avg_delivery_days)} 天，"
            f"高于全国 {_fmt(national)} 天；延迟率 {_fmt(row.delay_rate_pct)}%）"
            for row in top.itertuples()
        ]
        return (
            "诊断说明：现有聚合数据可以识别关联因素，但不能单独证明因果关系。\n"
            "平均配送时长最高的州包括：" + "、".join(items)
            + "。其中部分州延迟率较高，但也有州平均配送时长很长而延迟率不高，"
              "说明平均配送时长不能仅由是否超过承诺日期解释；具体原因仍需结合物流商、路线、"
              "仓库处理时长和订单明细进一步验证。"
        )
    try:
        answer = _llm_business_summary(query, df)
        if answer and "字段" not in answer[:30] and "查询" not in answer[:20]:
            if "退货率" in query:
                return (
                    "口径说明：Olist 当前数据没有实际退货/退款字段，以下使用低评分与负面评价率作为退货风险代理，"
                    "不能等同于真实退货率。\n" + answer
                )
            if "为什么" in query and "配送" in query:
                return "诊断说明：现有聚合数据可以识别关联因素，但不能单独证明因果关系。\n" + answer
            return answer
    except Exception:
        pass
    return _heuristic_business_summary(query, df)


def choose_sql(query: str) -> tuple[str, str]:
    q = query.lower()
    state_match = re.search(r"customer_state=([A-Z]{2})", query)
    context_state = state_match.group(1) if state_match else ""
    year_match = re.search(r"(20\d{2})\s*年", query)
    year = year_match.group(1) if year_match else ""
    year_filter = f"WHERE `year_month` LIKE '{year}%'" if year else ""
    and_year_filter = f"AND `year_month` LIKE '{year}%'" if year else ""
    if any(k in q for k in ("预测", "未来6周", "未来 6 周")):
        return (
            "SELECT week_start, total_gmv, total_orders FROM mv_weekly_sales ORDER BY week_start",
            "mv_weekly_sales",
        )
    if any(k in q for k in ("地理", "地图", "气泡图", "区域分布")):
        return (
            "SELECT * FROM mv_state_geo_sales ORDER BY total_gmv DESC",
            "mv_state_geo_sales",
        )
    if any(k in q for k in ("差评", "评分", "评价", "满意", "评论")) and any(
        k in q for k in ("卖家", "下架", "what-if", "what if", "模拟")
    ):
        return (
            textwrap.dedent(
                """
                SELECT seller_id, total_orders, total_gmv, avg_review_score, negative_orders, delay_rate
                FROM mv_seller_review_risk
                WHERE total_orders >= 3
                ORDER BY avg_review_score ASC, negative_orders DESC
                LIMIT 20
                """
            ).strip(),
            "mv_seller_review_risk",
        )
    if "三大优先改进策略" in q or ("全部分析" in q and any(k in q for k in ("建议", "策略", "改进"))):
        return (
            textwrap.dedent(
                """
                WITH recent_complete AS (
                    SELECT `year_month`
                    FROM mv_monthly_sales
                    WHERE total_orders >= 1000
                    ORDER BY `year_month` DESC
                    LIMIT 3
                ),
                worst_delivery AS (
                    SELECT customer_state,
                           SUM(delayed_orders) / NULLIF(SUM(total_orders), 0) AS delay_rate
                    FROM mv_delivery_perf
                    GROUP BY customer_state
                    ORDER BY delay_rate DESC
                    LIMIT 1
                ),
                top_payment AS (
                    SELECT payment_type, SUM(total_transactions) AS transactions
                    FROM mv_payment_dist
                    GROUP BY payment_type
                    ORDER BY transactions DESC
                    LIMIT 1
                )
                SELECT m.`year_month`,
                       m.total_gmv,
                       m.total_orders,
                       m.avg_basket,
                       ROUND(100 * SUM(d.on_time_rate * d.total_orders) / NULLIF(SUM(d.total_orders), 0), 2)
                           AS on_time_rate_pct,
                       w.customer_state AS highest_delay_state,
                       ROUND(100 * w.delay_rate, 2) AS highest_delay_rate_pct,
                       p.payment_type AS top_payment_type
                FROM mv_monthly_sales m
                JOIN recent_complete rc ON m.`year_month` = rc.`year_month`
                JOIN mv_delivery_perf d ON d.`year_month` = m.`year_month`
                CROSS JOIN worst_delivery w
                CROSS JOIN top_payment p
                GROUP BY m.`year_month`, m.total_gmv, m.total_orders, m.avg_basket,
                         w.customer_state, w.delay_rate, p.payment_type
                ORDER BY m.`year_month`
                """
            ).strip(),
            "mv_*",
        )
    if any(k in q for k in ("退货率", "东北部")):
        return (
            textwrap.dedent(
                """
                SELECT customer_state,
                       product_category_english,
                       SUM(review_count) AS review_count,
                       ROUND(SUM(avg_review_score * review_count) / NULLIF(SUM(review_count), 0), 2)
                           AS avg_review_score,
                       ROUND(100 * SUM(negative_review_rate * review_count) / NULLIF(SUM(review_count), 0), 2)
                           AS negative_review_rate_pct
                FROM mv_review_quality
                WHERE customer_state IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE')
                GROUP BY customer_state, product_category_english
                HAVING SUM(review_count) >= 20
                ORDER BY negative_review_rate_pct DESC, review_count DESC
                LIMIT 30
                """
            ).strip(),
            "mv_review_quality",
        )
    if any(k in q for k in ("gmv", "销售额")) and year and "州" not in q:
        if any(k in q for k in ("按月", "趋势")):
            return (
                f"SELECT `year_month`, total_gmv, total_orders FROM mv_monthly_sales {year_filter} ORDER BY `year_month`",
                "mv_monthly_sales",
            )
        return (
            f"SELECT SUM(total_gmv) AS total_gmv, SUM(total_orders) AS total_orders FROM mv_monthly_sales {year_filter}",
            "mv_monthly_sales",
        )
    if "州" in q and any(k in q for k in ("销售", "gmv", "订单", "排名")):
        if any(k in q for k in ("按月", "趋势")):
            return (
                textwrap.dedent(
                    f"""
                    SELECT s.`year_month`, s.customer_state, s.total_gmv, s.total_orders
                    FROM mv_state_sales s
                    JOIN (
                        SELECT customer_state, SUM(total_gmv) AS annual_gmv
                        FROM mv_state_sales
                        {year_filter}
                        GROUP BY customer_state
                        ORDER BY annual_gmv DESC
                        LIMIT 5
                    ) top_states ON s.customer_state = top_states.customer_state
                    {year_filter.replace('`year_month`', 's.`year_month`')}
                    ORDER BY s.`year_month`, s.total_gmv DESC
                    """
                ).strip(),
                "mv_state_sales",
            )
        return (
            textwrap.dedent(
                f"""
                SELECT customer_state, SUM(total_gmv) AS total_gmv, SUM(total_orders) AS total_orders
                FROM mv_state_sales
                {year_filter}
                GROUP BY customer_state
                ORDER BY total_gmv DESC
                LIMIT 15
                """
            ).strip(),
            "mv_state_sales",
        )
    if any(k in q for k in ("差评", "评分", "评价", "满意", "评论")):
        if any(k in q for k in ("卖家", "下架", "what-if", "what if", "模拟")):
            return (
                textwrap.dedent(
                    """
                    SELECT seller_id, total_orders, total_gmv, avg_review_score, negative_orders, delay_rate
                    FROM mv_seller_review_risk
                    WHERE total_orders >= 3
                    ORDER BY avg_review_score ASC, negative_orders DESC
                    LIMIT 20
                    """
                ).strip(),
                "mv_seller_review_risk",
            )
        return (
            textwrap.dedent(
                """
                SELECT customer_state,
                       product_category_english,
                       AVG(avg_review_score) AS avg_review_score,
                       AVG(negative_review_rate) AS negative_review_rate,
                       SUM(review_count) AS review_count
                FROM mv_review_quality
                GROUP BY customer_state, product_category_english
                ORDER BY negative_review_rate DESC, review_count DESC
                LIMIT 30
                """
            ).strip(),
            "mv_review_quality",
        )
    if any(k in q for k in ("地理", "地图", "气泡图", "区域分布")):
        return (
            "SELECT * FROM mv_state_geo_sales ORDER BY total_gmv DESC",
            "mv_state_geo_sales",
        )
    if any(k in q for k in ("支付", "分期")):
        if "分期" in q and any(k in q for k in ("矩阵", "交叉", "热力", "分布")):
            return (
                "SELECT * FROM mv_payment_installment_matrix ORDER BY payment_type, payment_installments",
                "mv_payment_installment_matrix",
            )
        if context_state:
            purchase_year_filter = f"AND YEAR(o.order_purchase_timestamp) = {year}" if year else ""
            return (
                textwrap.dedent(
                    f"""
                    SELECT
                        op.payment_type,
                        COUNT(*) AS total_transactions,
                        AVG(op.payment_installments) AS avg_installments,
                        SUM(op.payment_value) AS total_value
                    FROM order_payments op
                    JOIN orders o ON op.order_id = o.order_id
                    JOIN customers c ON o.customer_id = c.customer_id
                    WHERE c.customer_state = '{context_state}'
                    {purchase_year_filter}
                    GROUP BY op.payment_type
                    ORDER BY total_transactions DESC
                    LIMIT 20
                    """
                ).strip(),
                "base",
            )
        if "平均分期" in q or ("分期数" in q and not any(k in q for k in ("矩阵", "交叉", "热力", "分布"))):
            return (
                textwrap.dedent(
                    f"""
                    SELECT payment_type,
                           SUM(total_transactions) AS total_transactions,
                           ROUND(SUM(avg_installments * total_transactions) / NULLIF(SUM(total_transactions), 0), 2)
                               AS avg_installments,
                           (
                               SELECT ROUND(SUM(avg_installments * total_transactions)
                                      / NULLIF(SUM(total_transactions), 0), 2)
                               FROM mv_payment_dist
                               WHERE 1=1 {and_year_filter}
                           ) AS overall_avg_installments
                    FROM mv_payment_dist
                    {year_filter}
                    GROUP BY payment_type
                    ORDER BY avg_installments DESC
                    """
                ).strip(),
                "mv_payment_dist",
            )
        return (
            textwrap.dedent(
                f"""
                SELECT payment_type,
                       SUM(total_transactions) AS total_transactions,
                       SUM(total_value) AS total_value
                FROM mv_payment_dist
                {year_filter}
                GROUP BY payment_type
                ORDER BY total_transactions DESC
                """
            ).strip(),
            "mv_payment_dist",
        )
    if any(k in q for k in ("配送", "准时", "延迟")):
        if "全国均值" in q or ("为什么" in q and "配送" in q):
            return (
                textwrap.dedent(
                    f"""
                    SELECT customer_state,
                           ROUND(SUM(avg_delivery_days * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               AS avg_delivery_days,
                           ROUND(100 * SUM((1 - on_time_rate) * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               AS delay_rate_pct,
                           SUM(total_orders) AS total_orders,
                           (
                               SELECT ROUND(SUM(avg_delivery_days * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               FROM mv_delivery_perf
                               WHERE 1=1 {and_year_filter}
                           ) AS national_avg_delivery_days
                    FROM mv_delivery_perf
                    WHERE 1=1 {and_year_filter}
                    GROUP BY customer_state
                    HAVING SUM(total_orders) >= 50
                    ORDER BY avg_delivery_days DESC
                    LIMIT 15
                    """
                ).strip(),
                "mv_delivery_perf",
            )
        if "整体" in q and not any(k in q for k in ("哪些州", "哪个州", "最严重")):
            return (
                textwrap.dedent(
                    f"""
                    SELECT ROUND(100 * SUM(on_time_rate * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               AS overall_on_time_rate_pct,
                           SUM(total_orders) AS total_orders
                    FROM mv_delivery_perf
                    WHERE 1=1 {and_year_filter}
                    """
                ).strip(),
                "mv_delivery_perf",
            )
        if context_state:
            return (
                textwrap.dedent(
                    f"""
                    SELECT customer_state,
                           ROUND(100 * SUM(on_time_rate * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               AS on_time_rate_pct,
                           ROUND(SUM(avg_delivery_days * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                               AS avg_delivery_days,
                           SUM(delayed_orders) AS delayed_orders,
                           SUM(total_orders) AS total_orders
                    FROM mv_delivery_perf
                    WHERE customer_state = '{context_state}' {and_year_filter}
                    GROUP BY customer_state
                    """
                ).strip(),
                "mv_delivery_perf",
            )
        return (
            textwrap.dedent(
                f"""
                SELECT customer_state,
                    ROUND(100 * SUM((1 - on_time_rate) * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                        AS delay_rate_pct,
                    ROUND(SUM(avg_delivery_days * total_orders) / NULLIF(SUM(total_orders), 0), 2)
                        AS avg_delivery_days,
                    SUM(delayed_orders) AS delayed_orders,
                    SUM(total_orders) AS total_orders
                FROM mv_delivery_perf d
                WHERE 1=1 {and_year_filter}
                GROUP BY customer_state
                ORDER BY delay_rate_pct DESC, delayed_orders DESC
                LIMIT 15
                """
            ).strip(),
            "mv_delivery_perf",
        )
    if any(k in q for k in ("品类", "类目", "category")):
        return (
            "SELECT * FROM mv_category_sales ORDER BY `year_month` DESC, total_gmv DESC LIMIT 200",
            "mv_category_sales",
        )
    if any(k in q for k in ("重量", "运费", "尺寸")):
        return (
            "SELECT * FROM mv_weight_freight_bucket ORDER BY avg_weight_g",
            "mv_weight_freight_bucket",
        )
    return (
        "SELECT * FROM mv_monthly_sales ORDER BY `year_month` ASC",
        "mv_monthly_sales",
    )


def data_analyst_node(state: AgentState) -> AgentState:
    original_query = state.get("user_query", "")
    first_query = original_query
    first_context_note = ""
    sub_queries = _split_compound_questions(first_query)
    print(f"[data_analyst] node start: query={original_query[:120]}", flush=True)
    print(f"[data_analyst] split questions: {len(sub_queries)}", flush=True)

    sql_queries: list[str] = []
    summaries: list[str] = []
    strategies: list[str] = []
    data_results: list[dict] = []
    last_rows: list[dict] = []
    last_columns: list[str] = []
    last_preview_rows: list[dict] = []
    last_preview_columns: list[str] = []
    last_row_count = 0
    context_notes: list[str] = []

    for idx, raw_sub_query in enumerate(sub_queries, start=1):
        query = raw_sub_query
        context_note = ""
        if idx == 1:
            query = raw_sub_query
            context_note = first_context_note
        elif last_rows and last_columns:
            query, context_note = _resolve_context_from_rows(raw_sub_query, last_rows, last_columns)

        print(f"[data_analyst] sub-question {idx}/{len(sub_queries)} start: {query[:120]}", flush=True)
        if context_note:
            print(f"[data_analyst] sub-question {idx} context resolved: {context_note}", flush=True)
            context_notes.append(f"问题{idx}: {context_note}")

        sql, source, reason = _select_sql_for_query(query)
        df, sql, source, reason = _execute_sql_with_fallback(query, sql, source, reason)
        summary = _build_business_summary(query, df)
        rows, columns, row_count = _serializable_preview(df)

        sql_queries.append(sql)
        summaries.append(f"问题{idx}：{raw_sub_query}\n{summary}")
        strategy = f"问题{idx} 数据源：{source}；查询策略：{reason}"
        strategies.append(strategy)
        data_results.append(
            {
                "question": raw_sub_query,
                "resolved_query": query,
                "sql": sql,
                "source": source,
                "rows": rows,
                "columns": columns,
                "row_count": row_count,
            }
        )

        last_rows = rows
        last_columns = columns
        last_preview_rows = rows
        last_preview_columns = columns
        last_row_count = row_count
        print(f"[data_analyst] sub-question {idx} done: row_count={row_count}", flush=True)

    summary = "\n\n".join(summaries)
    query_strategy = "；".join(strategies)
    if context_notes:
        query_strategy = f"{query_strategy}；上下文解析：{'；'.join(context_notes)}"
    total_row_count = sum(int(item.get("row_count", 0)) for item in data_results)
    print(f"[data_analyst] node done: queries={len(sql_queries)}, total_row_count={total_row_count}", flush=True)
    return {
        "sql_queries": sql_queries,
        "data_summary": summary,
        "final_answer": summary,
        "query_strategy": query_strategy,
        "resolved_query": first_query,
        "context_note": "；".join(context_notes),
        "data_rows": last_preview_rows,
        "data_columns": last_preview_columns,
        "data_results": data_results,
        "data_row_count": total_row_count,
    }
