-- 迁移 0004：数据仓库刷新留痕表。仅放与 Olist 数据相关的元数据。
CREATE TABLE IF NOT EXISTS mv_refresh_log (
    id           BIGINT NOT NULL AUTO_INCREMENT,
    mv_name      VARCHAR(64),
    refreshed_at DATETIME,
    source_rows  BIGINT,
    result_rows  BIGINT,
    elapsed_ms   INT,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
