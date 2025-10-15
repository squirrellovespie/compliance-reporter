from __future__ import annotations
from typing import Any, Dict, List
from dataclasses import dataclass
from pathlib import Path
import datetime as dt
import re

from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable, KeepTogether,
    ListFlowable, ListItem,
)
from reportlab.pdfgen.canvas import Canvas

# ---------- styles ----------
def _stylesheet():
    styles = getSampleStyleSheet()

    def upsert(name, **kwargs):
        """Create or update a ParagraphStyle safely."""
        if name in styles.byName:
            # Update existing style (keep parent if not provided)
            base = styles[name]
            for k, v in kwargs.items():
                setattr(base, k, v)
            styles.byName[name] = base
        else:
            parent = kwargs.pop("parent", styles["BodyText"])
            styles.add(ParagraphStyle(name=name, parent=parent, **kwargs))

    # Body alias (ReportLab has BodyText; we expose Body for our code)
    upsert("Body", parent=styles["BodyText"], fontSize=10.5, leading=14, spaceAfter=6)

    # Headings
    upsert("TitleXL", parent=styles["Title"], fontSize=24, leading=28, spaceAfter=12)
    upsert("H1", parent=styles["Heading1"], fontSize=16, leading=19, spaceBefore=12, spaceAfter=6)
    upsert("H2", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=10, spaceAfter=6)

    # Muted / Small text
    upsert("Muted", parent=styles["BodyText"], fontSize=9.5, textColor=colors.grey)
    upsert("Small", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.black)

    # Bullets (avoid duplicate KeyError by upserting)
    upsert("Bullet", parent=styles["BodyText"], fontSize=10.5, leading=14,
           leftIndent=14, spaceBefore=2, spaceAfter=2)

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

def _md_inline(text: str) -> str:
    """
    Minimal inline markdown -> ReportLab-friendly markup:
    **bold**, *italics*, line breaks.
    """
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = text.replace("\n", "<br/>")
    return text

def _split_md_blocks(md: str) -> list[str]:
    # split on blank lines
    parts: list[str] = []
    buf: list[str] = []
    for line in md.splitlines():
        if line.strip() == "":
            if buf:
                parts.append("\n".join(buf))
                buf = []
        else:
            buf.append(line.rstrip())
    if buf:
        parts.append("\n".join(buf))
    return parts

def _parse_md_block(block: str):
    """
    Yields either:
      ("h", level:int, text)
      ("ol", [items])
      ("ul", [items])
      ("p", text)
    """
    lines = block.splitlines()
    # Headings ### / #### / ## / #
    m = re.match(r'^(#{1,6})\s+(.*)$', lines[0])
    if m:
        level = len(m.group(1))
        return [("h", level, m.group(2).strip())]

    # Lists
    if all(re.match(r'^\s*[-*]\s+.+$', ln) for ln in lines):
        items = [re.sub(r'^\s*[-*]\s+', '', ln).strip() for ln in lines]
        return [("ul", items)]
    if all(re.match(r'^\s*\d+\.\s+.+$', ln) for ln in lines):
        items = [re.sub(r'^\s*\d+\.\s+', '', ln).strip() for ln in lines]
        return [("ol", items)]

    # Paragraph
    return [("p", block.strip())]

def _md_to_flowables(md_text: str, styles):
    """
    Convert a subset of Markdown to ReportLab flowables:
    - Headings (#..######) -> H1/H2/H3 (cap at 3)
    - **bold**, *italic*
    - Bulleted and numbered lists
    - Paragraphs
    """
    flows = []
    for block in _split_md_blocks(md_text):
        for kind, *rest in _parse_md_block(block):
            if kind == "h":
                level, txt = rest
                txt = _md_inline(txt)
                if level <= 1:
                    flows.append(Paragraph(txt, styles["H1"]))
                elif level == 2:
                    flows.append(Paragraph(txt, styles["H2"]))
                else:
                    flows.append(Paragraph(txt, styles["Small"]))
                flows.append(Spacer(1, 4))

            elif kind in ("ul", "ol"):
                items = rest[0]
                lf_items = [
                    ListItem(Paragraph(_md_inline(it), styles["Body"]), leftIndent=0)
                    for it in items
                ]

                if kind == "ul":
                    flows.append(
                        ListFlowable(
                            lf_items,
                            bulletType="bullet",
                            bulletFontName="Helvetica",
                            bulletFontSize=9.5,
                            bulletIndent=0,    
                            leftIndent=14,    
                            bulletSep=" "       
                        )
                    )
                else:  # ordered list
                    flows.append(
                        ListFlowable(
                            lf_items,
                            bulletType="1",   
                            start=1,         
                            bulletFontName="Helvetica",
                            bulletFontSize=9.5,
                            bulletIndent=0,
                            leftIndent=14,
                            bulletSep=". "     
                        )
                    )
                flows.append(Spacer(1, 4))

            elif kind == "p":
                txt = _md_inline(rest[0])
                flows.append(Paragraph(txt, styles["Body"]))
                flows.append(Spacer(1, 2))

    return flows

def _strip_leading_duplicate_heading(section_title: str, md_text: str) -> str:
    """
    If the model repeats the section title as '### <title>' etc.,
    strip that leading heading to avoid double-title.
    """
    lines = md_text.lstrip().splitlines()
    if not lines:
        return md_text
    m = re.match(r'^\s*#{1,6}\s+(.*)$', lines[0])
    if m and m.group(1).strip().lower() == section_title.strip().lower():
        return "\n".join(lines[1:]).lstrip()
    return md_text

def _section(title: str, body_md: str, styles) -> list:
    body_md = _strip_leading_duplicate_heading(title, body_md or "")
    return [
        Paragraph(title, styles["H1"]),
        *_md_to_flowables(body_md, styles),
        Spacer(1, 0.12 * inch),
    ]