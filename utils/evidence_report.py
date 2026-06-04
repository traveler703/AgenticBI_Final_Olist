"""生成期末提交证据清单：数据、预聚合表、图表和性能报告状态。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from config.settings import OUTPUT_CHARTS_DIR, PROJECT_ROOT, check_raw_data_files
from utils.db import run_select

REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "submission_evidence.md"
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence"
EXPECTED_MVS = [
    "mv_monthly_sales",
    "mv_weekly_sales",
    "mv_state_sales",
    "mv_category_sales",
    "mv_delivery_perf",
    "mv_payment_dist",
    "mv_payment_installment_matrix",
    "mv_weight_freight_bucket",
    "mv_state_geo_sales",
    "mv_review_quality",
    "mv_seller_review_risk",
]


def _database_evidence() -> tuple[list[str], str]:
    rows: list[str] = []
    try:
        df = run_select(
            """
            SELECT table_name, table_rows
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name LIKE 'mv\\_%'
            ORDER BY table_name
            """
        )
        df.columns = [str(column).lower() for column in df.columns]
        found = set(df["table_name"].astype(str))
        for name in EXPECTED_MVS:
            match = df[df["table_name"] == name]
            row_count = int(match.iloc[0]["table_rows"]) if not match.empty else 0
            rows.append(f"| `{name}` | {'已创建' if name in found else '缺失'} | {row_count:,} |")
        return rows, "数据库连接成功"
    except Exception as exc:  # noqa: BLE001
        for name in EXPECTED_MVS:
            rows.append(f"| `{name}` | 待验证 | - |")
        return rows, f"数据库验证未完成：{exc}"


def main() -> None:
    data_ready, missing = check_raw_data_files()
    charts = sorted(OUTPUT_CHARTS_DIR.glob("*.png")) if OUTPUT_CHARTS_DIR.exists() else []
    performance = PROJECT_ROOT / "outputs" / "reports" / "performance_comparison.md"
    performance_image = PROJECT_ROOT / "outputs" / "reports" / "performance_comparison.png"
    dashboard_evidence = EVIDENCE_DIR / "dashboard_nlp_decision.png"
    preaggregation_evidence = EVIDENCE_DIR / "dashboard_preaggregation_sql.png"
    whatif_evidence = EVIDENCE_DIR / "dashboard_whatif_anomaly.png"
    geo_evidence = EVIDENCE_DIR / "chart_state_geo_bubble.png"
    topic_evidence = EVIDENCE_DIR / "chart_review_topics.png"
    mv_rows, database_status = _database_evidence()

    lines = [
        "# 提交证据清单",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 原始数据：{'9 个 CSV 已就绪' if data_ready else f'缺少 {len(missing)} 个 CSV'}",
        f"- 数据库：{database_status}",
        f"- 图表文件：{len(charts)} 个",
        f"- 性能报告：{'Markdown + PNG 已生成' if performance.exists() and performance_image.exists() else '待运行 python -m utils.benchmark'}",
        "",
        "## 物理预聚合表",
        "",
        "| 表名 | 状态 | 估算行数 |",
        "| --- | --- | ---: |",
        *mv_rows,
        "",
        "## 图表证据",
        "",
        *([f"- `{path.relative_to(PROJECT_ROOT)}`" for path in charts] or ["- 待生成"]),
        "",
        "## 提交前人工截图",
        "",
        f"- [{'x' if dashboard_evidence.exists() else ' '}] Streamlit 双栏首页、NLP 与决策建议",
        f"- [{'x' if preaggregation_evidence.exists() else ' '}] SQL 与查询策略展开区，显示命中 `mv_*`",
        f"- [{'x' if geo_evidence.exists() and topic_evidence.exists() else ' '}] 地理气泡图与评论主题图",
        f"- [{'x' if performance_image.exists() else ' '}] 预聚合性能对比图",
        f"- [{'x' if whatif_evidence.exists() else ' '}] What-if、异常检测与决策建议结果",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"提交证据清单已写入：{REPORT_PATH}")


if __name__ == "__main__":
    main()
