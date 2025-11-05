from __future__ import annotations
import os, json, time
from typing import List, Dict, Any, Optional

import requests

# --- Config knobs (env-overridable) ---
_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "4"))
_BACKOFF_BASE = float(os.getenv("AI_BACKOFF_BASE", "0.8"))

# ---------- Utilities ----------
def _sleep_backoff(attempt: int) -> None:
    # attempt starts from 1...
    delay = _BACKOFF_BASE * (2 ** max(0, attempt - 1))
    time.sleep(min(delay, 8.0))

def _should_retry(status: int | None) -> bool:
    return status in (429, 500, 502, 503, 504, 520, 522, 524, 529)

# ---------- Providers ----------
# OPENAI
def _openai_chat_complete(
    *, model: str, messages: List[Dict[str, str]],
    temperature: float, max_tokens: Optional[int], response_format: Optional[str]
) -> str:
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("openai package not installed. pip install openai>=1.30") from e

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    kwargs: Dict[str, Any] = {
        "model": model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)
    if response_format == "json_object":
        kwargs["response_format"] = {"type": "json_object"}

    # basic retry on OpenAI as well
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                _sleep_backoff(attempt)
            else:
                raise RuntimeError(f"OpenAI error: {e}") from e

# XAI (Grok)
def _xai_chat_complete(
    *, model: str, messages: List[Dict[str, str]],
    temperature: float, max_tokens: Optional[int], response_format: Optional[str]
) -> str:
    """
    Pure xAI implementation (no provider fallback).
    - Adds User-Agent and Connection headers (helps CF).
    - Retries with backoff on 5xx / 429.
    - Ignores response_format (xAI can be picky). Enforce JSON by prompt upstream.
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    url = os.getenv("XAI_API_URL", "https://api.x.ai/v1/chat/completions")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": os.getenv("AI_USER_AGENT", "compliance-reporter/1.0"),
        "Connection": "close",
    }
    payload: Dict[str, Any] = {
        "model": model or os.getenv("XAI_CHAT_MODEL", "grok-4-latest"),
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    # We DO NOT send response_format to xAI; enforce JSON via prompt when needed.

    last_status, last_text = None, None
    for attempt in range(1, _MAX_RETRIES + 1):
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        last_status, last_text = r.status_code, r.text
        if r.ok:
            data = r.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if _should_retry(r.status_code) and attempt < _MAX_RETRIES:
            _sleep_backoff(attempt)
            continue
        break

    raise RuntimeError(f"xAI error {last_status}: {last_text}")

# ---------- Public API ----------
def chat_complete(
    *,
    provider: str,
    model: Optional[str],
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    response_format: Optional[str] = None,  # "json_object" or None
) -> str:
    """
    messages: [{"role":"system"|"user"|"assistant","content": "..."}]
    provider: "openai" | "xai"
    model: provider-specific model name
    """
    provider = (provider or os.getenv("AI_PROVIDER", "openai")).lower().strip()

    if provider == "openai":
        return _openai_chat_complete(
            model=model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            messages=messages, temperature=temperature,
            max_tokens=max_tokens, response_format=response_format,
        )
    if provider == "xai":
        # No provider fallback here.
        return _xai_chat_complete(
            model=model or os.getenv("XAI_CHAT_MODEL", "grok-4-latest"),
            messages=messages, temperature=temperature,
            max_tokens=max_tokens, response_format=None,  # ignored
        )

    raise ValueError(f"Unknown provider: {provider}")
