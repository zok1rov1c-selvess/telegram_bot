"""AI tahlil natijasini chiroyli PDF faylga aylantirish.

Yangiliklar:
- Manbalar xulosa so'ngra alohida bo'limda
- Zamonaviy stil
"""
from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config import THEME
from services.fonts import get_unicode_fonts

log = logging.getLogger(__name__)

W, H = A4
DARK    = colors.HexColor(f"#{THEME['dark']}")
PRIMARY = colors.HexColor(f"#{THEME['primary']}")
ACCENT  = colors.HexColor(f"#{THEME['accent']}")
LIGHT   = colors.HexColor(f"#{THEME['light']}")
MUTED   = colors.HexColor(f"#{THEME['muted']}")
WHITE   = colors.white
LINK_C  = colors.HexColor("#1B5E9B")


def _register_fonts() -> tuple[str, str]:
    try:
        reg_path, bold_path = get_unicode_fonts()
        pdfmetrics.registerFont(TTFont("UnicodeR", reg_path))
        pdfmetrics.registerFont(TTFont("UnicodeB", bold_path))
        return "UnicodeR", "UnicodeB"
    except Exception as exc:
        log.warning("Shrift yuklanmadi, Helvetica ishlatiladi: %s", exc)
        return "Helvetica", "Helvetica-Bold"


def _styles(reg: str, bold: str) -> dict:
    return {
        "cover_title": ParagraphStyle(
            "cover_title", fontName=bold, fontSize=26, textColor=WHITE,
            leading=34, spaceAfter=12, alignment=1,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName=reg, fontSize=13, textColor=LIGHT,
            leading=18, alignment=1,
        ),
        "section_heading": ParagraphStyle(
            "section_heading", fontName=bold, fontSize=14, textColor=WHITE,
            backColor=PRIMARY, leading=20, spaceBefore=16, spaceAfter=6,
            leftIndent=-0.5*cm, rightIndent=-0.5*cm,
            borderPadding=(7, 12, 7, 12),
        ),
        "subheading": ParagraphStyle(
            "subheading", fontName=bold, fontSize=12, textColor=DARK,
            leading=16, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName=reg, fontSize=10.5, textColor=DARK,
            leading=15.5, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=reg, fontSize=10.5, textColor=DARK,
            leading=15, spaceAfter=4, leftIndent=14, bulletIndent=4,
        ),
        "highlight": ParagraphStyle(
            "highlight", fontName=reg, fontSize=10, textColor=DARK,
            leading=14, spaceAfter=3, leftIndent=20,
            backColor=LIGHT, borderPadding=(3, 8, 3, 8),
        ),
        "question": ParagraphStyle(
            "question", fontName=bold, fontSize=10.5, textColor=PRIMARY,
            leading=14, spaceAfter=5, leftIndent=14,
        ),
        "source_title": ParagraphStyle(
            "source_title", fontName=bold, fontSize=10, textColor=DARK,
            leading=14, spaceAfter=1, leftIndent=14,
        ),
        "source_url": ParagraphStyle(
            "source_url", fontName=reg, fontSize=9, textColor=LINK_C,
            leading=12, spaceAfter=6, leftIndent=20,
        ),
        "term_key": ParagraphStyle(
            "term_key", fontName=bold, fontSize=9.5, textColor=WHITE,
        ),
        "term_val": ParagraphStyle(
            "term_val", fontName=reg, fontSize=9.5, textColor=DARK,
        ),
        "footer": ParagraphStyle(
            "footer", fontName=reg, fontSize=8, textColor=MUTED, alignment=1,
        ),
    }


# ── Bloklar ───────────────────────────────────────────────────────────────────

def _cover_page(elements: list, data: dict, st: dict) -> None:
    panel = Table(
        [
            [Paragraph(data.get("title", "Hujjat Tahlili"), st["cover_title"])],
            [Paragraph(data.get("topic", ""), st["cover_sub"])],
            [Paragraph(f"Tur: {data.get('document_type', '—')}", st["cover_sub"])],
        ],
        colWidths=[W - 4*cm],
    )
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 24),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 24),
        ("LEFTPADDING", (0, 0), (-1, -1), 24),
        ("RIGHTPADDING", (0, 0), (-1, -1), 24),
    ]))
    elements.extend([Spacer(1, 2.5*cm), panel, PageBreak()])


def _summary_block(elements: list, data: dict, st: dict) -> None:
    elements.append(Paragraph("UMUMIY XULOSA", st["section_heading"]))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(data.get("summary", "—"), st["body"]))
    elements.append(Spacer(1, 0.5*cm))


