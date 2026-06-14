"""绘图工具：确定性地把数据按指定类型与编码渲染为 ECharts 规格。

只负责渲染，不做图表选型。选型与起名由可视化 Agent 决策后调用 build。
"""
from __future__ import annotations

import re

import pandas as pd

PALETTE = ["#D97757", "#6A9FB5", "#B5896A", "#8A8FB5", "#6AB58F", "#B56A9F", "#C9A24B", "#7C9885"]
PRIMARY = "#D97757"


def frame(item):
    return pd.DataFrame(item.get("rows") or [], columns=item.get("columns") or None)


def is_time(col):
    return any(t in str(col).lower() for t in ("year_month", "week", "date", "month", "day"))


def _lead_num(s):
    """区间桶的排序键，如 0-499g→0、1000-1999g→1000、5000g+→5000。year_month、日期、纯州名返回 None。"""
    s = str(s)
    if re.match(r"^\d{4}-\d{2}(-\d{2})?$", s):  # year_month 或日期，不当作区间桶
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", s)
    if m and re.search(r"[a-zA-Z+]|\d-\d", s):  # 含单位 g、加号、或区间 数-数 才算区间桶
        return float(m.group(1))
    return None


def _is_buckets(series):
    vals = series.dropna().unique()
    return len(vals) > 0 and all(_lead_num(v) is not None for v in vals)


def _xsort(d, x, rank_col=None):
    """数字横坐标按从小到大；区间桶按区间起点升序；其余分类在柱状里按指标排名。"""
    if pd.api.types.is_numeric_dtype(d[x]):
        return d.sort_values(x)
    if _is_buckets(d[x]):
        return d.sort_values(x, key=lambda col: col.map(_lead_num))
    if rank_col is not None:
        return d.sort_values(rank_col, ascending=False)
    return d.sort_values(x)


def _sorted_cats(series):
    vals = list(series.dropna().unique())
    if _is_buckets(series):
        return [str(v) for v in sorted(vals, key=_lead_num)]
    try:
        return [str(v) for v in sorted(vals, key=lambda v: float(v))]
    except (ValueError, TypeError):
        return sorted(str(v) for v in vals)


# 旋转的长标签放宽到 108px 再截断，配合 containLabel 自动留白，保证横轴描述能显示
CAT_LABEL = {"rotate": 30, "width": 108, "overflow": "truncate", "ellipsis": "…", "hideOverlap": True, "fontSize": 11}


def _base(_title=None):
    # margins 取小值，containLabel=true 会按坐标轴标签自动留白，避免再叠加大边距浪费底部与左侧
    return {"tooltip": {"trigger": "axis"}, "color": PALETTE,
            "grid": {"left": 14, "right": 22, "bottom": 14, "top": 16, "containLabel": True}}


def _titled(option, title):
    """把居中标题注入 ECharts（短标题不会截断），导出 PNG 时也含标题、图居中。"""
    option["title"] = {"text": title, "left": "center", "top": 6,
                       "textStyle": {"fontSize": 13, "fontWeight": 600, "color": "#3D3929"}}
    if "grid" in option:
        if option.get("legend"):
            option["legend"]["top"] = 30
            option["grid"]["top"] = 60
        else:
            option["grid"]["top"] = 44
    return option


def _line(df, x, y, title):
    d = _xsort(df[[x, y]].dropna(), x)
    o = _base(title)
    o.update({"xAxis": {"type": "category", "data": [str(v) for v in d[x]], "axisLabel": CAT_LABEL},
              "yAxis": {"type": "value"},
              "series": [{"type": "line", "smooth": True, "data": [round(float(v), 2) for v in d[y]],
                          "lineStyle": {"width": 3, "color": PRIMARY}, "itemStyle": {"color": PRIMARY},
                          "areaStyle": {"color": "rgba(217,119,87,0.12)"}}]})
    return o


def _bar(df, x, y, title):
    d = _xsort(df[[x, y]].dropna(), x, rank_col=y).head(20)
    o = _base(title)
    o["tooltip"] = {"trigger": "axis", "axisPointer": {"type": "shadow"}}
    o.update({"xAxis": {"type": "category", "data": [str(v) for v in d[x]], "axisLabel": CAT_LABEL},
              "yAxis": {"type": "value"},
              "series": [{"type": "bar", "barWidth": "55%", "data": [round(float(v), 2) for v in d[y]],
                          "itemStyle": {"color": PRIMARY, "borderRadius": [4, 4, 0, 0]}}]})
    return o


