"""代码强制声明。

对退货、因果这类容易误读的问题，由代码确定性地补上口径声明，不依赖 LLM 是否听话。
若答案里已含等价声明则跳过，避免重复。
"""
from __future__ import annotations

RETURN_NOTE = ("口径声明：Olist 数据集没有真实退货字段，本分析用差评率，即 review_score 小于等于 2 分，"
               "作为退货风险的代理指标，不等同实际退货率，最终方案建议结合平台内部退货数据交叉验证。")

CAUSAL_NOTE = ("诊断口径：聚合数据可识别关联因素，但不能单独证明因果，"
               "结论需结合订单明细、承运商与仓库处理时长进一步验证。")


def enforce(question, answer):
    q, a = question, answer or ""
    notes = []
    if "退货" in q and not any(k in a for k in ("退货字段", "代理指标", "代理")):
        notes.append(RETURN_NOTE)
    if "为什么" in q and not any(k in a for k in ("不能单独证明因果", "因果", "关联")):
        notes.append(CAUSAL_NOTE)
    if not notes:
        return a
    return a.rstrip() + "\n\n---\n" + "\n".join(f"> {n}" for n in notes)
