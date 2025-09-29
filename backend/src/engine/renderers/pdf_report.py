from __future__ import annotations
from typing import Any, Dict, List
from dataclasses import dataclass
from pathlib import Path
import datetime as dt

from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable
)
from reportlab.pdfgen.canvas import Canvas

# ---------- styles ----------
def _stylesheet():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleXL", parent=styles["Title"], fontSize=24, leading=28, spaceAfter=12))
    styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontSize=16, leading=19, spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontSize=10.5, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name="Muted", parent=styles["BodyText"], fontSize=9.5, textColor=colors.grey))
    # Use the existing 'Bullet' from sample stylesheet; don't re-add
    return styles

# ---------- header/footer ----------
def _header_footer(canvas: Canvas, doc):
    canvas.saveState()
    width, height = LETTER
    # brand bar
    canvas.setFillColorRGB(0.11, 0.13, 0.19)  # dark
    canvas.rect(0, height - 0.45 * inch, width, 0.45 * inch, fill=True, stroke=False)
    canvas.setFillColor(colors.whitesmoke)
    canvas.setFont("Helvetica-Bold", 11)
    # No "Compliance Reporter" and no "| Cyber Risk & Compliance Team"
    canvas.drawString(0.7 * inch, height - 0.30 * inch, "SecureEngage")
    # footer
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(width - 0.7 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()

# ---------- flowables ----------
class _SectionAnchor(Flowable):
    def __init__(self, text: str):
        super().__init__()
        self.text = text
    def draw(self):
        # no outline/toc use; keep simple anchor if needed later
        pass

# ---------- main ----------
@dataclass
class PdfMeta:
    framework: str
    firm: str
    generated_at: str

def _title_page(framework: str, firm: str, styles) -> List[Any]:
    now = dt.datetime.now().strftime("%B %d, %Y")
    return [
        Spacer(1, 1.5 * inch),
        Paragraph("Assessment Report", styles["TitleXL"]),
        Spacer(1, 0.1 * inch),
        Paragraph(f"<b>Framework:</b> {framework}", styles["Body"]),
        Paragraph(f"<b>Firm:</b> {firm}", styles["Body"]),
        Paragraph(f"<b>Date:</b> {now}", styles["Body"]),
        Spacer(1, 0.4 * inch),
        Paragraph("Prepared by SecureEngage", styles["Muted"]),
        PageBreak(),
    ]

def _plain_to_paragraphs(text: str, styles) -> List[Any]:
    # Split on blank lines, make paragraphs; support hyphen bullets `- `
    lines = [l.rstrip() for l in text.splitlines()]
    blocks: List[str] = []
    cur: List[str] = []
    for ln in lines + [""]:
        if ln.strip() == "":
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(ln)
    flows: List[Any] = []
    for b in blocks:
        # crude bullet detection
        if b.lstrip().startswith("- "):
            # turn into simple bullet list by replacing "- "->"• "
            blines = [f"• {x.strip()[2:]}" if x.strip().startswith("- ") else x for x in b.splitlines()]
            flows.append(Paragraph("<br/>".join(blines), styles["Body"]))
        else:
            flows.append(Paragraph(b.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles["Body"]))
    if not flows:
        flows.append(Paragraph("—", styles["Body"]))
    return flows

def _section(title: str, body_text: str, styles) -> List[Any]:
    return [
        _SectionAnchor(title),
        Paragraph(title, styles["H1"]),
        *_plain_to_paragraphs(body_text or "", styles),
        Spacer(1, 0.12 * inch),
    ]

def build_pdf(result: Dict[str, Any], out_path: Path) -> Path:
    """
    result: {
      framework, firm, sections: {title: plain_text, ...}, selected_sections: [...]
    }
    """
    styles = _stylesheet()
    story: List[Any] = []
    framework = result.get("framework", "")
    firm = result.get("firm", "")

    # Title (no TOC, no findings section)
    story += _title_page(framework, firm, styles)

    # Narrative sections (selected order)
    selected = result.get("selected_sections") or list((result.get("sections") or {}).keys())
    for sec in selected:
        prose = (result.get("sections") or {}).get(sec, "")
        story += _section(sec, prose, styles)

    # Build PDF
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=0.8*inch, rightMargin=0.8*inch,
        topMargin=0.9*inch, bottomMargin=0.7*inch,
        title=f"Assessment Report - {firm} ({framework})"
    )
    def _on_page(canvas, d): _header_footer(canvas, d)
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path
