"""data_layer 配置：读取 .env，提供多账号 MySQL 连接。

账号分离：
  - admin (root)   : 建库 + 执行数据库版本迁移
  - etl  (olist_etl): 清洗装载 + 刷新预聚合（建表/写表权限，离线工具使用）
  - ro   (olist_ro) : 只读账号，运行时由 backend 的 Agent 查询使用
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# data_layer/ 根目录
DATA_LAYER_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = DATA_LAYER_ROOT / "data" / "raw"
PROCESSED_DIR = DATA_LAYER_ROOT / "data" / "processed"
MIGRATIONS_DIR = DATA_LAYER_ROOT / "migrations"
SQL_DIR = DATA_LAYER_ROOT / "sql"

REQUIRED_CSV_FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
]


def _url(user: str, password: str, host: str, port: int, database: str = "") -> str:
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database: str
    admin_user: str
    admin_password: str
    etl_user: str
    etl_password: str
    ro_user: str
    ro_password: str

    # 不指定库名，用于 CREATE DATABASE / CREATE USER
    @property
    def admin_server_url(self) -> str:
        return _url(self.admin_user, self.admin_password, self.host, self.port)

    @property
    def admin_url(self) -> str:
        return _url(self.admin_user, self.admin_password, self.host, self.port, self.database)

    @property
    def etl_url(self) -> str:
        return _url(self.etl_user, self.etl_password, self.host, self.port, self.database)

    @property
    def ro_url(self) -> str:
        return _url(self.ro_user, self.ro_password, self.host, self.port, self.database)

    # yoyo 迁移：scheme 用 mysql（yoyo 的 mysql 后端底层走 pymysql）
    @property
    def yoyo_url(self) -> str:
        return (
            f"mysql://{self.admin_user}:{self.admin_password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@lru_cache
def get_settings() -> Settings:
    load_dotenv(DATA_LAYER_ROOT / ".env")
    return Settings(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "olist_bi"),
        admin_user=os.getenv("MYSQL_ADMIN_USER", "root"),
        admin_password=os.getenv("MYSQL_ADMIN_PASSWORD", "root"),
        etl_user=os.getenv("MYSQL_ETL_USER", "olist_etl"),
        etl_password=os.getenv("MYSQL_ETL_PASSWORD", "etl_pass_2024"),
        ro_user=os.getenv("MYSQL_RO_USER", "olist_ro"),
        ro_password=os.getenv("MYSQL_RO_PASSWORD", "ro_pass_2024"),
    )


def check_raw_data_files() -> tuple[bool, list[str]]:
    missing = [f for f in REQUIRED_CSV_FILES if not (RAW_DATA_DIR / f).exists()]
    return len(missing) == 0, missing
