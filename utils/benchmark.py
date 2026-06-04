"""物理预聚合表 vs 原表聚合 性能对比（报告截图用）。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import get_settings

REPORT_DIR = ROOT / "outputs" / "reports"

SLOW_QUERY = """
SELECT CONCAT(
           YEAR(o.order_purchase_timestamp),
           '-',
           LPAD(MONTH(o.order_purchase_timestamp), 2, '0')
       ) AS `year_month`,
       SUM(oi.price + oi.freight_value) AS total_gmv
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1
ORDER BY 1
"""

FAST_QUERY = "SELECT `year_month`, total_gmv FROM mv_monthly_sales ORDER BY 1"


def timed_query(engine, sql: str, label: str) -> float:
    start = time.perf_counter()
    with engine.connect() as conn:
        conn.execute(text(sql))
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed:.3f}s")
    return elapsed


def main() -> None:
    engine = create_engine(get_settings().mysql_url)
    print("=== 性能对比 ===")
    slow = timed_query(engine, SLOW_QUERY, "慢路径(原表 JOIN 聚合)")
    fast = timed_query(engine, FAST_QUERY, "快路径(mv_monthly_sales)")
    speedup = slow / fast if fast > 0 else 0
    if fast > 0:
        print(f"加速比约: {speedup:.1f}x")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "performance_comparison.md").write_text(
        "\n".join(
            [
                "# Pre-aggregation Performance Comparison",
                "",
                f"- Base JOIN aggregation: {slow:.4f}s",
                f"- Physical mv_monthly_sales table: {fast:.4f}s",
                f"- Speedup: {speedup:.1f}x" if speedup else "- Speedup: N/A",
                "",
                "## Slow Query",
                "```sql",
                SLOW_QUERY.strip(),
                "```",
                "",
                "## Fast Query",
                "```sql",
                FAST_QUERY.strip(),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    labels = ["Base JOIN aggregation", "Pre-aggregated query"]
    elapsed_ms = [slow * 1000, fast * 1000]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, elapsed_ms, color=["#c95050", "#2b8a6e"])
    ax.set_yscale("log")
    ax.set_ylabel("Query time (ms, log scale)")
    ax.set_title(f"Pre-Aggregation Performance: {speedup:.1f}x speedup")
    for bar, value in zip(bars, elapsed_ms):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.3f} ms", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "performance_comparison.png", dpi=160)
    plt.close(fig)
    print(f"报告材料已写入: {REPORT_DIR / 'performance_comparison.md'}")


if __name__ == "__main__":
    main()
