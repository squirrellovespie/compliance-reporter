# backend/src/engine/renderers/pdf_report.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import datetime as dt
import os
import re

from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable, KeepTogether,
    ListFlowable, ListItem, Image as RLImage,
)
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

# ────────────────────────────────────────────────────────────────────────────────
# Brand asset (logo)
# ────────────────────────────────────────────────────────────────────────────────
def _logo_path() -> Optional[str]:
    """
    Returns the absolute path to the brand logo PNG if available.
    Priority:
      1) env BRAND_LOGO_PATH
      2) backend/src/assets/seal_logo.png
    """
    env = os.getenv("BRAND_LOGO_PATH")
    if env and Path(env).exists():
        return env
    default = Path(__file__).resolve().parents[2] / "assets" / "seal_logo.png"
    return str(default) if default.exists() else None

# ────────────────────────────────────────────────────────────────────────────────
# Styles
# ────────────────────────────────────────────────────────────────────────────────
def _stylesheet():
    styles = getSampleStyleSheet()

    def upsert(name, **kwargs):
        if name in styles.byName:
            base = styles[name]
            for k, v in kwargs.items():
                setattr(base, k, v)
            styles.byName[name] = base
        else:
            parent = kwargs.pop("parent", styles["BodyText"])
            styles.add(ParagraphStyle(name=name, parent=parent, **kwargs))

    # Body
    upsert("Body", parent=styles["BodyText"], fontSize=10.5, leading=14, spaceAfter=6)

    # Headings hierarchy (H1–H4)
    upsert("TitleXL", parent=styles["Title"], fontSize=24, leading=28, spaceAfter=14)
    upsert("H1", parent=styles["Heading1"], fontSize=16, leading=19, spaceBefore=12, spaceAfter=6)
    upsert("H2", parent=styles["Heading2"], fontSize=13.5, leading=17, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1F2937"))
    upsert("H3", parent=styles["Heading3"], fontSize=12, leading=15, spaceBefore=8, spaceAfter=2, textColor=colors.HexColor("#374151"))
    upsert("H4", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#4B5563"))

    # Muted / Small text
    upsert("Muted", parent=styles["BodyText"], fontSize=9.5, textColor=colors.grey)
    upsert("Small", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.black)

    # Bullets (safe)
    upsert("Bullet", parent=styles["BodyText"], fontSize=10.5, leading=14, leftIndent=14, spaceBefore=2, spaceAfter=2)

    # Table text
    upsert("TableCell", parent=styles["BodyText"], fontSize=10, leading=13)
    upsert("TableHeader", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#111827"))

    # Caption
    upsert("Caption", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#6B7280"), spaceBefore=2, spaceAfter=6)

    return styles

# ────────────────────────────────────────────────────────────────────────────────
# Header / Footer
# ────────────────────────────────────────────────────────────────────────────────
def _header_footer(canvas: Canvas, doc):
    """
    Minimal footer only: page number.
    No colored bars, no company name on each page.
    """
    canvas.saveState()
    width, height = LETTER
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(width - 0.7 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()

# ────────────────────────────────────────────────────────────────────────────────
# Flowables
# ────────────────────────────────────────────────────────────────────────────────
class _SectionAnchor(Flowable):
    def __init__(self, text: str):
        super().__init__()
        self.text = text
    def draw(self):
        pass

# ────────────────────────────────────────────────────────────────────────────────
# Title Page
# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class PdfMeta:
    framework: str
    firm: str
    generated_at: str

def _title_page(framework: str, firm: str, styles) -> List[Any]:
    """
    Title page with centered logo (if available) and no additional design elements.
    Also shows the local timestamp.
    """
    now = dt.datetime.now().astimezone()
    # Example: October 31, 2025 at 02:36 PM ADT
    stamp = now.strftime("%B %d, %Y at %I:%M %p %Z")

    flows: List[Any] = []
    flows.append(Spacer(1, 1.0 * inch))

    # Logo (optional) – slightly larger than before
    lp = _logo_path()
    if lp:
        img = RLImage(lp)
        # Increased max footprint
        max_w, max_h = (4.0 * inch, 1.3 * inch)
        iw, ih = img.wrap(0, 0)
        scale = min(max_w / iw, max_h / ih)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        flows += [img, Spacer(1, 0.40 * inch)]
    else:
        flows += [Spacer(1, 0.10 * inch)]

    # More formal title
    flows += [
        Paragraph("Cybersecurity Assessment Report", styles["TitleXL"]),
        Spacer(1, 0.12 * inch),
        Paragraph(f"<b>Framework:</b> {framework}", styles["Body"]),
        Paragraph(f"<b>Firm:</b> {firm}", styles["Body"]),
        Paragraph(f"<b>Generated:</b> {stamp}", styles["Body"]),
        Spacer(1, 0.4 * inch),
        Paragraph("Prepared by SecureEngage", styles["Muted"]),
        PageBreak(),
    ]
    return flows

# ────────────────────────────────────────────────────────────────────────────────
# Markdown-ish renderer (headings, lists, tables, paragraphs)
# ────────────────────────────────────────────────────────────────────────────────
_inline_bold = re.compile(r'\*\*(.+?)\*\*')
_inline_ital = re.compile(r'\*(.+?)\*')

def _md_inline(text: str) -> str:
    # Basic inline markup: **bold**, *italic*, line breaks
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _inline_bold.sub(r'<b>\1</b>', text)
    text = _inline_ital.sub(r'<i>\1</i>', text)
    text = text.replace("\n", "<br/>")
    return text

def _split_md_blocks(md: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in (md or "").splitlines():
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
    Returns a list of tuples among:
      ("h", level:int, text)
      ("ol", [items])
      ("ul", [items])
      ("table", headers:list[str], rows:list[list[str]])
      ("p", text)
    """
    # Heading
    first = block.splitlines()[0]
    m = re.match(r'^(#{1,6})\s+(.*)$', first)
    if m:
        return [("h", len(m.group(1)), m.group(2).strip())]

    lines = block.splitlines()

    # Table (Markdown pipe style)
    if any("|" in l for l in lines) and any(re.match(r'^\s*\|?[:\- ]+\|[:\- \|]+\|?\s*$', l) for l in lines):
        norm = [l.strip() for l in lines if l.strip()]
        header_line = norm[0]
        data_lines = norm[2:] if len(norm) > 2 else []

        def split_row(row: str) -> List[str]:
            row = row.strip()
            if row.startswith("|"): row = row[1:]
            if row.endswith("|"): row = row[:-1]
            return [c.strip() for c in row.split("|")]

        headers = split_row(header_line)
        rows = [split_row(dl) for dl in data_lines if "|" in dl]
        return [("table", headers, rows)]

    # Unordered list
    if all(re.match(r'^\s*[-*]\s+.+$', ln) for ln in lines):
        items = [re.sub(r'^\s*[-*]\s+', '', ln).strip() for ln in lines]
        return [("ul", items)]

    # Ordered list
    if all(re.match(r'^\s*\d+\.\s+.+$', ln) for ln in lines):
        items = [re.sub(r'^\s*\d+\.\s+', '', ln).strip() for ln in lines]
        return [("ol", items)]

    # Paragraph
    return [("p", block.strip())]

# ────────────────────────────────────────────────────────────────────────────────
# Tables
# ────────────────────────────────────────────────────────────────────────────────
def _auto_col_widths(data: List[List[str]], font_name="Helvetica", font_size=10, max_total=6.5*inch) -> List[float]:
    """Heuristic column widths based on content length, capped to page width."""
    if not data or not data[0]:
        return []
    cols = len(data[0])
    max_w = [0.0] * cols
    for row in data:
        for i, cell in enumerate(row[:cols]):
            text = str(cell)
            w = stringWidth(text, font_name, font_size) + 10
            if w > max_w[i]:
                max_w[i] = w
    total = sum(max_w)
    if total <= max_total:
        return max_w
    scale = max_total / total
    return [w * scale for w in max_w]

def _make_table(headers: List[str], rows: List[List[str]], styles) -> Table:
    head = [Paragraph(_md_inline(h), styles["TableHeader"]) for h in headers]
    body = [[Paragraph(_md_inline(c), styles["TableCell"]) for c in r] for r in rows]
    data = [head] + body
    col_widths = _auto_col_widths([[str(c) for c in row] for row in ([headers] + rows)], font_size=10)

    tbl = Table(data, colWidths=col_widths or None, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F3F4F6")),
        ("LINEABOVE", (0,0), (-1,0), 0.6, colors.HexColor("#D1D5DB")),
        ("LINEBELOW", (0,0), (-1,0), 0.6, colors.HexColor("#D1D5DB")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E5E7EB")),
        ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    for r in range(1, len(data)):
        if r % 2 == 1:
            tbl.setStyle(TableStyle([("BACKGROUND", (0,r), (-1,r), colors.HexColor("#FAFAFA"))]))
    return tbl

# ────────────────────────────────────────────────────────────────────────────────
# Block → Flowables
# ────────────────────────────────────────────────────────────────────────────────
def _md_to_flowables(md_text: str, styles):
    flows: List[Any] = []
    for block in _split_md_blocks(md_text):
        for kind, *rest in _parse_md_block(block):
            if kind == "h":
                level, txt = rest
                txt = _md_inline(txt)
                if level <= 1:
                    flows.append(Paragraph(txt, styles["H1"]))
                elif level == 2:
                    flows.append(Paragraph(txt, styles["H2"]))
                elif level == 3:
                    flows.append(Paragraph(txt, styles["H3"]))
                else:
                    flows.append(Paragraph(txt, styles["H4"]))
                flows.append(Spacer(1, 4))

            elif kind == "ul":
                items = rest[0]
                lf_items = [ListItem(Paragraph(_md_inline(it), styles["Body"])) for it in items]
                flows.append(ListFlowable(
                    lf_items,
                    bulletType="bullet",
                    bulletFontName="Helvetica",
                    bulletFontSize=9.5,
                    leftIndent=14,
                    bulletIndent=0,
                    bulletSep=" ",
                ))
                flows.append(Spacer(1, 4))

            elif kind == "ol":
                items = rest[0]
                lf_items = [ListItem(Paragraph(_md_inline(it), styles["Body"])) for it in items]
                flows.append(ListFlowable(
                    lf_items,
                    bulletType="1",
                    start=1,
                    bulletFontName="Helvetica",
                    bulletFontSize=9.5,
                    leftIndent=14,
                    bulletIndent=0,
                    bulletSep=". ",
                ))
                flows.append(Spacer(1, 4))

            elif kind == "table":
                headers, rows = rest
                flows.append(_make_table(headers, rows, styles))
                flows.append(Spacer(1, 6))

            elif kind == "p":
                txt = _md_inline(rest[0])
                flows.append(Paragraph(txt, styles["Body"]))
                flows.append(Spacer(1, 2))
    return flows

def _strip_leading_duplicate_heading(section_title: str, md_text: str) -> str:
    lines = (md_text or "").lstrip().splitlines()
    if not lines:
        return md_text or ""
    m = re.match(r'^\s*#{1,6}\s+(.*)$', lines[0])
    if m and m.group(1).strip().lower() == section_title.strip().lower():
        return "\n".join(lines[1:]).lstrip()
    return md_text or ""

def _section(title: str, body_md: str, styles) -> list:
    body_md = _strip_leading_duplicate_heading(title, body_md or "")
    content = [
        Paragraph(title, styles["H1"]),
        *_md_to_flowables(body_md, styles),
    ]
    return [KeepTogether(content), Spacer(1, 0.12 * inch)]

# ────────────────────────────────────────────────────────────────────────────────
# Build
# ────────────────────────────────────────────────────────────────────────────────
def build_pdf(result: Dict[str, Any], out_path: Path) -> Path:
    """
    result: {
      framework, firm, sections: {title: md_text, ...}, selected_sections: [...]
    }
    """
    styles = _stylesheet()
    story: List[Any] = []
    framework = result.get("framework", "")
    firm = result.get("firm", "")

    # Title
    story += _title_page(framework, firm, styles)

    # Sections in selected order (fallback: dict order)
    selected = result.get("selected_sections") or list((result.get("sections") or {}).keys())
    for sec in selected:
        prose_md = (result.get("sections") or {}).get(sec, "") or "—"
        story += _section(sec, prose_md, styles)

    # Build
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=0.8*inch, rightMargin=0.8*inch,
        topMargin=0.9*inch, bottomMargin=0.7*inch,
        title=f"Assessment Report - {firm} ({framework})",
    )
    def _on_page(canvas, d): _header_footer(canvas, d)
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path
