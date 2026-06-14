"""一键刷新全部预聚合表。

声明式整体重算：逐块执行 sql/02_preaggregation.sql。
每张表刷新后：
  - 打印 源行数 → 结果行数 → 耗时
  - 写一行到 mv_refresh_log（mv_name, refreshed_at, source_rows, result_rows, elapsed_ms）
  - 全部刷新完跑一致性自校验：预聚合汇总值 == 基础表实时汇总值，不一致则报错退出。

入口：python -m utils.refresh_aggregations
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import SQL_DIR, get_settings

PREAGG_SQL = SQL_DIR / "02_preaggregation.sql"
MARKER = re.compile(r"^--\s*@mv:\s*(\w+)\s*\|\s*(\w+)\s*$")


def _parse_blocks(sql_text: str) -> list[tuple[str, str, list[str]]]:
    """切成 [(mv_name, source_table, [statements...]), ...]。"""
    blocks: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str] | None = None
    buffer: list[str] = []

    def flush():
        if current is not None:
            statements = [s.strip() for s in "\n".join(buffer).split(";") if s.strip()]
            blocks.append((current[0], current[1], statements))

    for line in sql_text.splitlines():
        m = MARKER.match(line.strip())
        if m:
            flush()
            current = (m.group(1), m.group(2))
            buffer = []
        elif current is not None:
            buffer.append(line)
    flush()
    return blocks


def _count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)


def refresh() -> None:
    engine = create_engine(get_settings().etl_url, pool_pre_ping=True)
    blocks = _parse_blocks(PREAGG_SQL.read_text(encoding="utf-8"))
    print(f"=== 刷新预聚合：{len(blocks)} 个对象 ===", flush=True)

    with engine.connect() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS mv_refresh_log (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mv_name VARCHAR(64), refreshed_at DATETIME,
            source_rows BIGINT, result_rows BIGINT, elapsed_ms INT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""))
        conn.commit()
        for mv_name, source_table, statements in blocks:
            source_rows = _count(conn, source_table)
            start = time.perf_counter()
            for stmt in statements:
                conn.execute(text(stmt))
            conn.commit()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result_rows = _count(conn, mv_name)
            conn.execute(
                text(
                    "INSERT INTO mv_refresh_log (mv_name, refreshed_at, source_rows, result_rows, elapsed_ms) "
                    "VALUES (:n, :t, :s, :r, :e)"
                ),
                {"n": mv_name, "t": datetime.now(), "s": source_rows, "r": result_rows, "e": elapsed_ms},
            )
            conn.commit()
            print(f"  {mv_name:<32} 源 {source_rows:>9,} → 结果 {result_rows:>7,} 行  {elapsed_ms:>6} ms", flush=True)

    _self_check(engine)


def _self_check(engine) -> None:
    """一致性自校验：预聚合汇总值必须等于基础表实时汇总值。"""
    print("=== 一致性自校验 ===", flush=True)
    checks: list[tuple[str, float, float]] = []
    with engine.connect() as conn:
        mv_gmv = float(conn.execute(text("SELECT COALESCE(SUM(total_gmv),0) FROM mv_monthly_sales")).scalar())
        base_gmv = float(conn.execute(text("SELECT COALESCE(SUM(item_gmv),0) FROM fact_order_items")).scalar())
        checks.append(("月度GMV合计 vs fact_order_items", mv_gmv, base_gmv))

        mv_orders = int(conn.execute(text("SELECT COALESCE(SUM(total_orders),0) FROM mv_monthly_sales")).scalar())
        base_orders = int(conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_order_items")).scalar())
        checks.append(("月度订单数合计 vs fact 唯一订单", mv_orders, base_orders))

        mv_pay = float(conn.execute(text("SELECT COALESCE(SUM(total_value),0) FROM mv_payment_dist")).scalar())
        base_pay = float(
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(op.payment_value),0) FROM order_payments op "
                    "JOIN orders o ON op.order_id=o.order_id WHERE o.order_purchase_timestamp IS NOT NULL"
                )
            ).scalar()
        )
        checks.append(("支付金额合计 vs order_payments", mv_pay, base_pay))

    failed = []
    for label, mv_value, base_value in checks:
        ok = abs(mv_value - base_value) <= max(1.0, abs(base_value) * 1e-6)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}: 预聚合={mv_value:,.2f}  基础表={base_value:,.2f}", flush=True)
        if not ok:
            failed.append(label)

    if failed:
        raise SystemExit(f"一致性自校验失败：{failed}（已拒绝产出脏视图）")
    print("一致性 PASS。", flush=True)


if __name__ == "__main__":
    refresh()
