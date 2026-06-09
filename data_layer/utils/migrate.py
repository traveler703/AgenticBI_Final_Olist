"""数据库版本管理（yoyo-migrations）。

用迁移工具自动、按版本、可追踪地执行 DDL。
迁移目录：data_layer/migrations/（0001.accounts / 0002.schema / 0003.indexes / 0004.logs）。
已应用的迁移记录在 yoyo 自建的 _yoyo_migration 表中，重复执行只应用新迁移，幂等。

单独运行：
  python -m utils.migrate            # 应用全部待应用迁移
  python -m utils.migrate --list     # 查看迁移状态
"""
from __future__ import annotations

import sys
from pathlib import Path

from yoyo import get_backend, read_migrations

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import MIGRATIONS_DIR, get_settings


def _backend():
    return get_backend(get_settings().yoyo_url)


def apply_migrations() -> list[str]:
    backend = _backend()
    migrations = read_migrations(str(MIGRATIONS_DIR))
    applied: list[str] = []
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        for migration in to_apply:
            applied.append(migration.id)
        backend.apply_migrations(to_apply)
    if applied:
        print("已应用迁移：" + ", ".join(applied), flush=True)
    else:
        print("无待应用迁移（schema 已是最新）。", flush=True)
    return applied


def list_status() -> None:
    backend = _backend()
    migrations = read_migrations(str(MIGRATIONS_DIR))
    applied_ids = {m.id for m in backend.to_rollback(migrations)}
    for m in migrations:
        mark = "[x]" if m.id in applied_ids else "[ ]"
        print(f"  {mark} {m.id}")


def main() -> None:
    if "--list" in sys.argv:
        list_status()
    else:
        apply_migrations()


if __name__ == "__main__":
    main()
