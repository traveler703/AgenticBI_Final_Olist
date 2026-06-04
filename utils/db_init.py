"""
MySQL 建库建表并从 data/raw/ 导入 Olist CSV。

数据路径：AgenticBI_Final_Olist/data/raw/*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import RAW_DATA_DIR, check_raw_data_files, get_settings

# 表名 -> CSV 文件名
TABLE_CSV_MAP = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}


def ensure_database() -> None:
    settings = get_settings()
    server_url = (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/"
    )
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with server_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    except Exception as exc:
        host, port = settings.mysql_host, settings.mysql_port
        print(
            f"\n无法连接 MySQL：{host}:{port}\n"
            f"  原因：{exc}\n\n"
            "常见处理：\n"
            "  1. 确认 MySQL 已启动（本机可执行：mysqladmin ping -h127.0.0.1）\n"
            "  2. 核对 .env 中 MYSQL_PORT 是否与实例一致（本机默认多为 3306）\n"
            "  3. 若用 Docker：在项目根目录执行 docker compose up -d\n"
            "  4. localhost 与 127.0.0.1 等价；连不上通常是端口或服务未启动，而非主机名\n"
        )
        raise SystemExit(1) from exc


def import_csv(engine, table: str, csv_name: str, chunksize: int | None = None) -> None:
    path = RAW_DATA_DIR / csv_name
    if not path.exists():
        raise FileNotFoundError(f"缺少数据文件: {path}")
    if chunksize and table == "geolocation":
        for i, chunk in enumerate(pd.read_csv(path, chunksize=chunksize)):
            chunk.to_sql(table, engine, if_exists="append" if i else "replace", index=False)
    else:
        df = pd.read_csv(path)
        df.to_sql(table, engine, if_exists="replace", index=False, method="multi", chunksize=5000)
    print(f"  已导入 {table} <- {csv_name}")


def main() -> None:
    ok, missing = check_raw_data_files()
    if not ok:
        print("错误：以下 CSV 未找到，请放入目录：")
        print(f"  {RAW_DATA_DIR}")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    settings = get_settings()
    ensure_database()
    engine = create_engine(settings.mysql_url)

    print(f"从 {RAW_DATA_DIR} 导入数据到 {settings.mysql_database} ...")
    for table, csv_name in TABLE_CSV_MAP.items():
        import_csv(
            engine,
            table,
            csv_name,
            chunksize=100_000 if table == "geolocation" else None,
        )
    print("db_init 完成。")


if __name__ == "__main__":
    main()
