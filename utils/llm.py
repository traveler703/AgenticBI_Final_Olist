"""DeepSeek 兼容 OpenAI API 的轻量封装。"""
from __future__ import annotations

from openai import OpenAI

from config.settings import get_settings


def deepseek_chat(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，已回退到规则 SQL。")

    print(f"[llm] DeepSeek request start: model={settings.deepseek_model}", flush=True)
    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=30,
    )
    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    content = response.choices[0].message.content or ""
    print(f"[llm] DeepSeek request done: response_chars={len(content)}", flush=True)
    return content
