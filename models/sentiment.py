"""订单评论情感分析（加分项）。"""
from __future__ import annotations

import pandas as pd

from utils.db import run_select


def review_sentiment_proxy_top_categories(limit: int = 10) -> pd.DataFrame:
    """使用 review_score 作为情感代理变量，统计低分占比最高品类。"""
    sql = f"""
    SELECT
        f.product_category_english,
        COUNT(*) AS review_cnt,
        AVG(r.review_score) AS avg_score,
        AVG(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS low_score_rate
    FROM order_reviews r
    JOIN fact_order_items f ON r.order_id = f.order_id
    WHERE f.product_category_english IS NOT NULL
    GROUP BY f.product_category_english
    HAVING review_cnt >= 30
    ORDER BY low_score_rate DESC, review_cnt DESC
    LIMIT {int(limit)}
    """
    return run_select(sql)
