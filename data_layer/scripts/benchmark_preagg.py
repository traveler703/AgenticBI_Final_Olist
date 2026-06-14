"""预聚合 vs 原始多表 JOIN 实时聚合 性能对比（Design §2.5，报告截图用）。

对同一组分析问题各跑 N 次，输出耗时对比表与 data/processed/benchmark_report.json，
并生成 data/processed/benchmark_report.png。

入口：python -m scripts.benchmark_preagg
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 图片统一用英文标签，避免中文字体缺失渲染成方块；控制台与 JSON 仍用中文
plt.rcParams["axes.unicode_minus"] = False
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import PROCESSED_DIR, get_settings

# (名称, 图表英文标签, 慢路径 SQL[原表JOIN], 快路径 SQL[mv_*])
CASES = [
    (
        "月度GMV趋势",
        "Monthly GMV trend",
        """SELECT CONCAT(YEAR(o.order_purchase_timestamp),'-',LPAD(MONTH(o.order_purchase_timestamp),2,'0')) ym,
                  SUM(oi.price+oi.freight_value) total_gmv
           FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
           WHERE o.order_purchase_timestamp IS NOT NULL GROUP BY ym ORDER BY ym""",
        "SELECT `year_month`, total_gmv FROM mv_monthly_sales ORDER BY `year_month`",
    ),
    (
        "各州GMV排名",
        "State GMV ranking",
        """SELECT c.customer_state, SUM(oi.price+oi.freight_value) total_gmv
           FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
           JOIN customers c ON o.customer_id=c.customer_id
           GROUP BY c.customer_state ORDER BY total_gmv DESC""",
        "SELECT customer_state, SUM(total_gmv) total_gmv FROM mv_state_sales GROUP BY customer_state ORDER BY total_gmv DESC",
    ),
]


def _timed(engine, sql: str, repeat: int = 5) -> float:
    best = float("inf")
    with engine.connect() as conn:
        for _ in range(repeat):
            start = time.perf_counter()
            conn.execute(text(sql)).fetchall()
            best = min(best, time.perf_counter() - start)
    return best


def main(repeat: int = 5) -> None:
    engine = create_engine(get_settings().ro_url, pool_pre_ping=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    print("=== 预聚合性能对比（取每组最优耗时）===", flush=True)
    for name, label, slow_sql, fast_sql in CASES:
        slow = _timed(engine, slow_sql, repeat)
        fast = _timed(engine, fast_sql, repeat)
        speedup = slow / fast if fast > 0 else 0.0
        results.append({"case": name, "label": label, "slow_ms": slow * 1000, "fast_ms": fast * 1000, "speedup": speedup})
        print(f"  {name:<12} 原表JOIN {slow*1000:8.1f} ms | mv_* {fast*1000:7.2f} ms | 加速 {speedup:6.1f}x", flush=True)

    (PROCESSED_DIR / "benchmark_report.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    labels = [r["label"] for r in results]
    slow_ms = [r["slow_ms"] for r in results]
    fast_ms = [r["fast_ms"] for r in results]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([i - 0.2 for i in x], slow_ms, width=0.4, label="Raw JOIN (on-the-fly)", color="#c95050")
    ax.bar([i + 0.2 for i in x], fast_ms, width=0.4, label="Pre-aggregated mv_*", color="#2b8a6e")
    ax.set_yscale("log")
    ax.set_ylabel("Query latency (ms, log scale)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title("Pre-aggregation Performance Benchmark")
    ax.legend()
    for i, r in enumerate(results):
        ax.text(i, max(r["slow_ms"], r["fast_ms"]), f"{r['speedup']:.0f}x", ha="center", va="bottom", fontsize=10)
    fig.tight_layout()
    fig.savefig(PROCESSED_DIR / "benchmark_report.png", dpi=150)
    plt.close(fig)
    print(f"报告已写入 {PROCESSED_DIR / 'benchmark_report.json'} 与 benchmark_report.png", flush=True)


if __name__ == "__main__":
    main()
