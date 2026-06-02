from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "utils" / "sql" / "create_materialized_views.sql").read_text(encoding="utf-8")


def test_mv_objects_are_physical_tables_not_plain_views() -> None:
    assert "CREATE VIEW mv_monthly_sales" not in SQL
    assert "CREATE TABLE mv_monthly_sales AS" in SQL
    assert "CREATE TABLE mv_state_sales AS" in SQL
    assert "CREATE TABLE mv_delivery_perf AS" in SQL
    assert "CREATE INDEX idx_mv_monthly_sales_month" in SQL


def test_review_risk_preaggregations_exist() -> None:
    assert "CREATE TABLE mv_review_quality AS" in SQL
    assert "CREATE TABLE mv_seller_review_risk AS" in SQL
    assert "negative_review_rate" in SQL
    assert "negative_orders" in SQL

