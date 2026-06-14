"""数据质量校验：外键零孤儿、关键行数、口径抽样、刷新一致性。

运行：cd data_layer && python -m pytest tests/ -v
需先完成 python -m utils.init_db。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import get_settings

MATERIALIZED_VIEWS = [
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

VIEW_GRAINS = {
    "mv_monthly_sales": "`year_month`",
    "mv_weekly_sales": "week_start",
    "mv_state_sales": "`year_month`, customer_state",
    "mv_category_sales": "`year_month`, product_category_english",
    "mv_delivery_perf": "`year_month`, customer_state",
    "mv_payment_dist": "`year_month`, payment_type",
    "mv_payment_installment_matrix": "payment_type, payment_installments",
    "mv_weight_freight_bucket": "weight_bucket",
    "mv_state_geo_sales": "customer_state",
    "mv_review_quality": "`year_month`, customer_state, product_category_english",
    "mv_seller_review_risk": "seller_id",
}


@pytest.fixture(scope="module")
def conn():
    engine = create_engine(get_settings().ro_url, pool_pre_ping=True)
    with engine.connect() as c:
        yield c


def _scalar(conn, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


def _number(conn, sql: str) -> float:
    return float(conn.execute(text(sql)).scalar() or 0)


def _assert_close(actual: float, expected: float) -> None:
    assert abs(actual - expected) <= max(1.0, abs(expected) * 1e-6)


def test_row_counts(conn):
    assert _scalar(conn, "SELECT COUNT(*) FROM orders") > 99_000
    assert _scalar(conn, "SELECT COUNT(*) FROM order_items") > 112_000
    assert _scalar(conn, "SELECT COUNT(*) FROM order_reviews") > 99_000


def test_no_orphan_order_items(conn):
    orphans = _scalar(
        conn,
        "SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o ON oi.order_id=o.order_id WHERE o.order_id IS NULL",
    )
    assert orphans == 0


def test_no_orphan_orders_customer(conn):
    orphans = _scalar(
        conn,
        "SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL",
    )
    assert orphans == 0


def test_review_score_range(conn):
    bad = _scalar(conn, "SELECT COUNT(*) FROM order_reviews WHERE review_score NOT BETWEEN 1 AND 5")
    assert bad == 0  # 越界已在清洗阶段置 NULL


def test_mv_consistency_gmv(conn):
    base = _number(conn, "SELECT SUM(item_gmv) FROM fact_order_items")
    for view in ("mv_monthly_sales", "mv_weekly_sales", "mv_state_sales", "mv_category_sales"):
        _assert_close(_number(conn, f"SELECT SUM(total_gmv) FROM {view}"), base)


def test_refresh_log_written(conn):
    rows = conn.execute(
        text(
            "SELECT mv_name FROM mv_refresh_log "
            "WHERE LEFT(mv_name, 3) = 'mv_' "
            "ORDER BY id DESC LIMIT 11"
        )
    ).scalars().all()
    assert len(rows) == 11
    assert set(rows) == set(MATERIALIZED_VIEWS)


@pytest.mark.parametrize("view", MATERIALIZED_VIEWS)
def test_all_materialized_views_present_and_nonempty(conn, view):
    assert _scalar(conn, f"SELECT COUNT(*) FROM {view}") > 0


@pytest.mark.parametrize("view,grain", VIEW_GRAINS.items())
def test_materialized_view_grain_is_unique(conn, view, grain):
    duplicates = _scalar(
        conn,
        f"SELECT COUNT(*) FROM ("
        f"SELECT {grain}, COUNT(*) n FROM {view} GROUP BY {grain} HAVING COUNT(*) > 1"
        f") duplicated_grains",
    )
    assert duplicates == 0


def test_delivery_preaggregation_is_order_grain(conn):
    mv_orders = _scalar(conn, "SELECT SUM(total_orders) FROM mv_delivery_perf")
    base_orders = _scalar(
        conn,
        "SELECT COUNT(DISTINCT order_id) FROM fact_order_items "
        "WHERE shipping_duration_days IS NOT NULL",
    )
    assert mv_orders == base_orders
    assert _scalar(
        conn,
        "SELECT COUNT(*) FROM mv_delivery_perf "
        "WHERE on_time_rate NOT BETWEEN 0 AND 1 "
        "OR delayed_orders < 0 OR delayed_orders > total_orders",
    ) == 0


def test_payment_preaggregations_match_base(conn):
    base = _number(
        conn,
        "SELECT SUM(op.payment_value) FROM order_payments op "
        "JOIN orders o ON op.order_id=o.order_id "
        "WHERE o.order_purchase_timestamp IS NOT NULL",
    )
    _assert_close(_number(conn, "SELECT SUM(total_value) FROM mv_payment_dist"), base)
    _assert_close(_number(conn, "SELECT SUM(total_value) FROM mv_payment_installment_matrix"), base)


def test_weight_bucket_matches_fact_rows(conn):
    assert _scalar(conn, "SELECT SUM(order_cnt) FROM mv_weight_freight_bucket") == _scalar(
        conn,
        "SELECT COUNT(*) FROM fact_order_items WHERE product_weight_g IS NOT NULL",
    )


def test_geo_preaggregation_matches_covered_states(conn):
    mv = _number(conn, "SELECT SUM(total_gmv) FROM mv_state_geo_sales")
    base = _number(
        conn,
        "SELECT SUM(s.total_gmv) FROM mv_state_sales s "
        "WHERE EXISTS ("
        "SELECT 1 FROM geolocation g "
        "WHERE g.geolocation_state=s.customer_state "
        "AND g.geolocation_lat BETWEEN -35 AND 6 "
        "AND g.geolocation_lng BETWEEN -75 AND -30)",
    )
    _assert_close(mv, base)


def test_review_quality_uses_one_order_level_review_weight(conn):
    attributed = _number(conn, "SELECT SUM(review_count) FROM mv_review_quality")
    reviewed_orders = _number(
        conn,
        "SELECT COUNT(*) FROM ("
        "SELECT DISTINCT f.order_id FROM fact_order_items f "
        "JOIN order_reviews r ON f.order_id=r.order_id "
        "WHERE r.review_score IS NOT NULL"
        ") reviewed",
    )
    _assert_close(attributed, reviewed_orders)
    assert _scalar(
        conn,
        "SELECT COUNT(*) FROM mv_review_quality "
        "WHERE avg_review_score NOT BETWEEN 1 AND 5 "
        "OR negative_review_rate NOT BETWEEN 0 AND 1 "
        "OR review_count <= 0",
    ) == 0


def test_seller_risk_matches_seller_order_grain(conn):
    _assert_close(
        _number(conn, "SELECT SUM(total_gmv) FROM mv_seller_review_risk"),
        _number(conn, "SELECT SUM(item_gmv) FROM fact_order_items"),
    )
    assert _scalar(
        conn,
        "SELECT COUNT(*) FROM mv_seller_review_risk "
        "WHERE (avg_review_score IS NOT NULL AND avg_review_score NOT BETWEEN 1 AND 5) "
        "OR (delay_rate IS NOT NULL AND delay_rate NOT BETWEEN 0 AND 1) "
        "OR total_orders <= 0 OR negative_orders < 0",
    ) == 0
