"""基于周度预聚合数据的稳健短期 GMV 预测。"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from utils.db import run_select

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
    """从自然语言问题中提取预测周数，并限制在适合短期模型的范围内。"""
    match = re.search(r"(?:未来|预测(?:未来)?)\s*(\d{1,3})\s*(?:个)?周", query)
    weeks = int(match.group(1)) if match else None
    if weeks is None:
        chinese_match = re.search(r"(?:未来|预测(?:未来)?)\s*([一二两三四五六七八九十]+)\s*(?:个)?周", query)
        weeks = _parse_chinese_integer(chinese_match.group(1)) if chinese_match else None
    return min(max(weeks, 1), MAX_FORECAST_WEEKS) if weeks is not None else default


def load_weekly_sales_history() -> tuple[pd.DataFrame, list[str]]:
    """读取周度序列，并排除订单量明显不足的不完整边界周。"""
    df = run_select(
        """
        SELECT week_start, total_gmv, total_orders
        FROM mv_weekly_sales
        ORDER BY week_start
        """
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


def forecast_next_weeks(weeks: int = DEFAULT_FORECAST_WEEKS) -> pd.DataFrame:
    """使用对数尺度阻尼趋势预测指定周数，确保 GMV 与区间非负。"""
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
        {
            "week_start": forecast_dates,
            "yhat": prediction,
            "yhat_lower": lower,
            "yhat_upper": upper,
        }
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


def forecast_next_6_weeks() -> pd.DataFrame:
    """兼容旧调用；默认预测未来 6 周。"""
    return forecast_next_weeks(DEFAULT_FORECAST_WEEKS)


def forecast_next_6_periods() -> pd.DataFrame:
    """兼容旧调用；默认业务周期为未来 6 周。"""
    return forecast_next_6_weeks()
