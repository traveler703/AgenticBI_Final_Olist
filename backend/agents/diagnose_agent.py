"""诊断 Agent：配送延迟根因下钻。

多表 JOIN，把订单宽表与地理表关联，用 haversine 算卖家到客户的距离，
对每个州汇总平均配送时长、跨州发货比例、平均距离，并给出距离与时长的相关性。
"""
from __future__ import annotations

from agents.common import run_logged

DIAGNOSE_SQL = """
WITH geo AS (
    SELECT geolocation_state st, AVG(geolocation_lat) lat, AVG(geolocation_lng) lng
    FROM geolocation WHERE geolocation_lat BETWEEN -35 AND 6 AND geolocation_lng BETWEEN -75 AND -30
    GROUP BY geolocation_state)
SELECT f.customer_state,
       ROUND(AVG(f.shipping_duration_days),2) avg_days,
       ROUND(100*AVG(CASE WHEN f.seller_state<>f.customer_state THEN 1 ELSE 0 END),1) cross_state_pct,
       ROUND(AVG(6371*2*ASIN(SQRT(POWER(SIN(RADIANS(gc.lat-gs.lat)/2),2)
             + COS(RADIANS(gs.lat))*COS(RADIANS(gc.lat))*POWER(SIN(RADIANS(gc.lng-gs.lng)/2),2)))),0) avg_dist_km,
       COUNT(*) n
FROM fact_order_items f
JOIN geo gc ON f.customer_state=gc.st
JOIN geo gs ON f.seller_state=gs.st
WHERE f.shipping_duration_days IS NOT NULL
GROUP BY f.customer_state HAVING n>=100
ORDER BY avg_days DESC"""


def diagnose_delivery(question="", *, provider=None, model=None, conversation_id=None, emit=lambda e: None):
    emit({"type": "status", "text": "诊断：地理距离下钻…"})
    df, meta = run_logged(DIAGNOSE_SQL, question or "配送延迟地理下钻", conversation_id)
    queries = [meta] if meta else []
    if df is None or df.empty:
        return "诊断查询无结果。", {}, queries
    nat = float(df["avg_days"].mul(df["n"]).sum() / df["n"].sum())
    corr = float(df["avg_days"].corr(df["avg_dist_km"]))
    items = [f"{r.customer_state} {r.avg_days}天 距离{int(r.avg_dist_km)}km 跨州{r.cross_state_pct}%"
             for r in df.head(6).itertuples()]
    text = (f"诊断下钻，关联卖家与客户地理并用 haversine 算距离：全国平均配送 {nat:.1f} 天。"
            f"配送最慢的州为 {'、'.join(items)}。配送时长与卖家客户地理距离的相关系数 {corr:+.2f}，"
            "距离越远且跨州比例越高配送越慢，偏远北部州由距离主导。"
            "聚合只能识别关联，因果仍需结合承运商与仓库处理时长进一步验证。")
    from agents import reflection
    rn = reflection.note(question or "配送诊断", text, provider=provider, model=model, emit=emit)
    if rn:
        text += f"\n反思：{rn}"
    return text, {"rows": df.head(20).to_dict(orient="records")}, queries
