-- Physical pre-aggregation tables for MySQL.
-- These mv_* objects are deliberately materialized as tables, not plain VIEWs,
-- so benchmark.py can show a real speed difference against live JOIN queries.
-- Dependency order: db_init -> etl -> refresh_views.

DROP VIEW IF EXISTS mv_monthly_sales;
DROP TABLE IF EXISTS mv_monthly_sales;
CREATE TABLE mv_monthly_sales AS
SELECT
    `year_month`,
    SUM(item_gmv) AS total_gmv,
    COUNT(DISTINCT order_id) AS total_orders,
    SUM(item_gmv) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_basket,
    SUM(freight_value) AS total_freight
FROM fact_order_items
GROUP BY `year_month`;

CREATE INDEX idx_mv_monthly_sales_month ON mv_monthly_sales(`year_month`(7));

DROP VIEW IF EXISTS mv_weekly_sales;
DROP TABLE IF EXISTS mv_weekly_sales;
CREATE TABLE mv_weekly_sales AS
SELECT
    DATE_SUB(DATE(order_purchase_timestamp), INTERVAL WEEKDAY(order_purchase_timestamp) DAY) AS week_start,
    SUM(item_gmv) AS total_gmv,
    COUNT(DISTINCT order_id) AS total_orders,
    SUM(item_gmv) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_basket,
    SUM(freight_value) AS total_freight
FROM fact_order_items
GROUP BY week_start;

CREATE INDEX idx_mv_weekly_sales_week ON mv_weekly_sales(week_start);

DROP VIEW IF EXISTS mv_state_sales;
DROP TABLE IF EXISTS mv_state_sales;
CREATE TABLE mv_state_sales AS
SELECT
    `year_month`,
    customer_state,
    SUM(item_gmv) AS total_gmv,
    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM fact_order_items
GROUP BY `year_month`, customer_state;

CREATE INDEX idx_mv_state_sales_month_state ON mv_state_sales(`year_month`(7), customer_state(2));

DROP VIEW IF EXISTS mv_category_sales;
DROP TABLE IF EXISTS mv_category_sales;
CREATE TABLE mv_category_sales AS
SELECT
    `year_month`,
    product_category_english,
    SUM(item_gmv) AS total_gmv,
    COUNT(DISTINCT order_id) AS total_orders,
    AVG(price) AS avg_price
FROM fact_order_items
GROUP BY `year_month`, product_category_english;

CREATE INDEX idx_mv_category_sales_month_cat ON mv_category_sales(`year_month`(7), product_category_english(128));

DROP VIEW IF EXISTS mv_delivery_perf;
DROP TABLE IF EXISTS mv_delivery_perf;
CREATE TABLE mv_delivery_perf AS
SELECT
    `year_month`,
    customer_state,
    AVG(shipping_duration_days) AS avg_delivery_days,
    AVG(is_on_time) AS on_time_rate,
    SUM(CASE WHEN is_on_time = 0 THEN 1 ELSE 0 END) AS delayed_orders,
    COUNT(DISTINCT order_id) AS total_orders
FROM fact_order_items
WHERE shipping_duration_days IS NOT NULL
GROUP BY `year_month`, customer_state;

CREATE INDEX idx_mv_delivery_perf_month_state ON mv_delivery_perf(`year_month`(7), customer_state(2));

DROP VIEW IF EXISTS mv_payment_dist;
DROP TABLE IF EXISTS mv_payment_dist;
CREATE TABLE mv_payment_dist AS
SELECT
    CONCAT(
        YEAR(o.order_purchase_timestamp),
        '-',
        LPAD(MONTH(o.order_purchase_timestamp), 2, '0')
    ) AS `year_month`,
    op.payment_type,
    COUNT(*) AS total_transactions,
    AVG(op.payment_installments) AS avg_installments,
    SUM(op.payment_value) AS total_value
FROM order_payments op
JOIN orders o ON op.order_id = o.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY `year_month`, op.payment_type;

CREATE INDEX idx_mv_payment_dist_month_type ON mv_payment_dist(`year_month`(7), payment_type(32));

