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


@pytest.fixture(scope="module")
def conn():
    engine = create_engine(get_settings().ro_url, pool_pre_ping=True)
    with engine.connect() as c:
        yield c


def _scalar(conn, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


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
    mv = float(conn.execute(text("SELECT SUM(total_gmv) FROM mv_monthly_sales")).scalar())
    base = float(conn.execute(text("SELECT SUM(item_gmv) FROM fact_order_items")).scalar())
    assert abs(mv - base) <= max(1.0, abs(base) * 1e-6)


def test_refresh_log_written(conn):
    assert _scalar(conn, "SELECT COUNT(*) FROM mv_refresh_log") >= 6


def test_six_core_views_present(conn):
    for view in [
        "mv_monthly_sales",
        "mv_state_sales",
        "mv_category_sales",
        "mv_delivery_perf",
        "mv_payment_dist",
        "mv_review_quality",
    ]:
        assert _scalar(conn, f"SELECT COUNT(*) FROM {view}") > 0
