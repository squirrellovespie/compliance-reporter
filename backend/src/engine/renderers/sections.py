# backend/src/engine/renderers/sections.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
import os

from langchain_openai import ChatOpenAI  # or your OpenAI client
# If you aren’t using LangChain for gen, import your direct OpenAI client instead.

from services.vector_langchain import query as vec_query  # your retriever wrapper

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_POLICY = (
    "You are a compliance reporting assistant. Write concise, defensible prose. "
    "Ground every claim in retrieved context; if evidence is insufficient, say so."
)

def _prep_messages(
    overarching_prompt: Optional[str],
    section_name: str,
    section_prompt: str,
    firm: str,
    framework: str,
    retrieved_snippets: List[str],
) -> List[Dict[str, str]]:
    system_text = SYSTEM_POLICY
    if overarching_prompt:
        # Prepend user-provided global guidance
        system_text = f"{overarching_prompt.strip()}\n\n{SYSTEM_POLICY}"

    # Build a compact context block
    context_block = "\n\n".join([f"- {s.strip()}" for s in retrieved_snippets[:10]])

    user_text = (
        f"Framework: {framework}\nFirm: {firm}\n"
        f"Section: {section_name}\n\n"
        f"Section instructions:\n{section_prompt}\n\n"
        f"Top evidence snippets:\n{context_block}\n\n"
        "Write the section. If specific details are missing in the evidence, state that explicitly."
    )

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]

def _retrieve_for_section(framework: str, firm: str, section_prompt: str) -> List[str]:
    # retrieve from both framework index and firm uploads/assessment
    snippets: List[str] = []

    # framework chunks
    fw_results = vec_query(collection_name=f"fw_{framework}", text=section_prompt, k=6)
    snippets += [r["text"] for r in fw_results]

    # firm assessment / evidence
    asmt_results = vec_query(collection_name=f"asmt_{firm}", text=section_prompt, k=6)
    ev_results = vec_query(collection_name=f"ev_{firm}", text=section_prompt, k=6)
    snippets += [r["text"] for r in (asmt_results + ev_results)]

    return snippets

def render_sections(
    framework: str,
    firm: str,
    findings: List[Dict[str, Any]],
    sections: List[Dict[str, Any]],
    prompt_overrides: Dict[str, str],
    overarching_prompt: Optional[str] = None,
) -> Dict[str, str]:
    """
    Returns {section_name: markdown}
    """
    llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=0.2)
    out: Dict[str, str] = {}

    # Make a quick “findings summary” string available to all sections if you want to include it
    findings_bullets = [
        f"* {f.get('id','')}: {f.get('assessment','Unknown')} — {f.get('claim','')}"
        for f in findings
    ]
    # You can weave this into the user message if desired.

    for s in sections:
        sec_name = s["name"]
        base_prompt = s.get("default_prompt", f"Write the '{sec_name}' section.")
        section_prompt = prompt_overrides.get(s["id"], base_prompt)

        # Retrieve
        snippets = _retrieve_for_section(framework, firm, section_prompt)

        # Build messages and generate
        messages = _prep_messages(
            overarching_prompt=overarching_prompt,
            section_name=sec_name,
            section_prompt=section_prompt,
            firm=firm,
            framework=framework,
            retrieved_snippets=snippets,
        )

        resp = llm.invoke(messages)  # if using LC ChatOpenAI
        out[sec_name] = resp.content.strip()

    return out
