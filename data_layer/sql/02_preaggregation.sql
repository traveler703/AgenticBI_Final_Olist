-- ============================================================
-- 预聚合层：物理预聚合表
-- 声明式整体重算：首建与刷新走完全相同的 SQL 。
-- 刷新入口：python -m utils.refresh_aggregations。
-- ============================================================

-- @mv: fact_order_items | order_items
DROP TABLE IF EXISTS fact_order_items;
CREATE TABLE fact_order_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    oi.price,
    oi.freight_value,
    (oi.price + oi.freight_value) AS item_gmv,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    CONCAT(YEAR(o.order_purchase_timestamp), '-', LPAD(MONTH(o.order_purchase_timestamp), 2, '0')) AS `year_month`,
    YEAR(o.order_purchase_timestamp)  AS year_of_purchase,
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
JOIN orders o     ON oi.order_id = o.order_id
JOIN customers c  ON o.customer_id = c.customer_id
JOIN products p   ON oi.product_id = p.product_id
LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
JOIN sellers s    ON oi.seller_id = s.seller_id
WHERE o.order_purchase_timestamp IS NOT NULL;
CREATE INDEX idx_fact_month   ON fact_order_items(`year_month`(7));
CREATE INDEX idx_fact_state   ON fact_order_items(customer_state(2));
CREATE INDEX idx_fact_seller  ON fact_order_items(seller_id(32));
CREATE INDEX idx_fact_order   ON fact_order_items(order_id(32));

-- @mv: mv_monthly_sales | fact_order_items
DROP TABLE IF EXISTS mv_monthly_sales;
CREATE TABLE mv_monthly_sales AS
SELECT `year_month`,
       SUM(item_gmv) AS total_gmv,
       COUNT(DISTINCT order_id) AS total_orders,
       SUM(item_gmv) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_basket,
       SUM(freight_value) AS total_freight
FROM fact_order_items
GROUP BY `year_month`;
CREATE INDEX idx_mv_monthly_sales_month ON mv_monthly_sales(`year_month`(7));

-- @mv: mv_weekly_sales | fact_order_items
DROP TABLE IF EXISTS mv_weekly_sales;
CREATE TABLE mv_weekly_sales AS
SELECT DATE_SUB(DATE(order_purchase_timestamp), INTERVAL WEEKDAY(order_purchase_timestamp) DAY) AS week_start,
       SUM(item_gmv) AS total_gmv,
       COUNT(DISTINCT order_id) AS total_orders,
       SUM(item_gmv) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_basket,
       SUM(freight_value) AS total_freight
FROM fact_order_items
GROUP BY week_start;
CREATE INDEX idx_mv_weekly_sales_week ON mv_weekly_sales(week_start);

-- @mv: mv_state_sales | fact_order_items
DROP TABLE IF EXISTS mv_state_sales;
CREATE TABLE mv_state_sales AS
SELECT `year_month`,
       customer_state,
       SUM(item_gmv) AS total_gmv,
       COUNT(DISTINCT order_id) AS total_orders,
       COUNT(DISTINCT customer_id) AS unique_customers
FROM fact_order_items
GROUP BY `year_month`, customer_state;
CREATE INDEX idx_mv_state_sales_month_state ON mv_state_sales(`year_month`(7), customer_state(2));

-- @mv: mv_category_sales | fact_order_items
DROP TABLE IF EXISTS mv_category_sales;
CREATE TABLE mv_category_sales AS
SELECT `year_month`,
       product_category_english,
       SUM(item_gmv) AS total_gmv,
       COUNT(DISTINCT order_id) AS total_orders,
       AVG(price) AS avg_price
FROM fact_order_items
GROUP BY `year_month`, product_category_english;
CREATE INDEX idx_mv_category_sales_month_cat ON mv_category_sales(`year_month`(7), product_category_english(128));

-- @mv: mv_delivery_perf | fact_order_items
DROP TABLE IF EXISTS mv_delivery_perf;
CREATE TABLE mv_delivery_perf AS
WITH order_delivery AS (
    SELECT order_id,
           MAX(`year_month`) AS `year_month`,
           MAX(customer_state) AS customer_state,
           MAX(shipping_duration_days) AS shipping_duration_days,
           MAX(is_on_time) AS is_on_time
    FROM fact_order_items
    WHERE shipping_duration_days IS NOT NULL
    GROUP BY order_id
)
SELECT `year_month`,
       customer_state,
       AVG(shipping_duration_days) AS avg_delivery_days,
       AVG(is_on_time) AS on_time_rate,
       SUM(CASE WHEN is_on_time = 0 THEN 1 ELSE 0 END) AS delayed_orders,
       COUNT(*) AS total_orders
FROM order_delivery
GROUP BY `year_month`, customer_state;
CREATE INDEX idx_mv_delivery_perf_month_state ON mv_delivery_perf(`year_month`(7), customer_state(2));

-- @mv: mv_payment_dist | order_payments
DROP TABLE IF EXISTS mv_payment_dist;
CREATE TABLE mv_payment_dist AS
SELECT CONCAT(YEAR(o.order_purchase_timestamp), '-', LPAD(MONTH(o.order_purchase_timestamp), 2, '0')) AS `year_month`,
       op.payment_type,
       COUNT(*) AS total_transactions,
       AVG(op.payment_installments) AS avg_installments,
       SUM(op.payment_value) AS total_value
FROM order_payments op
JOIN orders o ON op.order_id = o.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY `year_month`, op.payment_type;
CREATE INDEX idx_mv_payment_dist_month_type ON mv_payment_dist(`year_month`(7), payment_type(32));

