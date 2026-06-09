"""清洗规则。每个函数接收原始 DataFrame，返回清洗后的 DataFrame。

通用：去字段首尾空白；空串统一为 NULL（NaN）；时间戳解析为 datetime，非法置 NULL。
清洗与装载幂等：重复执行结果一致。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TIMESTAMP_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            df[col] = df[col].replace({"": np.nan, "nan": np.nan, "NaN": np.nan})
    return df


def _parse_timestamps(df: pd.DataFrame, table: str) -> pd.DataFrame:
    for col in TIMESTAMP_COLUMNS.get(table, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def clean_table(table: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = _strip_strings(df)
    df = _parse_timestamps(df, table)

    if table == "order_items":
        for col in ("price", "freight_value"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[df[col] < 0, col] = np.nan  # 负值置 NULL

    elif table == "products":
        df["product_category_name"] = df["product_category_name"].fillna("unknown")

    elif table == "order_payments":
        df["payment_installments"] = pd.to_numeric(df["payment_installments"], errors="coerce")
        df.loc[df["payment_installments"] < 1, "payment_installments"] = 1  # 归一为 1
        df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce")

    elif table == "order_reviews":
        df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
        df.loc[(df["review_score"] < 1) | (df["review_score"] > 5), "review_score"] = np.nan

    elif table == "customers":
        df["customer_city"] = df["customer_city"].str.lower()
        df["customer_state"] = df["customer_state"].str.upper().str.slice(0, 2)

    elif table == "sellers":
        df["seller_city"] = df["seller_city"].str.lower()
        df["seller_state"] = df["seller_state"].str.upper().str.slice(0, 2)

    elif table == "geolocation":
        df["geolocation_city"] = df["geolocation_city"].str.lower()
        df["geolocation_state"] = df["geolocation_state"].str.upper().str.slice(0, 2)
        df["geolocation_lat"] = pd.to_numeric(df["geolocation_lat"], errors="coerce")
        df["geolocation_lng"] = pd.to_numeric(df["geolocation_lng"], errors="coerce")

    elif table == "product_category_name_translation":
        # 去 BOM：translation 文件首列可能带
        df = df.rename(columns={c: c.replace("﻿", "") for c in df.columns})

    # 交给 to_sql：pandas 的 NaN/NaT 会自动写入 SQL NULL（无需逐格替换，避免大表变慢）
    return df
