"""LLM 抽象层：云(OpenAI 兼容/DeepSeek) 与本地 Ollama 可切换，支持 function-calling。"""
from __future__ import annotations

import httpx
import time
from openai import OpenAI

from core.config import get_settings


class LLMUnavailable(RuntimeError):
    pass


def _resolve(provider, model):
    s = get_settings()
    provider = (provider or s.llm_provider or "cloud").lower()
    if provider == "ollama":
        return "ollama", s.ollama_base_url, "ollama", (model or s.ollama_model)
    if not s.cloud_api_key:
        raise LLMUnavailable("未配置云 API Key。")
    return "cloud", s.cloud_base_url, s.cloud_api_key, (model or s.cloud_model)


def _client(provider, model, timeout=90.0):
    provider, base_url, api_key, model_name = _resolve(provider, model)
    s = get_settings()
    # 本地 Ollama 走 localhost 必须绕过代理；云端 DeepSeek 国内直连更稳，默认也绕过系统代理，
    # 经本地代理(Clash 外区出口)回连国内 API 易出现 SSL EOF。需走代理的 OpenAI 可设 CLOUD_USE_PROXY=true
    bypass_proxy = provider == "ollama" or not s.cloud_use_proxy
    http_client = httpx.Client(trust_env=False, timeout=timeout) if bypass_proxy else None
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=3, http_client=http_client), model_name


def chat(system, user, *, provider=None, model=None, temperature=0.2):
    client, model_name = _client(provider, model)
    try:
        r = client.chat.completions.create(
            model=model_name, temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception as e:
        raise LLMUnavailable(f"调用失败：{e}") from e
    return r.choices[0].message.content or ""


def chat_messages(messages, *, tools=None, provider=None, model=None, temperature=0.2):
    """带历史 + 可选工具的对话，返回原始 message（含 tool_calls）。"""
    client, model_name = _client(provider, model)
    kwargs = dict(model=model_name, temperature=temperature, messages=messages)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        r = client.chat.completions.create(**kwargs)
    except Exception as e:
        raise LLMUnavailable(f"调用失败：{e}") from e
    return r.choices[0].message


def list_models():
    s = get_settings()
    cloud = sorted({s.cloud_model})
    ollama, ok = [], False
    try:
        r = httpx.get(s.ollama_base_url.replace("/v1", "") + "/api/tags", timeout=2.0, trust_env=False)
        if r.status_code == 200:
            ok = True
            ollama = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        ok = False
    return {
        "default_provider": s.llm_provider,
        "providers": {
            "cloud": {"available": bool(s.cloud_api_key), "models": cloud, "default": s.cloud_model},
            "ollama": {"available": ok, "models": ollama or [s.ollama_model], "default": s.ollama_model},
        },
    }


def healthcheck(provider=None, model=None) -> dict:
    """Probe the configured LLM provider without issuing a completion."""
    started = time.perf_counter()
    try:
        client, model_name = _client(provider, model, timeout=5.0)
        client.models.list()
        return {
            "ok": True,
            "provider": (provider or get_settings().llm_provider or "cloud").lower(),
            "model": model_name,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": (provider or get_settings().llm_provider or "cloud").lower(),
            "model": model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc)[:300],
        }
