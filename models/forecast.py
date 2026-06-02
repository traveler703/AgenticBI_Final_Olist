"""基于 mv_monthly_sales 的销售额预测。"""
from __future__ import annotations

import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from utils.db import run_select


def forecast_next_6_periods() -> pd.DataFrame:
    df = run_select("SELECT `year_month`, total_gmv FROM mv_monthly_sales ORDER BY `year_month`")
    if df.empty or len(df) < 6:
        return pd.DataFrame(columns=["year_month", "yhat", "yhat_lower", "yhat_upper"])

    ts = pd.to_numeric(df["total_gmv"], errors="coerce").fillna(method="ffill")
    model = ExponentialSmoothing(ts, trend="add", seasonal=None)
    fitted = model.fit(optimized=True)
    pred = fitted.forecast(6)
    std = float(ts.std()) if len(ts) > 1 else 0.0

    last_ym = pd.Period(df["year_month"].iloc[-1], freq="M")
    periods = [(last_ym + i).strftime("%Y-%m") for i in range(1, 7)]
    out = pd.DataFrame({"year_month": periods, "yhat": pred.values})
    out["yhat_lower"] = out["yhat"] - 1.96 * std
    out["yhat_upper"] = out["yhat"] + 1.96 * std
    return out
