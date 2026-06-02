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
    "mv_state_sales",
    "mv_category_sales",
    "mv_delivery_perf",
    "mv_payment_dist",
    "mv_review_quality",
    "mv_seller_review_risk",
]

DATA_DICTIONARY = """
预聚合视图优先：
- mv_monthly_sales(`year_month`, total_gmv, total_orders, avg_basket, total_freight)
- mv_state_sales(`year_month`, customer_state, total_gmv, total_orders, unique_customers)
- mv_category_sales(`year_month`, product_category_english, total_gmv, total_orders, avg_price)
- mv_delivery_perf(`year_month`, customer_state, avg_delivery_days, on_time_rate, delayed_orders, total_orders)
- mv_payment_dist(`year_month`, payment_type, total_transactions, avg_installments, total_value)
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
    return parts[:5]


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
{{"sql": "SELECT ...", "source": "mv_monthly_sales|mv_state_sales|mv_category_sales|mv_delivery_perf|mv_payment_dist|mv_review_quality|mv_seller_review_risk|fact_order_items|base", "reason": "命中原因"}}
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
    keywords = ("准时", "延迟", "配送", "交付", "交付率", "支付", "分期", "重量", "运费")
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


def _resolve_context_query(state: AgentState) -> tuple[str, str]:
    """用上一轮结果解析“这个州/排名第一/这些州”等追问指代。"""
    query = state.get("user_query", "")
    rows = state.get("data_rows") or []
    columns = state.get("data_columns") or []
    return _resolve_context_from_rows(query, rows, columns)


def _resolve_context_from_rows(query: str, rows: list[dict], columns: list[str]) -> tuple[str, str]:
    """基于给定结果表解析当前问句中的指代，用于跨轮追问和同轮多问。"""
    if not rows or not columns:
        return query, ""

    q = query.lower()
    trigger_terms = ("这个", "该", "上述", "上面", "刚才", "排名第一", "第一名", "这些", "它们", "该州", "这个州")
    if not any(term in q for term in trigger_terms):
        return query, ""

    df = pd.DataFrame(rows, columns=columns)
    dim_col = _preferred_dimension_column(df)
    metric_col = _preferred_metric_column(df)
    if not dim_col:
        return query, ""

    context_items: list[str] = []
    if "排名第一" in q or "第一名" in q or "这个" in q or "该" in q:
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
    sample = df.head(30).to_json(orient="records", force_ascii=False, date_format="iso")
    system = (
        "你是电商 BI 分析顾问。根据用户问题和 SQL 查询结果表，直接给业务答案。"
        "必须给出具体数字、排名或关键对象，不要只描述字段，不要输出查询策略。"
        "如果是排名问题，列出前5名及数值；如果是比例问题，给出百分比。"
        "回答使用简体中文，控制在3-6句话。"
    )
    user = f"""
用户问题：{query}
结果总行数：{len(df)}
字段：{list(df.columns)}
结果样例（最多30行，已按SQL排序）：{sample}
"""
    return deepseek_chat(system, user, temperature=0.0).strip()


def _build_business_summary(query: str, df: pd.DataFrame) -> str:
    try:
        answer = _llm_business_summary(query, df)
        if answer and "字段" not in answer[:30] and "查询" not in answer[:20]:
            return answer
    except Exception:
        pass
    return _heuristic_business_summary(query, df)


def choose_sql(query: str) -> tuple[str, str]:
    q = query.lower()
    state_match = re.search(r"customer_state=([A-Z]{2})", query)
    context_state = state_match.group(1) if state_match else ""
    if "州" in q and any(k in q for k in ("销售", "gmv", "订单")):
        return (
            "SELECT * FROM mv_state_sales ORDER BY `year_month` DESC, total_gmv DESC LIMIT 200",
            "mv_state_sales",
        )
    if any(k in q for k in ("支付", "分期")):
        if context_state:
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
                    GROUP BY op.payment_type
                    ORDER BY total_transactions DESC
                    LIMIT 20
                    """
                ).strip(),
                "base",
            )
        return (
            "SELECT * FROM mv_payment_dist ORDER BY `year_month` DESC, total_transactions DESC LIMIT 200",
            "mv_payment_dist",
        )
    if any(k in q for k in ("配送", "准时", "延迟")):
        state_filter = f"AND d.customer_state = '{context_state}'" if context_state else ""
        return (
            textwrap.dedent(
                f"""
                SELECT
                    d.customer_state,
                    ROUND(d.on_time_rate * 100, 2) AS on_time_rate_pct,
                    ROUND((1 - d.on_time_rate) * 100, 2) AS delay_rate_pct,
                    d.avg_delivery_days,
                    d.delayed_orders,
                    d.`year_month`,
                    (
                        SELECT ROUND(AVG(on_time_rate) * 100, 2)
                        FROM mv_delivery_perf
                        WHERE `year_month` = (SELECT MAX(`year_month`) FROM mv_delivery_perf)
                    ) AS overall_on_time_rate_pct
                FROM mv_delivery_perf d
                WHERE d.`year_month` = (SELECT MAX(`year_month`) FROM mv_delivery_perf)
                {state_filter}
                ORDER BY d.on_time_rate ASC, d.delayed_orders DESC
                LIMIT 15
                """
            ).strip(),
            "mv_delivery_perf",
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
    if any(k in q for k in ("品类", "类目", "category")):
        return (
            "SELECT * FROM mv_category_sales ORDER BY `year_month` DESC, total_gmv DESC LIMIT 200",
            "mv_category_sales",
        )
    if any(k in q for k in ("重量", "运费", "尺寸")):
        return (
            textwrap.dedent(
                """
                SELECT
                    product_weight_g,
                    AVG(freight_value) AS avg_freight,
                    COUNT(*) AS order_cnt,
                    AVG(shipping_duration_days) AS avg_delivery_days
                FROM fact_order_items
                WHERE product_weight_g IS NOT NULL
                GROUP BY product_weight_g
                ORDER BY order_cnt DESC
                LIMIT 500
                """
            ).strip(),
            "fact_order_items",
        )
    return (
        "SELECT * FROM mv_monthly_sales ORDER BY `year_month` ASC",
        "mv_monthly_sales",
    )


def data_analyst_node(state: AgentState) -> AgentState:
    original_query = state.get("user_query", "")
    first_query, first_context_note = _resolve_context_query(state)
    sub_queries = _split_compound_questions(first_query)
    print(f"[data_analyst] node start: query={original_query[:120]}", flush=True)
    print(f"[data_analyst] split questions: {len(sub_queries)}", flush=True)

    sql_queries: list[str] = []
    summaries: list[str] = []
    strategies: list[str] = []
    data_results: list[dict] = []
    last_rows: list[dict] = state.get("data_rows") or []
    last_columns: list[str] = state.get("data_columns") or []
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
