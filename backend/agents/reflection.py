"""反思组件。

让 Agent 在行动之后对结果做一次评估反思，判断是否真实、完整地回答了问题，
据此决定是否需要修正再来一轮。这是 Reflexion 模式，用于提升结论的可靠性。
元与评论这类简单 Agent 不接入。
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from llm.client import chat

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"
REFLECTION_SYSTEM = (
    PROMPT_DIR / "reflection_system_prompt.txt"
).read_text(encoding="utf-8")

def reflect(question, draft, evidence, *, provider=None, model=None, emit=lambda e: None):
    """评估一步结果，返回 {ok, issue, suggestion}。失败时默认通过，不阻断主流程。"""
    emit({"type": "status", "text": "反思：评估结果是否充分准确…"})
    user = f"用户问题：{question}\n待评估结论：{draft}\n已用证据：{evidence}"
    try:
        raw = chat(REFLECTION_SYSTEM, user, provider=provider, model=model, temperature=0.0)
        obj = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        return {"ok": bool(obj.get("ok", True)), "issue": obj.get("issue", ""), "suggestion": obj.get("suggestion", "")}
    except Exception:
        return {"ok": True, "issue": "", "suggestion": ""}


def note(question, draft, *, provider=None, model=None, emit=lambda e: None):
    """对分析结果给一句反思自评，附在结论后，提示局限或风险。失败返回空串。"""
    emit({"type": "status", "text": "反思：自评结论局限…"})
    system = ("你是分析质检员。用一句不超过40字的中文，指出下面分析结论的主要局限或需注意的风险，"
              "例如样本不足、相关非因果、代理指标、数据边界。无明显局限则输出空字符串。只输出这句话。")
    try:
        t = chat(system, f"问题：{question}\n结论：{draft}", provider=provider, model=model, temperature=0.2).strip()
        return t if t and len(t) < 60 else ""
    except Exception:
        return ""