-- @mv: mv_payment_installment_matrix | order_payments
DROP TABLE IF EXISTS mv_payment_installment_matrix;
CREATE TABLE mv_payment_installment_matrix AS
SELECT op.payment_type,
       op.payment_installments,
       COUNT(*) AS total_transactions,
       SUM(op.payment_value) AS total_value
FROM order_payments op
GROUP BY op.payment_type, op.payment_installments;
CREATE INDEX idx_mv_payment_installment_matrix ON mv_payment_installment_matrix(payment_type(32), payment_installments);

-- @mv: mv_weight_freight_bucket | fact_order_items
DROP TABLE IF EXISTS mv_weight_freight_bucket;
CREATE TABLE mv_weight_freight_bucket AS
SELECT CASE
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

-- @mv: mv_state_geo_sales | mv_state_sales
DROP TABLE IF EXISTS mv_state_geo_sales;
CREATE TABLE mv_state_geo_sales AS
SELECT s.customer_state,
       SUM(s.total_gmv) AS total_gmv,
       SUM(s.total_orders) AS total_orders,
       g.latitude,
       g.longitude
FROM mv_state_sales s
JOIN (
    SELECT geolocation_state AS customer_state,
           AVG(geolocation_lat) AS latitude,
           AVG(geolocation_lng) AS longitude
    FROM geolocation
    WHERE geolocation_lat BETWEEN -35 AND 6
      AND geolocation_lng BETWEEN -75 AND -30
    GROUP BY geolocation_state
) g ON s.customer_state = g.customer_state
GROUP BY s.customer_state, g.latitude, g.longitude;
CREATE INDEX idx_mv_state_geo_sales_state ON mv_state_geo_sales(customer_state(2));

-- @mv: mv_review_quality | fact_order_items
DROP TABLE IF EXISTS mv_review_quality;
CREATE TABLE mv_review_quality AS
WITH order_context AS (
    SELECT order_id,
           MAX(`year_month`) AS `year_month`,
           MAX(customer_state) AS customer_state
    FROM fact_order_items
    GROUP BY order_id
),
order_categories AS (
    SELECT DISTINCT order_id, product_category_english
    FROM fact_order_items
),
category_counts AS (
    SELECT order_id, COUNT(*) AS category_count
    FROM order_categories
    GROUP BY order_id
),
order_reviews_one AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM order_reviews
    WHERE review_score IS NOT NULL
    GROUP BY order_id
),
attributed_reviews AS (
    SELECT c.`year_month`,
           c.customer_state,
           oc.product_category_english,
           r.review_score,
           1.0 / cc.category_count AS attribution_weight
    FROM order_context c
    JOIN order_categories oc ON c.order_id = oc.order_id
    JOIN category_counts cc ON c.order_id = cc.order_id
    JOIN order_reviews_one r ON c.order_id = r.order_id
)
SELECT `year_month`,
       customer_state,
       product_category_english,
       SUM(review_score * attribution_weight) / NULLIF(SUM(attribution_weight), 0) AS avg_review_score,
       SUM(CASE WHEN review_score <= 2 THEN attribution_weight ELSE 0 END)
           / NULLIF(SUM(attribution_weight), 0) AS negative_review_rate,
       SUM(attribution_weight) AS review_count
FROM attributed_reviews
GROUP BY `year_month`, customer_state, product_category_english;
CREATE INDEX idx_mv_review_quality_month_state ON mv_review_quality(`year_month`(7), customer_state(2));
CREATE INDEX idx_mv_review_quality_category ON mv_review_quality(product_category_english(128));

-- @mv: mv_seller_review_risk | fact_order_items
DROP TABLE IF EXISTS mv_seller_review_risk;
CREATE TABLE mv_seller_review_risk AS
WITH seller_orders AS (
    SELECT order_id,
           seller_id,
           SUM(item_gmv) AS seller_gmv,
           MAX(CASE WHEN shipping_duration_days IS NOT NULL THEN is_on_time END) AS is_on_time
    FROM fact_order_items
    GROUP BY order_id, seller_id
),
seller_counts AS (
    SELECT order_id, COUNT(*) AS seller_count
    FROM seller_orders
    GROUP BY order_id
),
order_reviews_one AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM order_reviews
    WHERE review_score IS NOT NULL
    GROUP BY order_id
)
SELECT so.seller_id,
       COUNT(*) AS total_orders,
       SUM(so.seller_gmv) AS total_gmv,
       LEAST(5.0, GREATEST(
           1.0,
           SUM(CAST(r.review_score AS DECIMAL(20,8)) / sc.seller_count)
               / NULLIF(SUM(
                   CASE WHEN r.review_score IS NOT NULL
                        THEN CAST(1 AS DECIMAL(20,8)) / sc.seller_count
                        ELSE 0 END
               ), 0)
       )) AS avg_review_score,
       SUM(
           CASE WHEN r.review_score <= 2
                THEN CAST(1 AS DECIMAL(20,8)) / sc.seller_count
                ELSE 0 END
       ) AS negative_orders,
       AVG(CASE WHEN so.is_on_time IS NOT NULL THEN 1 - so.is_on_time END) AS delay_rate
FROM seller_orders so
JOIN seller_counts sc ON so.order_id = sc.order_id
LEFT JOIN order_reviews_one r ON so.order_id = r.order_id
GROUP BY so.seller_id;
CREATE INDEX idx_mv_seller_review_risk_score ON mv_seller_review_risk(avg_review_score, negative_orders);
