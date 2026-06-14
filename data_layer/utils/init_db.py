"""一键编排离线建库。

顺序：建库(admin) → 版本迁移(账号/schema/索引/日志表) → 清洗装载9表(etl) → 刷新6+预聚合表(etl) + 自校验。
跑完即退出，不常驻。

入口：python -m utils.init_db
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import check_raw_data_files, get_settings


def ensure_database() -> None:
    settings = get_settings()
    engine = create_engine(settings.admin_server_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(
            f"\n无法连接 MySQL：{settings.host}:{settings.port}\n  原因：{exc}\n\n"
            "请确认 MySQL 已启动（docker run ... mysql:8）且 .env 连接信息正确。\n"
        )
        raise SystemExit(1) from exc
    print(f"数据库 `{settings.database}` 就绪。", flush=True)


def main() -> None:
    ok, missing = check_raw_data_files()
    if not ok:
        print("错误：以下 CSV 未找到，请放入 data/raw/：")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    print("========== 阶段 A：离线数据处理 ==========", flush=True)
    ensure_database()

    print("\n--- 1/3 数据库版本迁移 ---", flush=True)
    from utils.migrate import apply_migrations
    apply_migrations()

    print("\n--- 2/3 清洗装载基础表 ---", flush=True)
    from utils.load import main as load_main
    load_main()

    print("\n--- 3/3 刷新预聚合表 + 自校验 ---", flush=True)
    from utils.refresh_aggregations import refresh
    refresh()

    print("\n========== init_db 完成，数据底座已就绪 ==========", flush=True)


if __name__ == "__main__":
    main()
