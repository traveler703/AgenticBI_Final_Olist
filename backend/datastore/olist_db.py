"""只读访问 Olist 数据仓库（olist_ro 账号，DB 层兜底防写）。"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text

from core.config import get_settings
from core.sql_guard import sanitize


@lru_cache
def _engine():
    return create_engine(get_settings().olist_ro_url, pool_pre_ping=True)


def read_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    with _engine().connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def run_agent_sql(sql: str) -> tuple[pd.DataFrame, str]:
    safe = sanitize(sql)
    with _engine().connect() as c:
        return pd.read_sql(text(safe), c), safe


def refresh_log(limit: int = 24) -> list[dict]:
    try:
        df = read_df(
            "SELECT mv_name, refreshed_at, source_rows, result_rows, elapsed_ms "
            "FROM mv_refresh_log ORDER BY refreshed_at DESC, id DESC LIMIT :n",
            {"n": limit},
        )
        df["refreshed_at"] = df["refreshed_at"].astype(str)
        return df.to_dict(orient="records")
    except Exception:
        return []
