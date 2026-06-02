"""
Agentic BI 入口：检查环境后启动 Streamlit 仪表板。
首次使用请先：db_init → etl → refresh_views
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    raw_dir = ROOT / "data" / "raw"
    csv_count = len(list(raw_dir.glob("*.csv"))) if raw_dir.exists() else 0
    if csv_count < 9:
        print(
            "提示：请先将 Olist 的 9 个 CSV 放入：\n"
            f"  {raw_dir}\n"
            "详见 data/raw/README.md"
        )

    dashboard = ROOT / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard)], check=False)


if __name__ == "__main__":
    main()
