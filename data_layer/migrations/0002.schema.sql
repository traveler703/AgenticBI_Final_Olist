-- 迁移 0002：9 张规范化基础表 DDL

CREATE TABLE IF NOT EXISTS customers (
    customer_id              VARCHAR(64)  NOT NULL,
    customer_unique_id       VARCHAR(64),
    customer_zip_code_prefix INT,
    customer_city            VARCHAR(128),
    customer_state           VARCHAR(8),
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sellers (
    seller_id              VARCHAR(64) NOT NULL,
    seller_zip_code_prefix INT,
    seller_city            VARCHAR(128),
    seller_state           VARCHAR(8),
    PRIMARY KEY (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    product_id                 VARCHAR(64) NOT NULL,
    product_category_name      VARCHAR(128),
    product_name_lenght        INT,
    product_description_lenght INT,
    product_photos_qty         INT,
    product_weight_g           INT,
    product_length_cm          INT,
    product_height_cm          INT,
    product_width_cm           INT,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS orders (
    order_id                      VARCHAR(64) NOT NULL,
    customer_id                   VARCHAR(64),
    order_status                  VARCHAR(32),
    order_purchase_timestamp      DATETIME NULL,
    order_approved_at             DATETIME NULL,
    order_delivered_carrier_date  DATETIME NULL,
    order_delivered_customer_date DATETIME NULL,
    order_estimated_delivery_date DATETIME NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_items (
    order_id            VARCHAR(64) NOT NULL,
    order_item_id       INT NOT NULL,
    product_id          VARCHAR(64),
    seller_id           VARCHAR(64),
    shipping_limit_date DATETIME NULL,
    price               DECIMAL(10,2),
    freight_value       DECIMAL(10,2),
    PRIMARY KEY (order_id, order_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_payments (
    order_id             VARCHAR(64) NOT NULL,
    payment_sequential   INT NOT NULL,
    payment_type         VARCHAR(32),
    payment_installments INT,
    payment_value        DECIMAL(10,2),
    PRIMARY KEY (order_id, payment_sequential)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_reviews (
    review_pk               BIGINT NOT NULL AUTO_INCREMENT,
    review_id               VARCHAR(64),
    order_id                VARCHAR(64),
    review_score            INT,
    review_comment_title    VARCHAR(255),
    review_comment_message  TEXT,
    review_creation_date    DATETIME NULL,
    review_answer_timestamp DATETIME NULL,
    PRIMARY KEY (review_pk)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_zip_code_prefix INT,
    geolocation_lat             DOUBLE,
    geolocation_lng             DOUBLE,
    geolocation_city            VARCHAR(128),
    geolocation_state           VARCHAR(8)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS product_category_name_translation (
    product_category_name         VARCHAR(128) NOT NULL,
    product_category_name_english VARCHAR(128),
    PRIMARY KEY (product_category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
