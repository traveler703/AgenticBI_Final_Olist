from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from config.settings import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(settings.mysql_url, pool_pre_ping=True)


def run_select(sql: str, params: dict | None = None) -> pd.DataFrame:
    normalized = sql.strip().lower()
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("只允许执行 SELECT/WITH 查询语句。")
    forbidden = (" update ", " delete ", " drop ", " truncate ", " insert ", " alter ", " create ")
    wrapped = f" {normalized} "
    if any(token in wrapped for token in forbidden):
        raise ValueError("检测到非只读 SQL 关键字，已拒绝执行。")

    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)