DROP VIEW IF EXISTS mv_payment_installment_matrix;
DROP TABLE IF EXISTS mv_payment_installment_matrix;
CREATE TABLE mv_payment_installment_matrix AS
SELECT
    op.payment_type,
    op.payment_installments,
    COUNT(*) AS total_transactions,
    SUM(op.payment_value) AS total_value
FROM order_payments op
GROUP BY op.payment_type, op.payment_installments;

CREATE INDEX idx_mv_payment_installment_matrix ON mv_payment_installment_matrix(payment_type(32), payment_installments);

DROP VIEW IF EXISTS mv_weight_freight_bucket;
DROP TABLE IF EXISTS mv_weight_freight_bucket;
CREATE TABLE mv_weight_freight_bucket AS
SELECT
    CASE
        WHEN product_weight_g < 500 THEN '0-499g'
        WHEN product_weight_g < 1000 THEN '500-999g'
        WHEN product_weight_g < 2000 THEN '1000-1999g'
        WHEN product_weight_g < 5000 THEN '2000-4999g'
        ELSE '5000g+'
    END AS weight_bucket,
    AVG(product_weight_g) AS avg_weight_g,
    AVG(product_length_cm) AS avg_length_cm,
    AVG(product_height_cm) AS avg_height_cm,
    AVG(product_width_cm) AS avg_width_cm,
    AVG(product_length_cm * product_height_cm * product_width_cm) AS avg_volume_cm3,
    AVG(freight_value) AS avg_freight,
    AVG(shipping_duration_days) AS avg_delivery_days,
    COUNT(*) AS order_cnt
FROM fact_order_items
WHERE product_weight_g IS NOT NULL
GROUP BY weight_bucket;

CREATE INDEX idx_mv_weight_freight_bucket ON mv_weight_freight_bucket(weight_bucket);

DROP VIEW IF EXISTS mv_state_geo_sales;
DROP TABLE IF EXISTS mv_state_geo_sales;
CREATE TABLE mv_state_geo_sales AS
SELECT
    s.customer_state,
    SUM(s.total_gmv) AS total_gmv,
    SUM(s.total_orders) AS total_orders,
    g.latitude,
    g.longitude
FROM mv_state_sales s
JOIN (
    SELECT
        geolocation_state AS customer_state,
        AVG(geolocation_lat) AS latitude,
        AVG(geolocation_lng) AS longitude
    FROM geolocation
    WHERE geolocation_lat BETWEEN -35 AND 6
      AND geolocation_lng BETWEEN -75 AND -30
    GROUP BY geolocation_state
) g ON s.customer_state = g.customer_state
GROUP BY s.customer_state, g.latitude, g.longitude;

CREATE INDEX idx_mv_state_geo_sales_state ON mv_state_geo_sales(customer_state(2));

DROP VIEW IF EXISTS mv_review_quality;
DROP TABLE IF EXISTS mv_review_quality;
CREATE TABLE mv_review_quality AS
SELECT
    f.`year_month`,
    f.customer_state,
    f.product_category_english,
    AVG(r.review_score) AS avg_review_score,
    AVG(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_review_rate,
    COUNT(DISTINCT r.review_id) AS review_count
FROM fact_order_items f
JOIN order_reviews r ON f.order_id = r.order_id
GROUP BY f.`year_month`, f.customer_state, f.product_category_english;

CREATE INDEX idx_mv_review_quality_month_state ON mv_review_quality(`year_month`(7), customer_state(2));
CREATE INDEX idx_mv_review_quality_category ON mv_review_quality(product_category_english(128));

DROP VIEW IF EXISTS mv_seller_review_risk;
DROP TABLE IF EXISTS mv_seller_review_risk;
CREATE TABLE mv_seller_review_risk AS
SELECT
    f.seller_id,
    COUNT(DISTINCT f.order_id) AS total_orders,
    SUM(f.item_gmv) AS total_gmv,
    AVG(r.review_score) AS avg_review_score,
    SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_orders,
    AVG(CASE WHEN f.is_on_time = 0 THEN 1 ELSE 0 END) AS delay_rate
FROM fact_order_items f
LEFT JOIN order_reviews r ON f.order_id = r.order_id
GROUP BY f.seller_id;

CREATE INDEX idx_mv_seller_review_risk_score ON mv_seller_review_risk(avg_review_score, negative_orders);
