-- 迁移 0001：数据库账号分离（多账号机制）
-- 由 admin(root) 通过 yoyo 自动执行，无需手动 mysql < ...
--   olist_etl : 离线 ETL / 刷新预聚合（建表写表权限）
--   olist_ro  : 运行时 Agent 只读查询（仅 SELECT，DB 层兜底防写）
-- 密码与 data_layer/.env 中 MYSQL_ETL_PASSWORD / MYSQL_RO_PASSWORD 保持一致。

CREATE USER IF NOT EXISTS 'olist_etl'@'%' IDENTIFIED BY 'etl_pass_2024';
ALTER USER 'olist_etl'@'%' IDENTIFIED BY 'etl_pass_2024';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, CREATE VIEW
    ON `olist_bi`.* TO 'olist_etl'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, CREATE VIEW
    ON `agentic_app`.* TO 'olist_etl'@'%';

CREATE USER IF NOT EXISTS 'olist_ro'@'%' IDENTIFIED BY 'ro_pass_2024';
ALTER USER 'olist_ro'@'%' IDENTIFIED BY 'ro_pass_2024';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'olist_ro'@'%';
GRANT SELECT ON `olist_bi`.* TO 'olist_ro'@'%';

FLUSH PRIVILEGES;