def _grouped_line(df, x, y, g, title):
    d = df[[x, y, g]].dropna()
    xs = _sorted_cats(d[x])
    series = []
    for name, part in d.groupby(g):
        part = part.set_index(part[x].astype(str))
        series.append({"type": "line", "name": str(name), "smooth": True,
                       "data": [round(float(part[y].get(xx)), 2) if xx in part.index else None for xx in xs]})
    o = _base(title)
    o["legend"] = {"top": 26, "type": "scroll"}
    o["grid"]["top"] = 66
    o.update({"xAxis": {"type": "category", "data": xs, "axisLabel": CAT_LABEL},
              "yAxis": {"type": "value"}, "series": series})
    return o


def _scatter(df, x, y, size, label, title):
    cols = [x, y] + ([size] if size else []) + ([label] if label else [])
    d = df[cols].dropna().head(120)
    smax = float(d[size].max()) if size and d[size].max() else 1.0
    data = []
    for _, r in d.iterrows():
        ss = max(8, float(r[size]) / smax * 46) if size else 14
        item = {"value": [round(float(r[x]), 3), round(float(r[y]), 3)], "symbolSize": round(ss, 1)}
        if label:
            item["name"] = str(r[label])
        data.append(item)
    o = _base(title)
    o["tooltip"] = {"trigger": "item"}
    o.update({"xAxis": {"type": "value", "name": x, "scale": True},
              "yAxis": {"type": "value", "name": y, "scale": True},
              "series": [{"type": "scatter", "data": data, "itemStyle": {"color": PRIMARY, "opacity": 0.6}}]})
    return o


def _geo(df, title):
    d = df.dropna(subset=["longitude", "latitude", "total_gmv"])
    gmax = float(d["total_gmv"].max()) or 1.0
    # 气泡直径取 sqrt 缩放，使面积近似与 GMV 成比例；整体调小，避免 SP 过大遮挡
    data = [{"value": [round(float(r["longitude"]), 3), round(float(r["latitude"]), 3), round(float(r["total_gmv"]), 2)],
             "name": str(r.get("customer_state", "")), "symbolSize": round(6 + (float(r["total_gmv"]) / gmax) ** 0.5 * 38, 1)}
            for _, r in d.iterrows()]
    return {
        # dimensions 命名后，tooltip 里 {@GMV} 才能解析为第 3 维数值
        "tooltip": {"trigger": "item", "formatter": "{b}<br/>GMV：{@GMV}"},
        "color": PALETTE,
        # 右侧留 64px 给纵向色带；底部留 30px 让“经度”轴名显示完整
        "grid": {"left": 14, "right": 64, "bottom": 30, "top": 16, "containLabel": True},
        "visualMap": {"type": "continuous", "min": 0, "max": round(gmax), "dimension": 2,
                      "orient": "vertical", "right": 10, "top": "center", "itemHeight": 170, "calculable": True,
                      "text": ["GMV 高", "低"], "textStyle": {"fontSize": 10, "color": "#6b6552"},
                      "inRange": {"color": ["#F0D9CE", "#E6A579", "#D97757", "#A6442A"]}},
        "xAxis": {"type": "value", "name": "经度", "scale": True, "nameLocation": "middle", "nameGap": 24},
        "yAxis": {"type": "value", "name": "纬度", "scale": True, "nameLocation": "middle", "nameGap": 38},
        "series": [{"type": "scatter", "dimensions": ["经度", "纬度", "GMV"], "data": data,
                    "itemStyle": {"opacity": 0.82, "borderColor": "#fff", "borderWidth": 0.5},
                    "label": {"show": True, "formatter": "{b}", "fontSize": 10, "position": "right", "color": "#3D3929"}}],
    }


def _heat_pieces(vmax):
    """按数量级分箱，缓解极端偏斜（如某格 25457、中位仅 133），让小值单元也能上色区分。"""
    colors = ["#F5EFE8", "#F0D9CE", "#E6A579", "#D97757", "#C0563E", "#A6442A"]
    edges = [e for e in (10, 100, 1000, 10000, 100000) if e < vmax] + [vmax]
    pieces = [{"max": edges[0], "color": colors[0]}]
    for k in range(len(edges) - 1):
        pieces.append({"min": edges[k], "max": edges[k + 1], "color": colors[min(k + 1, len(colors) - 1)]})
    return pieces


