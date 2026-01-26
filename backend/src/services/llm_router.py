# backend/src/services/llm_router.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import os
import requests
import json

# We reuse your existing OpenAI wrapper if you already have it.
# It should expose: chat_complete(messages, temperature, max_tokens, response_format)
try:
    from services.openai_client import chat_complete as _openai_chat
except Exception:
    _openai_chat = None


def _xai_chat_complete(
    *,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 1000,
    response_format: Optional[str] = None,
) -> str:
    """
    Minimal Grok/xAI client using HTTP.
    Env: XAI_API_KEY
    Endpoint: https://api.x.ai/v1/chat/completions
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # If you request JSON output, xAI expects tool-ish patterns; we keep simple text here.
    # You can extend with tools/json output as needed.

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"xAI error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"xAI unexpected response: {data}")


def chat_complete(
    *,
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 1000,
    response_format: Optional[str] = None,  # "json_object" for OpenAI JSON mode
) -> str:
    """
    Unified chat interface.
    """
    p = (provider or "openai").lower()

    # if p == "openai":
    if p in {"xai", "grok", "openai"}:
        if _openai_chat is None:
            raise RuntimeError("OpenAI client unavailable; ensure services/openai_client.py exists")
        # Your openai_client.chat_complete signature: (messages, response_format, temperature, max_tokens)
        return _openai_chat(
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    elif p in {"xai", "grok"}:
        return _xai_chat_complete(
            model=model or "grok-4-latest",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    else:
        raise ValueError(f"Unknown provider: {provider}")
