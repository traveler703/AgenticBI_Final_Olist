"""SQL 安全校验：仅只读、单语句、防注入、强制 LIMIT。

与数据库侧的 olist_ro 只读账号双重兜底：即使 guard 漏判，DB 也拒绝写。
"""
from __future__ import annotations

import re

FORBIDDEN = (
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "replace", "grant", "revoke", "into outfile", "load_file", "load data",
    "information_schema", "mysql.", "sleep(", "benchmark(",
)
# 预聚合视图聚合结果通常很小，上限放宽到 2000 以免月度长表等被截断
MAX_LIMIT = 2000


class SqlGuardError(ValueError):
    pass


def sanitize(sql: str, default_limit: int = 1000) -> str:
    """校验并规范化只读 SQL；非法直接抛 SqlGuardError。"""
    if not sql or not sql.strip():
        raise SqlGuardError("空 SQL。")
    cleaned = sql.strip().rstrip(";").strip()

    # 禁止多语句
    if ";" in cleaned:
        raise SqlGuardError("不允许多条语句（检测到分号）。")

    low = cleaned.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise SqlGuardError("只允许 SELECT / WITH 查询。")

    padded = f" {low} "
    for token in FORBIDDEN:
        if token in padded:
            raise SqlGuardError(f"检测到非只读/危险关键字：{token}")

    # 注释注入
    if "--" in cleaned or "/*" in cleaned:
        raise SqlGuardError("不允许 SQL 注释。")

    # 强制 LIMIT 上限
    m = re.search(r"\blimit\s+(\d+)", low)
    if m:
        if int(m.group(1)) > MAX_LIMIT:
            cleaned = re.sub(r"(\blimit\s+)\d+", rf"\g<1>{MAX_LIMIT}", cleaned, flags=re.I)
    else:
        cleaned = f"{cleaned} LIMIT {default_limit}"
    return cleaned
