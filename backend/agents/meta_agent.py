"""元/记忆 Agent：处理与数据分析无关的消息——关于本次对话本身、历史回顾、寒暄。

例：「我上一个问题是什么」「你能做什么」「你好」。由它基于对话历史作答，不查数据库。
"""
from __future__ import annotations

from llm.client import chat_messages

SYSTEM = (
    "你是 Olist BI 助手的对话管理 Agent，只处理与数据分析无关的消息：关于本次对话的元问题"
    "（如用户问‘我上一个问题是什么’‘刚才聊了什么’）、能力介绍、问候与闲聊。"
    "依据提供的对话历史如实、简洁地回答；不要编造数据数字。"
    "若用户其实是在问电商数据，请提示他直接提问业务问题。简体中文。"
)


def run(question, history, *, provider, model):
    msgs = [{"role": "system", "content": SYSTEM}]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": question})
    msg = chat_messages(msgs, provider=provider, model=model, temperature=0.3)
    return msg.content or "（无法回答）"
