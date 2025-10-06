from __future__ import annotations
import os, json
from typing import List, Dict, Any, Optional

try:
    from openai import OpenAI
except Exception as e:
    raise RuntimeError("openai package not installed. pip install openai>=1.30") from e

def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

def _model() -> str:
    # small, fast, cheap default; override by env if you like
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

def chat_complete(
    *,
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    response_format: Optional[str] = None,   # "json_object" or None
) -> str:
    """
    messages: [{"role":"system"|"user"|"assistant","content": "..."}]
    response_format: if "json_object", we set {"type":"json_object"} safely.
    Returns assistant text content.
    """
    client = _client()
    kwargs: Dict[str, Any] = {
        "model": _model(),
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)
    if response_format == "json_object":
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content or "").strip()
    return content