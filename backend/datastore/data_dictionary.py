"""数据字典：基础表 + 预聚合视图的结构化描述。

数据分析 Agent 的 Prompt 强制注入本字典，作为「选表 / 命中视图」的依据，
并体现「优先用视图」策略。口径定义同时写入，Agent 必须遵守。
"""
from __future__ import annotations

# 预聚合视图：name -> {grain, fields, use_when, dimensions}
MATERIALIZED_VIEWS: dict[str, dict] = {
    "mv_monthly_sales": {
        "grain": "year_month",
        "dimensions": ["year_month"],
        "fields": ["year_month", "total_gmv", "total_orders", "avg_basket", "total_freight"],
        "use_when": ["月度销售", "GMV趋势", "环比增长", "客单价"],
    },
    "mv_weekly_sales": {
        "grain": "week_start",
        "dimensions": ["week_start"],
        "fields": ["week_start", "total_gmv", "total_orders", "avg_basket", "total_freight"],
        "use_when": ["周度GMV", "短期销售预测输入"],
    },
    "mv_state_sales": {
        "grain": "year_month + customer_state",
        "dimensions": ["year_month", "customer_state"],
        "fields": ["year_month", "customer_state", "total_gmv", "total_orders", "unique_customers"],
        "use_when": ["各州销售", "区域对比", "州级排名", "各州月度趋势"],
    },
    "mv_category_sales": {
        "grain": "year_month + product_category_english",
        "dimensions": ["year_month", "product_category_english"],
        "fields": ["year_month", "product_category_english", "total_gmv", "total_orders", "avg_price"],
        "use_when": ["品类表现", "Top品类", "下滑品类"],
    },
    "mv_delivery_perf": {
        "grain": "year_month + customer_state",
        "dimensions": ["year_month", "customer_state"],
        "fields": ["year_month", "customer_state", "avg_delivery_days", "on_time_rate", "delayed_orders", "total_orders"],
        "use_when": ["订单级配送延迟", "订单级准时率", "物流诊断"],
    },
    "mv_payment_dist": {
        "grain": "year_month + payment_type",
        "dimensions": ["year_month", "payment_type"],
        "fields": ["year_month", "payment_type", "total_transactions", "avg_installments", "total_value"],
        "use_when": ["支付方式", "分期", "支付偏好"],
    },
    "mv_payment_installment_matrix": {
        "grain": "payment_type + payment_installments",
        "dimensions": ["payment_type", "payment_installments"],
        "fields": ["payment_type", "payment_installments", "total_transactions", "total_value"],
        "use_when": ["支付方式×分期数交叉", "支付分期热力图"],
    },
    "mv_weight_freight_bucket": {
        "grain": "weight_bucket",
        "dimensions": ["weight_bucket"],
        "fields": ["weight_bucket", "avg_weight_g", "avg_length_cm", "avg_height_cm", "avg_width_cm",
                   "avg_volume_cm3", "avg_freight", "avg_delivery_days", "order_cnt"],
        "use_when": ["商品重量/尺寸与运费关系", "重量分桶配送"],
    },
    "mv_state_geo_sales": {
        "grain": "customer_state",
        "dimensions": ["customer_state"],
        "fields": ["customer_state", "total_gmv", "total_orders", "latitude", "longitude"],
        "use_when": ["州级地理分布", "地图", "在地图上展示", "地理气泡图/热力图", "经纬度坐标"],
    },
    "mv_review_quality": {
        "grain": "year_month + customer_state + product_category_english",
        "dimensions": ["year_month", "customer_state", "product_category_english"],
        "fields": ["year_month", "customer_state", "product_category_english", "avg_review_score",
                   "negative_review_rate", "review_count"],
        "use_when": ["订单级评论质量", "评分", "差评率", "品类满意度", "退货风险代理"],
    },
    "mv_seller_review_risk": {
        "grain": "seller_id",
        "dimensions": ["seller_id"],
        "fields": ["seller_id", "total_orders", "total_gmv", "avg_review_score", "negative_orders", "delay_rate"],
        "use_when": ["高差评卖家", "What-if 下架模拟", "卖家风险"],
    },
}

# 回退用基础/明细表
BASE_TABLES: dict[str, dict] = {
    "fact_order_items": {
        "description": "订单明细宽表（回退查询主力）",
        "key_fields": ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value",
                       "item_gmv", "year_month", "customer_state", "seller_state",
                       "product_category_english", "product_weight_g", "is_on_time", "shipping_duration_days"],
    },
    "orders": {"pk": "order_id", "joins": "customers via customer_id"},
    "order_items": {"pk": "(order_id, order_item_id)", "joins": "orders / products / sellers"},
    "customers": {"pk": "customer_id", "key_fields": ["customer_state", "customer_city"]},
    "sellers": {"pk": "seller_id", "key_fields": ["seller_state", "seller_city"]},
    "products": {"pk": "product_id"},
    "order_payments": {"pk": "(order_id, payment_sequential)"},
    "order_reviews": {"pk": "review_pk", "key_fields": ["order_id", "review_score", "review_comment_message"]},
    "geolocation": {"note": "百万行；州级分析优先用 mv_state_geo_sales"},
}

# 口径定义（Agent 必须遵守）
METRIC_DEFINITIONS = {
    "total_gmv": "Σ(price + freight_value)，即 fact_order_items.item_gmv 之和（含运费口径，与基础表一致）",
    "avg_basket": "total_gmv / total_orders",
    "shipping_duration_days": "delivered_customer_date − purchase_timestamp（天），仅 delivered 订单有值",
    "on_time_rate": "订单级 delivered_customer_date ≤ estimated_delivery_date 的比例，每个订单只计一次",
    "low_score / negative": (
        "review_score ≤ 2；先聚合为订单级评分，多品类/多卖家订单按不同对象等权分摊；"
        "review_count 为归因后的有效订单评论数"
    ),
}

# 命名约定提醒：本项目沿用原始 Olist 列名，year_month 为保留字需反引号
NAMING_NOTE = "字段 year_month 在 SQL 中必须写成 `year_month`（反引号）。只能返回一条 SELECT，禁止分号拼接。"


def question_dimensions_hint() -> str:
    lines = []
    for name, meta in MATERIALIZED_VIEWS.items():
        lines.append(f"- {name}({', '.join(meta['fields'])}) | 粒度={meta['grain']} | 适用：{ '/'.join(meta['use_when']) }")
    return "\n".join(lines)
