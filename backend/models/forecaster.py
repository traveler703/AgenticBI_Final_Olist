"""基于周度预聚合数据的稳健短期 GMV 预测（对数尺度阻尼趋势 + 经验区间）。

输入序列取自 mv_weekly_sales；输出未来 N 周 yhat 与置信区间，供预测 Agent 与可视化使用。
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from datastore.olist_db import read_df

DEFAULT_FORECAST_WEEKS = 6
MAX_FORECAST_WEEKS = 52
TRAINING_WEEKS = 39
FORECAST_COLUMNS = ["week_start", "yhat", "yhat_lower", "yhat_upper"]


def _parse_chinese_integer(text: str) -> int | None:
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if "十" in text:
        tens, ones = text.split("十", 1)
        return (digits.get(tens, 1) * 10) + digits.get(ones, 0)
    return digits.get(text)


def extract_forecast_weeks(query: str, default: int = DEFAULT_FORECAST_WEEKS) -> int:
    match = re.search(r"(?:未来|预测(?:未来)?)\s*(\d{1,3})\s*(?:个)?周", query)
    weeks = int(match.group(1)) if match else None
    if weeks is None:
        chinese_match = re.search(r"(?:未来|预测(?:未来)?)\s*([一二两三四五六七八九十]+)\s*(?:个)?周", query)
        weeks = _parse_chinese_integer(chinese_match.group(1)) if chinese_match else None
    return min(max(weeks, 1), MAX_FORECAST_WEEKS) if weeks is not None else default


def load_weekly_sales_history() -> tuple[pd.DataFrame, list[str]]:
    try:
        df = read_df("SELECT week_start, total_gmv, total_orders FROM mv_weekly_sales ORDER BY week_start")
    except Exception as exc:
        if "mv_weekly_sales" not in str(exc).lower():
            raise
        df = read_df(
            "SELECT DATE_SUB(DATE(order_purchase_timestamp), "
            "INTERVAL WEEKDAY(order_purchase_timestamp) DAY) AS week_start, "
            "SUM(item_gmv) AS total_gmv, "
            "COUNT(DISTINCT order_id) AS total_orders "
            "FROM fact_order_items "
            "WHERE order_purchase_timestamp IS NOT NULL "
            "GROUP BY week_start ORDER BY week_start"
        )
    if df.empty:
        return df, []
    history = df.copy()
    history["week_start"] = pd.to_datetime(history["week_start"], errors="coerce")
    history["total_gmv"] = pd.to_numeric(history["total_gmv"], errors="coerce")
    history["total_orders"] = pd.to_numeric(history["total_orders"], errors="coerce")
    history = history.dropna(subset=["week_start", "total_gmv", "total_orders"]).sort_values("week_start")

    gap_groups = history["week_start"].diff().dt.days.ne(7).cumsum()
    longest_group = gap_groups.value_counts().idxmax()
    complete = history[gap_groups == longest_group].copy()

    median_orders = float(complete["total_orders"].median()) if not complete.empty else 0.0
    minimum_orders = max(10.0, median_orders * 0.20)
    while len(complete) >= 12 and float(complete.iloc[0]["total_orders"]) < minimum_orders:
        complete = complete.iloc[1:]
    while len(complete) >= 12 and float(complete.iloc[-1]["total_orders"]) < minimum_orders:
        complete = complete.iloc[:-1]
    excluded = history.loc[~history.index.isin(complete.index), "week_start"].dt.strftime("%Y-%m-%d").tolist()

    if len(complete) < 12:
        complete = history.copy()
        excluded = []
    return complete.reset_index(drop=True), excluded


def fit_forecast(values, periods: int):
    """对任意数值序列拟合对数尺度阻尼趋势，返回 (yhat, lower, upper)。供通用预测使用。"""
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 8:
        return None
    log = np.log1p(np.clip(arr, 0, None))
    fitted = ExponentialSmoothing(log, trend="add", damped_trend=True, seasonal=None).fit(optimized=True, remove_bias=True)
    logp = np.asarray(fitted.forecast(periods), dtype=float)
    resid = np.abs(np.asarray(log - fitted.fittedvalues, dtype=float))
    resid = resid[np.isfinite(resid)]
    margin = float(np.quantile(resid, 0.90)) if len(resid) else 0.0
    pred = np.maximum(np.expm1(logp), 0.0)
    lower = np.maximum(np.expm1(logp - margin), 0.0)
    upper = np.maximum(np.expm1(logp + margin), pred)
    return [round(float(v), 2) for v in pred], [round(float(v), 2) for v in lower], [round(float(v), 2) for v in upper]


def forecast_next_weeks(weeks: int = DEFAULT_FORECAST_WEEKS) -> pd.DataFrame:
    weeks = min(max(int(weeks), 1), MAX_FORECAST_WEEKS)
    history, excluded = load_weekly_sales_history()
    if history.empty or len(history) < 12:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    training = history.tail(TRAINING_WEEKS).copy()
    values = training["total_gmv"].clip(lower=0).astype(float)
    log_values = np.log1p(values)
    model = ExponentialSmoothing(log_values, trend="add", damped_trend=True, seasonal=None)
    fitted = model.fit(optimized=True, remove_bias=True)
    log_prediction = np.asarray(fitted.forecast(weeks), dtype=float)

    residuals = np.asarray(log_values - fitted.fittedvalues, dtype=float)
    finite_residuals = np.abs(residuals[np.isfinite(residuals)])
    margin = float(np.quantile(finite_residuals, 0.90)) if len(finite_residuals) else 0.0

    prediction = np.maximum(np.expm1(log_prediction), 0.0)
    lower = np.maximum(np.expm1(log_prediction - margin), 0.0)
    upper = np.maximum(np.expm1(log_prediction + margin), prediction)

    last_week = pd.Timestamp(history["week_start"].iloc[-1])
    forecast_dates = pd.date_range(last_week + pd.Timedelta(weeks=1), periods=weeks, freq="W-MON")
    out = pd.DataFrame(
        {"week_start": forecast_dates, "yhat": prediction, "yhat_lower": lower, "yhat_upper": upper}
    )
    out.attrs["excluded_incomplete_weeks"] = excluded
    out.attrs["history_start"] = history["week_start"].iloc[0].strftime("%Y-%m-%d")
    out.attrs["history_end"] = history["week_start"].iloc[-1].strftime("%Y-%m-%d")
    out.attrs["training_weeks"] = len(training)
    out.attrs["forecast_weeks"] = weeks
    change_rate = float(prediction[-1] / prediction[0] - 1) if prediction[0] else 0.0
    out.attrs["forecast_change_rate"] = change_rate
    out.attrs["trend_description"] = "短期基准水平基本稳定" if abs(change_rate) < 0.03 else "短期趋势存在变化"
    out.attrs["method"] = "recent 39-week log-scale damped Holt trend with empirical 90% interval"
    return out
