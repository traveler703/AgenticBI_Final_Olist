import numpy as np
import pandas as pd

from agents.data_analyst import choose_sql
from agents.coordinator import coordinator_node
from agents.decision import decision_node
from models.forecast import extract_forecast_weeks, forecast_next_weeks, load_weekly_sales_history


def _weekly_fixture() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=24, freq="W-MON")
    orders = [5] + [100 + index * 3 for index in range(22)] + [2]
    orders[10] = 20  # 连续历史中的真实低谷不应被删除
    gmv = [order_count * 150.0 for order_count in orders]
    return pd.DataFrame({"week_start": dates, "total_gmv": gmv, "total_orders": orders})


def test_weekly_history_only_trims_incomplete_edges(monkeypatch) -> None:
    monkeypatch.setattr("models.forecast.run_select", lambda sql: _weekly_fixture())

    history, excluded = load_weekly_sales_history()

    assert len(history) == 22
    assert history.iloc[0]["week_start"] == pd.Timestamp("2024-01-08")
    assert history.iloc[-1]["week_start"] == pd.Timestamp("2024-06-03")
    assert pd.Timestamp("2024-03-11") in set(history["week_start"])
    assert excluded == ["2024-01-01", "2024-06-10"]


def test_six_week_forecast_is_weekly_and_nonnegative(monkeypatch) -> None:
    monkeypatch.setattr("models.forecast.run_select", lambda sql: _weekly_fixture())

    forecast = forecast_next_weeks(6)

    assert len(forecast) == 6
    assert list(forecast["week_start"].diff().dropna().dt.days) == [7, 7, 7, 7, 7]
    assert np.isfinite(forecast[["yhat", "yhat_lower", "yhat_upper"]].to_numpy()).all()
    assert (forecast[["yhat", "yhat_lower", "yhat_upper"]] >= 0).all().all()
    assert (forecast["yhat_lower"] <= forecast["yhat"]).all()
    assert (forecast["yhat"] <= forecast["yhat_upper"]).all()


def test_forecast_horizon_is_parsed_from_query_and_passed_to_state() -> None:
    assert extract_forecast_weeks("预测未来10周销售额") == 10
    assert extract_forecast_weeks("预测未来十二周销售额") == 12
    assert extract_forecast_weeks("预测销售额") == 6
    assert extract_forecast_weeks("预测未来100周销售额") == 52
    assert coordinator_node({"user_query": "预测未来10周销售额"})["forecast_weeks"] == 10


def test_ten_week_forecast_returns_ten_rows(monkeypatch) -> None:
    monkeypatch.setattr("models.forecast.run_select", lambda sql: _weekly_fixture())

    forecast = forecast_next_weeks(10)

    assert len(forecast) == 10
    assert forecast.attrs["forecast_weeks"] == 10


def test_forecast_query_uses_weekly_preaggregation() -> None:
    _, source = choose_sql("根据历史订单趋势，预测未来6周销售额")
    assert source == "mv_weekly_sales"


def test_decision_reports_requested_horizon_without_negative_values(monkeypatch) -> None:
    forecast = pd.DataFrame(
        {
            "week_start": pd.date_range("2024-06-10", periods=10, freq="W-MON"),
            "yhat": [100.0] * 10,
            "yhat_lower": [80.0] * 10,
            "yhat_upper": [120.0] * 10,
        }
    )
    forecast.attrs["trend_description"] = "短期基准水平基本稳定"
    forecast.attrs["forecast_change_rate"] = 0.0
    monkeypatch.setattr("agents.decision.forecast_next_weeks", lambda weeks: forecast)
    monkeypatch.setattr("agents.decision.deepseek_chat", lambda *args, **kwargs: "建议内容")

    result = decision_node(
        {
            "user_query": "预测未来10周销售额",
            "need_decision": True,
            "data_summary": "预测输入已准备。",
        }
    )

    assert "未来10周 GMV 合计约 1,000" in result["final_answer"]
    assert "短期基准水平基本稳定" in result["final_answer"]
    assert "运营建议由LLM" in result["final_answer"]
    assert "未来6期末" not in result["final_answer"]
    assert result["forecast_result"]["forecast_lower"] == 800.0
    assert result["forecast_result"]["forecast_weeks"] == 10
    assert result["advice_source"] == "LLM"