def _heatmap(df, xc, yc, vc, title):
    d = df[[xc, yc, vc]].dropna()
    xs = _sorted_cats(d[xc])
    ys = _sorted_cats(d[yc])
    xi, yi = {v: i for i, v in enumerate(xs)}, {v: i for i, v in enumerate(ys)}
    data = [[xi[str(r[xc])], yi[str(r[yc])], round(float(r[vc]), 2)] for _, r in d.iterrows()]
    vmax = max((p[2] for p in data), default=1)
    o = _base(title)
    o["tooltip"] = {"trigger": "item"}
    o["grid"]["bottom"] = 76
    o.update({"xAxis": {"type": "category", "data": xs, "axisLabel": CAT_LABEL, "splitArea": {"show": True}},
              "yAxis": {"type": "category", "data": ys, "splitArea": {"show": True}},
              # 分段(piecewise)对数级色阶，避免线性刻度下小值单元全部发白
              "visualMap": {"type": "piecewise", "dimension": 2, "pieces": _heat_pieces(vmax),
                            "orient": "horizontal", "left": "center", "bottom": 2, "itemWidth": 14, "itemHeight": 12},
              "series": [{"type": "heatmap", "data": data,
                          "itemStyle": {"borderColor": "#fff", "borderWidth": 1}}]})
    return o


def _pie(df, name, value, title):
    d = df[[name, value]].dropna()
    d = d[pd.to_numeric(d[value], errors="coerce") > 0].sort_values(value, ascending=False).head(12)
    data = [{"name": str(r[name]), "value": round(float(r[value]), 2)} for _, r in d.iterrows()]
    return {"tooltip": {"trigger": "item"}, "color": PALETTE, "legend": {"top": 30, "type": "scroll"},
            "series": [{"type": "pie", "radius": ["35%", "65%"], "center": ["50%", "58%"], "data": data,
                        "label": {"formatter": "{b} {d}%"}}]}


def build(chart_type, df, enc, title):
    """按可视化 Agent 给的类型与编码渲染图表。编码非法或构建失败返回 None，作为兜底。

    enc 字段：x, y, series, size, label, value，按图表类型取用。
    """
    try:
        t = (chart_type or "").lower()
        cols = set(df.columns)
        x, y, series = enc.get("x"), enc.get("y"), enc.get("series")
        if df.empty or len(df) < 2:
            return None
        if t == "line" and x in cols and y in cols:
            o = _line(df, x, y, title)
        elif t in ("bar", "column") and x in cols and y in cols:
            o = _bar(df, x, y, title)
        elif t in ("grouped_line", "multi_line", "multiline") and {x, y, series} <= cols:
            o = _grouped_line(df, x, y, series, title)
        elif t == "pie" and x in cols and y in cols:
            o = _pie(df, x, y, title)
        elif t == "scatter" and x in cols and y in cols:
            size = enc.get("size") if enc.get("size") in cols else None
            label = enc.get("label") if enc.get("label") in cols else None
            o = _scatter(df, x, y, size, label, title)
        elif t == "heatmap" and {x, y} <= cols and enc.get("value") in cols:
            o = _heatmap(df, x, y, enc["value"], title)
        elif t == "geo" and {"longitude", "latitude"} <= cols and "total_gmv" in cols:
            o = _geo(df, title)
        else:
            return None
        return _titled(o, title)
    except Exception:
        return None


def make_spec(item, idx, chart_type, title, option):
    return {"id": f"r{idx}", "title": title, "type": chart_type, "source": item.get("source"),
            "route": item.get("route"), "matched_view": item.get("matched_view"),
            "elapsed_ms": item.get("elapsed_ms"), "sql": item.get("sql"), "option": option}


def chart_signature(ch):
    """用于去重。同类型加同 x 轴加同首序列数据视为重复图。返回可哈希的字符串。"""
    import json
    o = ch.get("option", {})
    x = (o.get("xAxis") or {}).get("data") or []
    s = o.get("series") or [{}]
    sd = s[0].get("data") or []
    return json.dumps([ch.get("type"), x, sd], default=str, ensure_ascii=False)[:3000]


