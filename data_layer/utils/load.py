"""CSV → 基础表 装载（清洗后 append 到迁移管理的表结构）。

schema 由 migrations 统一管理；本步骤只负责 TRUNCATE + 清洗 + 写入数据，
因此重复装载幂等，且不会破坏迁移创建的索引。使用 etl 账号写入。
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from utils.clean import clean_table
from utils.config import RAW_DATA_DIR, get_settings

# 表名 -> CSV 文件名
TABLE_CSV_MAP = {
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}

CHUNKED_TABLES = {"geolocation"}


def _engine():
    return create_engine(get_settings().etl_url, pool_pre_ping=True)


def load_table(engine, table: str, csv_name: str) -> int:
    path = RAW_DATA_DIR / csv_name
    if not path.exists():
        raise FileNotFoundError(f"缺少数据文件: {path}")

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table}"))

    total = 0
    if table in CHUNKED_TABLES:
        for chunk in pd.read_csv(path, encoding="utf-8-sig", chunksize=100_000):
            chunk = clean_table(table, chunk)
            chunk.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=5000)
            total += len(chunk)
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
        df = clean_table(table, df)
        df.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=5000)
        total = len(df)
    print(f"  装载 {table:<34} <- {csv_name}  ({total:,} 行)", flush=True)
    return total


def main() -> None:
    engine = _engine()
    print("开始清洗装载 9 张基础表 ...", flush=True)
    for table, csv_name in TABLE_CSV_MAP.items():
        load_table(engine, table, csv_name)
    print("基础表装载完成。", flush=True)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
