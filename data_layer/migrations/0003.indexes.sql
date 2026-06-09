-- 迁移 0003：基础表 JOIN / 过滤列索引，加速 ETL、回退查询与 benchmark 慢路径。

CREATE INDEX idx_orders_customer       ON orders(customer_id);
CREATE INDEX idx_orders_status         ON orders(order_status);
CREATE INDEX idx_orders_purchase_ts    ON orders(order_purchase_timestamp);
CREATE INDEX idx_order_items_product   ON order_items(product_id);
CREATE INDEX idx_order_items_seller    ON order_items(seller_id);
CREATE INDEX idx_payments_order        ON order_payments(order_id);
CREATE INDEX idx_reviews_order         ON order_reviews(order_id);
CREATE INDEX idx_reviews_score         ON order_reviews(review_score);
CREATE INDEX idx_customers_state       ON customers(customer_state);
CREATE INDEX idx_sellers_state         ON sellers(seller_state);
CREATE INDEX idx_geo_zip               ON geolocation(geolocation_zip_code_prefix);
CREATE INDEX idx_geo_state             ON geolocation(geolocation_state);
CREATE INDEX idx_products_category     ON products(product_category_name);
