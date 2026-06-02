"""执行预聚合视图 SQL。"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import get_settings

SQL_FILE = Path(__file__).parent / "sql" / "create_materialized_views.sql"


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.mysql_url)
    sql = SQL_FILE.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()
    print(
        "物理预聚合表已创建/刷新："
        "mv_monthly_sales, mv_state_sales, mv_category_sales, mv_delivery_perf, "
        "mv_payment_dist, mv_review_quality, mv_seller_review_risk"
    )


if __name__ == "__main__":
    main()
