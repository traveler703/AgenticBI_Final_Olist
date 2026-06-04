from pathlib import Path

import pandas as pd

from agents.coordinator import coordinator_node
from agents.data_analyst import (
    _build_business_summary,
    _resolve_context_from_rows,
    _split_compound_questions,
    choose_sql,
    data_analyst_node,
)
from agents.decision import decision_node
from agents.visualizer import generate_query_charts
from models.sentiment import score_review_text


ROOT = Path(__file__).resolve().parents[1]


def test_review_text_sentiment_uses_comment_words() -> None:
    positive, positive_subjectivity, _, _ = score_review_text("Produto excelente, perfeito e recomendo")
    negative, negative_subjectivity, _, _ = score_review_text("Produto ruim, atrasado e quebrado")

    assert positive > 0
    assert negative < 0
    assert positive_subjectivity > 0
    assert negative_subjectivity > 0


def test_coordinator_routes_comment_questions_to_nlp() -> None:
    state = coordinator_node({"user_query": "分析差评评论的情感和关键词，并给出优化建议"})

    assert state["need_nlp"] is True
    assert state["need_decision"] is True
    assert "评论文本洞察" in state["plan_steps"]
    assert "决策建议" in state["plan_steps"]


def test_decision_has_actionable_fallback_without_llm(monkeypatch) -> None:
    def fail_llm(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("agents.decision.deepseek_chat", fail_llm)
    result = decision_node(
        {
            "user_query": "如何优化平台运营？",
            "analysis_type": "prescriptive",
            "need_decision": True,
            "data_summary": "配送延迟州已识别。",
            "nlp_insights": "负向主题集中在延迟和破损。",
        }
    )

    assert "物流" in result["decision_advice"]
    assert "卖家" in result["decision_advice"]
    assert "建议：" in result["final_answer"]


def test_extended_preaggregations_and_visualizations_are_registered() -> None:
    sql = (ROOT / "utils" / "sql" / "create_materialized_views.sql").read_text(encoding="utf-8")
    visualizer = (ROOT / "agents" / "visualizer.py").read_text(encoding="utf-8")
    graph = (ROOT / "agents" / "graph.py").read_text(encoding="utf-8")

    for table in ("mv_payment_installment_matrix", "mv_weight_freight_bucket", "mv_state_geo_sales"):
        assert f"CREATE TABLE {table} AS" in sql
    assert "chart_state_geo_bubble.png" in visualizer
    assert "chart_review_topics.png" in visualizer
    assert 'graph.add_node("nlp_insights", nlp_insights_node)' in graph


def test_specialized_visual_queries_use_preaggregations() -> None:
    _, payment_source = choose_sql("支付方式与分期数交叉矩阵")
    _, geo_source = choose_sql("展示州级销售额地理气泡图")
    _, weight_source = choose_sql("分析商品重量和运费关系")
    _, whatif_source = choose_sql("如果下架 Top 20 高差评卖家，并扫描州级订单异常")

    assert payment_source == "mv_payment_installment_matrix"
    assert geo_source == "mv_state_geo_sales"
    assert weight_source == "mv_weight_freight_bucket"
    assert whatif_source == "mv_seller_review_risk"


def test_visualizer_generates_only_query_relevant_chart(monkeypatch) -> None:
    monkeypatch.setattr("agents.visualizer._plot_bar", lambda *args, **kwargs: "dynamic/state_bar.png")
    state = {
        "user_query": "2017年各州销售额排名怎样？",
        "data_results": [
            {
                "question": "2017年各州销售额排名怎样？",
                "source": "mv_state_sales",
                "columns": ["customer_state", "total_gmv"],
                "rows": [
                    {"customer_state": "SP", "total_gmv": 100.0},
                    {"customer_state": "RJ", "total_gmv": 60.0},
                ],
            }
        ],
    }

    paths, titles, strategy = generate_query_charts(state)

    assert paths == ["dynamic/state_bar.png"]
    assert len(titles) == 1
    assert "各州销售额" in titles[0]
    assert "柱状图" in strategy


def test_visualizer_uses_topic_chart_for_comment_query(monkeypatch) -> None:
    monkeypatch.setattr("agents.visualizer._plot_review_topics_from_state", lambda *args, **kwargs: "dynamic/topics.png")
    state = {
        "user_query": "分析差评评论关键词",
        "need_nlp": True,
        "nlp_result": {"negative_keywords": [{"term": "defeito", "count": 3}]},
        "data_results": [
            {
                "question": "分析差评评论关键词",
                "source": "base",
                "columns": ["order_id", "review_score", "review_comment_message"],
                "rows": [{"order_id": "1", "review_score": 1, "review_comment_message": "defeito"}],
            }
        ],
    }

    paths, titles, strategy = generate_query_charts(state)

    assert paths == ["dynamic/topics.png"]
    assert len(titles) == 1
    assert "评论主题关键词" in titles[0]
    assert "评论文本洞察" in strategy


def test_forecast_query_avoids_duplicate_monthly_chart(monkeypatch) -> None:
    monkeypatch.setattr("agents.visualizer._plot_forecast", lambda *args, **kwargs: "dynamic/forecast.png")
    state = {
        "user_query": "预测未来6周销售额",
        "need_forecast": True,
        "data_results": [
            {
                "question": "预测未来6周销售额",
                "source": "mv_weekly_sales",
                "columns": ["week_start", "total_gmv"],
                "rows": [{"week_start": "2018-01-01", "total_gmv": 100.0}],
            }
        ],
    }

    paths, titles, strategy = generate_query_charts(state)

    assert paths == ["dynamic/forecast.png"]
    assert len(titles) == 1
    assert "预测" in strategy


def test_visualizer_passes_requested_forecast_horizon(monkeypatch) -> None:
    called = {}

    def fake_plot(title, filename, weeks):
        called["weeks"] = weeks
        return "dynamic/forecast.png"

    monkeypatch.setattr("agents.visualizer._plot_forecast", fake_plot)
    generate_query_charts({"user_query": "预测未来10周销售额", "need_forecast": True, "data_results": []})

    assert called["weeks"] == 10


def test_dashboard_does_not_fallback_to_fixed_charts_after_query() -> None:
    dashboard = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    queried_chart_block = dashboard.split('chart_paths = normalize_chart_paths(last.get("chart_paths", []))', 1)[1]

    assert "chart_paths = list_existing_chart_paths()" not in queried_chart_block
    assert 'chart_titles = last.get("chart_titles") or []' in queried_chart_block


def test_dashboard_has_no_default_chart_button() -> None:
    dashboard = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")

    assert "生成默认图表" not in dashboard
    assert "build_default_charts" not in dashboard


def test_dashboard_run_agent_keeps_thread_id_keyword_compatibility() -> None:
    dashboard = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")

    assert "def run_agent(query: str, thread_id: str)" in dashboard
    assert 'config={"configurable": {"thread_id": thread_id}}' not in dashboard


def test_validation_queries_use_distinct_aggregated_sql() -> None:
    popular_sql, popular_source = choose_sql("哪种支付方式最受欢迎")
    installments_sql, installments_source = choose_sql("平均分期数是多少")
    strategy_sql, strategy_source = choose_sql("基于全部分析结果，给出平台 3 个月内的三大优先改进策略")
    return_risk_sql, return_risk_source = choose_sql("如何降低巴西东北部地区的高退货率")

    assert popular_sql != installments_sql
    assert "GROUP BY payment_type" in popular_sql
    assert "overall_avg_installments" in installments_sql
    assert popular_source == installments_source == "mv_payment_dist"
    assert "recent_complete" in strategy_sql
    assert strategy_source == "mv_*"
    assert "negative_review_rate_pct" in return_risk_sql
    assert return_risk_source == "mv_review_quality"


def test_compound_questions_keep_year_and_merge_advice_request() -> None:
    year_parts = _split_compound_questions("2017年哪个州销售额最高？交付准时率是多少？哪种支付方式最受欢迎？")
    advice_parts = _split_compound_questions("如何降低东北部高退货率？请给出具体运营方案。")

    assert all(part.startswith("2017年") for part in year_parts)
    assert len(advice_parts) == 1


def test_state_context_is_applied_to_implicit_followup() -> None:
    resolved, note = _resolve_context_from_rows(
        "2017年交付准时率是多少",
        [{"customer_state": "SP", "total_gmv": 100.0}, {"customer_state": "RJ", "total_gmv": 60.0}],
        ["customer_state", "total_gmv"],
    )

    assert "customer_state=SP" in resolved
    assert note == "customer_state=SP"


def test_new_turn_does_not_inherit_previous_result_context(monkeypatch) -> None:
    payment_df = pd.DataFrame([{"payment_type": "credit_card", "total_transactions": 10}])

    monkeypatch.setattr(
        "agents.data_analyst._select_sql_for_query",
        lambda query: ("SELECT 1", "mv_payment_dist", "test"),
    )
    monkeypatch.setattr(
        "agents.data_analyst._execute_sql_with_fallback",
        lambda query, sql, source, reason: (payment_df, sql, source, reason),
    )
    monkeypatch.setattr("agents.data_analyst._build_business_summary", lambda query, df: "ok")

    result = data_analyst_node(
        {
            "user_query": "哪种支付方式最受欢迎？平均分期数是多少？",
            "data_rows": [{"customer_state": "SP", "total_gmv": 100.0}],
            "data_columns": ["customer_state", "total_gmv"],
        }
    )

    assert len(result["data_results"]) == 2
    assert "customer_state=SP" not in result["query_strategy"]
    assert all("customer_state=SP" not in item["resolved_query"] for item in result["data_results"])


def test_weight_view_contains_size_and_volume_fields() -> None:
    sql = (ROOT / "utils" / "sql" / "create_materialized_views.sql").read_text(encoding="utf-8")

    assert "AVG(product_length_cm)" in sql
    assert "avg_volume_cm3" in sql


def test_payment_charts_use_question_specific_metrics(monkeypatch) -> None:
    metrics = []

    def fake_bar(df, x, y, title, filename):
        metrics.append(y)
        return f"dynamic/{filename}"

    monkeypatch.setattr("agents.visualizer._plot_bar", fake_bar)
    rows = [
        {"payment_type": "credit_card", "total_transactions": 10, "avg_installments": 3.5},
        {"payment_type": "boleto", "total_transactions": 4, "avg_installments": 1.0},
    ]
    generate_query_charts(
        {
            "user_query": "哪种支付方式最受欢迎？平均分期数是多少？",
            "data_results": [
                {
                    "question": "哪种支付方式最受欢迎",
                    "source": "mv_payment_dist",
                    "columns": list(rows[0]),
                    "rows": rows,
                },
                {
                    "question": "平均分期数是多少",
                    "source": "mv_payment_dist",
                    "columns": list(rows[0]),
                    "rows": rows,
                },
            ],
        }
    )

    assert metrics == ["total_transactions", "avg_installments"]


def test_delivery_charts_use_question_specific_metrics(monkeypatch) -> None:
    metrics = []

    def fake_bar(df, x, y, title, filename):
        metrics.append(y)
        return f"dynamic/{filename}"

    monkeypatch.setattr("agents.visualizer._plot_bar", fake_bar)
    rows = [
        {
            "customer_state": "AL",
            "delay_rate_pct": 23.99,
            "avg_delivery_days": 24.2,
            "delayed_orders": 103,
            "total_orders": 700,
        },
        {
            "customer_state": "MA",
            "delay_rate_pct": 19.80,
            "avg_delivery_days": 21.4,
            "delayed_orders": 163,
            "total_orders": 900,
        },
    ]
    questions = [
        "哪些州的派送延迟时间最长",
        "哪些州延迟最严重",
        "哪些州的延迟订单最多",
    ]
    generate_query_charts(
        {
            "user_query": "？".join(questions),
            "data_results": [
                {
                    "question": question,
                    "source": "mv_delivery_perf",
                    "columns": list(rows[0]),
                    "rows": rows,
                }
                for question in questions
            ],
        }
    )

    assert metrics == ["avg_delivery_days", "delay_rate_pct", "delayed_orders"]


def test_proxy_and_diagnostic_summaries_do_not_claim_unsupported_causes() -> None:
    risk_summary = _build_business_summary(
        "如何降低巴西东北部地区的高退货率",
        pd.DataFrame(
            [
                {
                    "customer_state": "RN",
                    "product_category_english": "perfumery",
                    "negative_review_rate_pct": 42.86,
                    "review_count": 21,
                }
            ]
        ),
    )
    delivery_summary = _build_business_summary(
        "为什么某些州的平均配送时长显著高于全国均值",
        pd.DataFrame(
            [
                {
                    "customer_state": "AP",
                    "avg_delivery_days": 28.33,
                    "delay_rate_pct": 12.0,
                    "national_avg_delivery_days": 12.43,
                }
            ]
        ),
    )

    assert "不能等同于真实退货率" in risk_summary
    assert "尚不能判断" in risk_summary
    assert "不能单独证明因果关系" in delivery_summary
    assert "进一步验证" in delivery_summary