def forecast_chart(p):
    hx, fx = p["hx"], p["fx"]
    x = hx + fx
    nh = len(hx)
    o = _base()
    o["legend"] = {"top": 4, "data": ["历史", "预测", "置信区间"]}
    o["grid"]["top"] = 34
    o.update({"xAxis": {"type": "category", "data": x, "axisLabel": CAT_LABEL}, "yAxis": {"type": "value"},
              "series": [
                  {"name": "置信区间", "type": "line", "stack": "c", "symbol": "none", "lineStyle": {"opacity": 0},
                   "areaStyle": {"opacity": 0}, "data": [None] * nh + p["lo"]},
                  {"name": "置信区间", "type": "line", "stack": "c", "symbol": "none", "lineStyle": {"opacity": 0},
                   "areaStyle": {"color": "rgba(217,119,87,0.18)"},
                   "data": [None] * nh + [round(u - l, 2) for u, l in zip(p["hi"], p["lo"])]},
                  {"name": "历史", "type": "line", "smooth": True, "data": p["hy"] + [None] * len(fx),
                   "lineStyle": {"width": 2.5, "color": "#6A9FB5"}, "itemStyle": {"color": "#6A9FB5"}},
                  {"name": "预测", "type": "line", "smooth": True, "data": [None] * nh + p["yhat"],
                   "lineStyle": {"width": 2.5, "type": "dashed", "color": PRIMARY}, "itemStyle": {"color": PRIMARY}}]})
    title = f"{p.get('label', '指标')} 历史与预测"
    return {"id": "forecast", "title": title, "type": "forecast", "source": "mv_*", "option": _titled(o, title)}


def whatif_chart(p):
    lo = min(p["cur"], p["sim"])
    o = {"tooltip": {"trigger": "axis"}, "color": PALETTE,
         "grid": {"left": 48, "right": 24, "bottom": 30, "top": 18, "containLabel": True},
         "xAxis": {"type": "category", "data": ["现状", "假设后"]},
         "yAxis": {"type": "value", "min": (round(lo * 0.9, 2) if lo > 0 else None)},
         "series": [{"type": "bar", "barWidth": "45%", "label": {"show": True, "position": "top"},
                     "itemStyle": {"color": PRIMARY, "borderRadius": [4, 4, 0, 0]},
                     "data": [round(p["cur"], 3), round(p["sim"], 3)]}]}
    title = f"What-if · {p.get('label', '指标')}前后对比"
    return {"id": "whatif", "title": title, "type": "bar", "source": "what-if", "option": _titled(o, title)}


def diagnose_chart(payload):
    df = pd.DataFrame(payload.get("rows") or [])
    if df.empty or "avg_dist_km" not in df.columns:
        return None
    o = _scatter(df, "avg_dist_km", "avg_days", "n" if "n" in df.columns else None,
                 "customer_state", "距离 vs 配送时长")
    o["xAxis"]["name"] = "卖家-客户距离(km)"
    o["yAxis"]["name"] = "平均配送(天)"
    title = "诊断 · 地理距离 vs 配送时长"
    return {"id": "diagnose", "title": title, "type": "scatter", "source": "fact+geolocation", "option": _titled(o, title)}


def anomaly_chart(anomalies):
    items = [a for a in anomalies if a.get("value") is not None][:10]
    if not items:
        return None
    xs = [a["scope"] for a in items]
    data = [{"value": a["value"], "itemStyle": {"color": "#C0563E" if a.get("severity") == "high" else "#C9962F"}}
            for a in items]
    o = {"tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}}, "color": PALETTE,
         "grid": {"left": 48, "right": 24, "bottom": 80, "top": 44, "containLabel": True},
         "xAxis": {"type": "category", "data": xs, "axisLabel": CAT_LABEL},
         "yAxis": {"type": "value", "name": "环比% / z"},
         "series": [{"type": "bar", "barWidth": "55%", "data": data}]}
    title = "异常幅度"
    return {"id": "anomaly", "title": title, "type": "bar", "source": "mv_*", "option": _titled(o, title)}


def wordcloud_chart(keywords):
    sent_color = {"pos": "#5E9C7E", "neg": "#C0563E", "topic": "#B5896A"}
    data = [{"name": k["term"], "value": k["count"],
             "textStyle": {"color": sent_color.get(k.get("sentiment"), PRIMARY)}}
            for k in keywords if k.get("term")]
    o = {"tooltip": {"show": True},
         "series": [{"type": "wordCloud", "shape": "circle", "sizeRange": [14, 58], "rotationRange": [-30, 30],
                     "gridSize": 8, "drawOutOfBound": False, "data": data}]}
    return {"id": "wordcloud", "title": "评论词云", "type": "wordcloud", "source": "order_reviews",
            "option": _titled(o, "评论词云（绿正向·红负向·棕主题）")}