def _key_points(elements: list, data: dict, st: dict) -> None:
    pts = data.get("key_points", [])
    if not pts:
        return
    elements.append(Paragraph("ASOSIY NUQTALAR", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    for p in pts:
        elements.append(Paragraph(f"• {p}", st["bullet"]))
    elements.append(Spacer(1, 0.4*cm))


def _sections_block(elements: list, data: dict, st: dict) -> None:
    sections = data.get("sections", [])
    if not sections:
        return
    elements.append(Paragraph("BO'LIMLAR", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    for sec in sections:
        elements.append(Paragraph(sec.get("heading", ""), st["subheading"]))
        content = sec.get("content", "")
        if content:
            elements.append(Paragraph(content, st["body"]))
        for hl in sec.get("highlights", []):
            elements.append(Paragraph(f"→ {hl}", st["highlight"]))
        elements.append(Spacer(1, 0.3*cm))


def _terms_table(elements: list, data: dict, st: dict) -> None:
    terms = data.get("terms", [])
    if not terms:
        return
    elements.append(Paragraph("ATAMALAR LUGHATI", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    rows = [
        [Paragraph(t.get("term", ""), st["term_key"]),
         Paragraph(t.get("definition", ""), st["term_val"])]
        for t in terms
    ]
    tbl = Table(rows, colWidths=[5.5*cm, W - 4*cm - 5.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PRIMARY),
        ("BACKGROUND", (1, 0), (1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [LIGHT, WHITE]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D8E8")),
    ]))
    elements.extend([tbl, Spacer(1, 0.5*cm)])


def _figures_block(elements: list, data: dict, st: dict) -> None:
    figs = data.get("figures", [])
    if not figs:
        return
    elements.append(Paragraph("MUHIM RAQAMLAR VA FAKTLAR", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    row_data = [
        [Paragraph(f, st["body"]) for f in figs[i:i+2]]
        for i in range(0, len(figs), 2)
    ]
    if row_data:
        tbl = Table(row_data, colWidths=[(W-4*cm)/2, (W-4*cm)/2])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.extend([tbl, Spacer(1, 0.5*cm)])


def _conclusion_block(elements: list, data: dict, st: dict) -> None:
    c = data.get("conclusion", "")
    if not c:
        return
    elements.append(Paragraph("YAKUNIY XULOSA", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(c, st["body"]))
    elements.append(Spacer(1, 0.4*cm))


def _questions_block(elements: list, data: dict, st: dict) -> None:
    qs = data.get("questions", [])
    if not qs:
        return
    elements.append(Paragraph("NAZORAT SAVOLLARI", st["section_heading"]))
    elements.append(Spacer(1, 0.2*cm))
    for i, q in enumerate(qs, 1):
        elements.append(Paragraph(f"{i}. {q}", st["question"]))
    elements.append(Spacer(1, 0.4*cm))


def _sources_block(elements: list, data: dict, st: dict) -> None:
    """Foydalanilgan manbalar — xulosa va savollardan KEYIN."""
    sources = data.get("sources", [])
    if not sources:
        return
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph("FOYDALANILGAN MANBALAR", st["section_heading"]))
    elements.append(Spacer(1, 0.25*cm))
    for i, src in enumerate(sources, 1):
        title = src.get("title", "")
        url = src.get("url", "")
        desc = src.get("description", "")
        # Sarlavha qatori
        line = f"{i}. {title}"
        if desc:
            line += f" — {desc}"
        elements.append(Paragraph(line, st["source_title"]))
        # URL alohida qatorda
        if url:
            elements.append(Paragraph(url, st["source_url"]))
        else:
            elements.append(Spacer(1, 0.1*cm))
    elements.append(Spacer(1, 0.3*cm))


# ── Asosiy funksiya ───────────────────────────────────────────────────────────

def build_pdf(data: dict, out_path: Path) -> Path:
    """Tahlil natijasidan PDF yaratadi."""
    reg, bold = _register_fonts()
    st = _styles(reg, bold)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.2*cm, bottomMargin=2*cm,
        title=data.get("title", "Tahlil"),
    )

    elements: list = []
    _cover_page(elements, data, st)
    _summary_block(elements, data, st)
    _key_points(elements, data, st)
    _sections_block(elements, data, st)
    _terms_table(elements, data, st)
    _figures_block(elements, data, st)
    _conclusion_block(elements, data, st)
    _questions_block(elements, data, st)
    # Manbalar — eng oxirida
    _sources_block(elements, data, st)

    if data.get("ai_error"):
        elements.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
        elements.append(Paragraph(
            f"⚠ AI xatosi: {data['ai_error']}",
            st["footer"]
        ))

    doc.build(elements)
    return out_path
