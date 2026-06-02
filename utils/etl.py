"""
ETL：构建 fact_order_items 宽表及衍生字段。
前置：utils.db_init 已完成。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import get_settings

FACT_ORDER_ITEMS_SQL = """
CREATE TABLE fact_order_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    oi.price,
    oi.freight_value,
    (oi.price + oi.freight_value) AS item_gmv,
    o.order_id AS order_unique_check,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    CONCAT(
        YEAR(o.order_purchase_timestamp),
        '-',
        LPAD(MONTH(o.order_purchase_timestamp), 2, '0')
    ) AS `year_month`,
    YEAR(o.order_purchase_timestamp) AS year_of_purchase,
    MONTH(o.order_purchase_timestamp) AS month_of_purchase,
    c.customer_state,
    c.customer_city,
    s.seller_state,
    s.seller_city,
    p.product_category_name,
    COALESCE(t.product_category_name_english, p.product_category_name) AS product_category_english,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
             AND o.order_delivered_customer_date <= o.order_estimated_delivery_date
        THEN 1 ELSE 0
    END AS is_on_time,
    DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp) AS shipping_duration_days
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN product_category_name_translation t
    ON p.product_category_name = t.product_category_name
JOIN sellers s ON oi.seller_id = s.seller_id
WHERE o.order_purchase_timestamp IS NOT NULL
"""


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.mysql_url)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fact_order_items"))
        conn.execute(text(FACT_ORDER_ITEMS_SQL))
        conn.commit()
    print("ETL 完成：fact_order_items 已构建。")


if __name__ == "__main__":
    main()
