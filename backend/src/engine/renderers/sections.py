from __future__ import annotations
from typing import Dict, List
import os

from langchain_openai import ChatOpenAI

DEFAULT_TEMPLATES: Dict[str, str] = {
    "Executive Summary": (
        "Write an executive summary for firm '{firm}' against framework '{framework}'. "
        "Summarize current posture, key strengths, and key gaps. Max 180 words."
    ),
    "Governance and Risk Management": "Write Governance & Risk Management analysis for '{firm}'.",
    "Technology Operations and Resilience": "Write Technology Operations & Resilience analysis for '{firm}'.",
    "Cyber Security": "Write Cyber Security analysis for '{firm}'.",
    "Third-Party and Outsourcing Oversight": "Write Third-Party & Outsourcing Oversight analysis for '{firm}'.",
    "Maturity Assessment and Gap Summary": "Write maturity assessment and gap summary for '{firm}' with clear levels.",
    "Recommendations": "Provide prioritized recommendations for '{firm}' with rationale and estimated effort.",
    "Conclusion": "Conclude the report for '{firm}'.",
}

def _make_prompt(title: str, framework: str, firm: str, findings: List[dict], custom: str | None) -> str:
    base = custom or DEFAULT_TEMPLATES.get(title, f"Write the section: {title} for '{firm}'.")
    bullets = []
    for f in findings[:12]:
        bullets.append(f"- {f.get('id','')}: {f.get('assessment','Unknown')} – {f.get('claim','')}")
    ctx = "\n".join(bullets) or "- (no findings)"
    return (
        f"{base}\n\n"
        f"Framework: {framework}\n"
        f"Firm: {firm}\n"
        f"Key Findings:\n{ctx}\n\n"
        "Style: clear, neutral, professional English. No markdown headings ('#'), no asterisks. "
        "Return plain paragraphs and short bullet lists only when needed."
    )

def render_sections(
    framework: str,
    firm: str,
    findings: List[dict],
    selected_sections: List[str],
    prompts: Dict[str, str],
) -> Dict[str, str]:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.3)

    out: Dict[str, str] = {}
    for title in selected_sections:
        prompt = _make_prompt(title, framework, firm, findings, prompts.get(title))
        resp = llm.invoke(prompt)
        out[title] = (getattr(resp, "content", None) or str(resp)).strip()
    return out
