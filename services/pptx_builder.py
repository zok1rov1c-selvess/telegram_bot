"""AI taqdimot rejasidan chiroyli PPTX fayl yaratish.

Xususiyatlar:
- Har bir slayd turi uchun turli background ranglar/gradient
- Varoqlarda manba linki yo'q — faqat oxirida bitta "Foydalanilgan manbalar" slaydida
- Zamonaviy, professional dizayn
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm, Pt

log = logging.getLogger(__name__)

# ── Rang palitralari ──────────────────────────────────────────────────────────
# Har bir mavzu uchun (bg, header, accent, text, bullet_dot) to'plamlari
PALETTES = [
    # 0 - Ko'k (asosiy)
    ("0D2137", "1B5E9B", "2E86DE", "EAF2FA", "FFFFFF", "C8E0F8"),
    # 1 - Qoʻngʻir/Oltin
    ("1C1008", "7B4F12", "E8A020", "FFF8EC", "FFFFFF", "F5D080"),
    # 2 - Yashil
    ("0A1F0E", "1A5C2A", "2DBD52", "EAFAF1", "FFFFFF", "A9DFBF"),
    # 3 - Binafsha
    ("180D2E", "5B2D8E", "9B59B6", "F5EEF8", "FFFFFF", "D7BDE2"),
    # 4 - Qizil/Toʻq
    ("1A0808", "7B1010", "E82020", "FDF2F2", "FFFFFF", "F5A9A9"),
    # 5 - Dengiz
    ("071520", "0E5272", "17A2B8", "E8F8FC", "FFFFFF", "A9E4EF"),
    # 6 - Qoʻngʻir-kulrang
    ("141414", "374151", "607D8B", "ECEFF1", "FFFFFF", "B0BEC5"),
    # 7 - Toshko'mir
    ("0A0A0A", "1F1F2E", "5C6BC0", "E8EAF6", "FFFFFF", "9FA8DA"),
]

SLIDE_W = Cm(33.87)
SLIDE_H = Cm(19.05)


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str)


def _solid_bg(slide, hex_color: str) -> None:
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(hex_color)


def _gradient_bg(slide, hex1: str, hex2: str) -> None:
    """Oddiy diagonal gradient effect (2 ta rect bilan)."""
    _solid_bg(slide, hex1)
    shape = slide.shapes.add_shape(1, Cm(0), Cm(0), SLIDE_W, SLIDE_H)
    shape.line.fill.background()
    fill = shape.fill
    fill.gradient()
    fill.gradient_angle = 135
    stops = fill.gradient_stops
    stops[0].position = 0.0
    stops[0].color.rgb = _rgb(hex1)
    stops[1].position = 1.0
    stops[1].color.rgb = _rgb(hex2)


def _rect(slide, left, top, width, height, hex_color: str) -> None:
    s = slide.shapes.add_shape(1, left, top, width, height)
    s.line.fill.background()
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(hex_color)


def _textbox(slide, text: str, left, top, width, height,
             hex_color: str, size: int, bold: bool = False,
             align=PP_ALIGN.LEFT, wrap: bool = True) -> None:
    txb = slide.shapes.add_textbox(left, top, width, height)
    txb.word_wrap = wrap
    tf = txb.text_frame
    tf.word_wrap = wrap
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    run.font.color.rgb = _rgb(hex_color)
    run.font.size = Pt(size)
    run.font.bold = bold


def _add_image_safe(slide, path: str, left, top, width, height) -> bool:
    try:
        from PIL import Image as PILImage
        import io
        with PILImage.open(path) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            buf.seek(0)
        slide.shapes.add_picture(buf, left, top, width, height)
        return True
    except Exception as exc:
        log.debug("Rasm qo'shilmadi (%s): %s", path, exc)
        return False


# ── Slayd turlari ─────────────────────────────────────────────────────────────

def _slide_cover(prs: Presentation, data: dict, pal: tuple) -> None:
    """Muqova — to'q gradient, katta sarlavha."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, bg)
    # pastki dekorativ chiziq
    _rect(slide, Cm(0), SLIDE_H - Cm(0.6), SLIDE_W, Cm(0.6), acc)
    # yuqori ingichka chiziq
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(0.25), acc)
    # sarlavha
    _textbox(slide, data.get("title", "Taqdimot"),
             Cm(2), Cm(4), Cm(29), Cm(6),
             wh, 38, bold=True, align=PP_ALIGN.CENTER)
    # tavsif
    sub = data.get("subtitle", "")
    if sub:
        _textbox(slide, sub, Cm(3), Cm(11), Cm(27), Cm(2.5),
                 lt, 18, align=PP_ALIGN.CENTER)
    # pastki chap yil/brend
    _textbox(slide, "2025–2026", Cm(1.5), SLIDE_H - Cm(1.6), Cm(8), Cm(1.2),
             _rgb_muted(acc), 11)


def _slide_agenda(prs: Presentation, data: dict, pal: tuple) -> None:
    """Reja slayd — yorqin header, raqamli ro'yxat."""
    agenda = data.get("agenda", [])
    if not agenda:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, lt)
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(3), hdr)
    _textbox(slide, "REJA", Cm(1.5), Cm(0.6), Cm(30), Cm(2),
             wh, 26, bold=True, align=PP_ALIGN.CENTER)
    y = Cm(3.5)
    for i, item in enumerate(agenda[:10], 1):
        # raqam circle
        _rect(slide, Cm(1.8), y + Cm(0.15), Cm(0.75), Cm(0.75), hdr)
        _textbox(slide, str(i), Cm(1.85), y + Cm(0.08), Cm(0.65), Cm(0.85),
                 wh, 11, bold=True, align=PP_ALIGN.CENTER)
        _textbox(slide, item, Cm(2.9), y, Cm(27), Cm(1.1), _rgb_txt(bg), 13)
        y += Cm(1.35)


def _slide_stats(prs: Presentation, data: dict, pal: tuple) -> None:
    """Statistika slayd — kartochkalar."""
    stats = data.get("stats", [])
    if not stats:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, bg)
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(2.8), hdr)
    _textbox(slide, "STATISTIKA VA RAQAMLAR", Cm(1), Cm(0.5), Cm(31), Cm(2),
             wh, 22, bold=True, align=PP_ALIGN.CENTER)
    cols = min(len(stats), 4)
    box_w = Cm(30.0 / cols)
    for i, stat in enumerate(stats[:4]):
        x = Cm(1.5) + i * box_w
        _rect(slide, x + Cm(0.3), Cm(4.2), box_w - Cm(0.6), Cm(7), acc)
        _textbox(slide, stat.get("value", ""), x + Cm(0.4), Cm(4.8),
                 box_w - Cm(0.8), Cm(3.2), wh, 36, bold=True, align=PP_ALIGN.CENTER)
        _textbox(slide, stat.get("label", ""), x + Cm(0.4), Cm(8.2),
                 box_w - Cm(0.8), Cm(2.5), lt, 12, align=PP_ALIGN.CENTER)


def _slide_content(prs: Presentation, sld: dict, images: dict,
                   pal: tuple, idx: int) -> None:
    """Asosiy kontent slayd — har xil background."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal

    # Juft/toq indeksga qarab fon
    if idx % 3 == 0:
        _solid_bg(slide, bg)
        title_c, body_c, bullet_c = wh, lt, acc
        header_bg = hdr
    elif idx % 3 == 1:
        _solid_bg(slide, lt)
        title_c, body_c, bullet_c = bg, _rgb_txt(lt), hdr
        header_bg = hdr
    else:
        _solid_bg(slide, "FFFFFF")
        title_c, body_c, bullet_c = bg, "374151", acc
        header_bg = hdr

    # Header panel
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(2.6), header_bg)
    _textbox(slide, sld.get("title", ""), Cm(0.8), Cm(0.3),
             Cm(31), Cm(2.1), wh, 18, bold=True)

    has_image = sld.get("image_query", "") in images
    text_w = Cm(19.5) if has_image else Cm(31)

    if has_image:
        img_path = images[sld["image_query"]]
        _add_image_safe(slide, img_path, Cm(20.2), Cm(2.9), Cm(13), Cm(10.5))

    bullets = sld.get("bullets", [])
    y = Cm(3.0)
    for b in bullets[:7]:
        # bullet nuqtasi
        _rect(slide, Cm(1.1), y + Cm(0.3), Cm(0.32), Cm(0.32), bullet_c)
        _textbox(slide, b, Cm(1.7), y, text_w - Cm(1.5), Cm(1.5), body_c, 12)
        y += Cm(1.6)

    notes = sld.get("notes", "")
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def _slide_two_column(prs: Presentation, sld: dict, pal: tuple, idx: int) -> None:
    """Ikki ustunli slayd."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal

    if idx % 2 == 0:
        _solid_bg(slide, bg)
        body_c, bullet_c = lt, acc
    else:
        _solid_bg(slide, lt)
        body_c, bullet_c = bg, hdr

    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(2.6), hdr)
    _textbox(slide, sld.get("title", ""), Cm(0.8), Cm(0.3),
             Cm(31), Cm(2.1), wh, 18, bold=True)
    # ajratgich chiziq
    _rect(slide, SLIDE_W / 2 - Cm(0.06), Cm(2.8), Cm(0.12), SLIDE_H - Cm(3.5), acc)

    bullets = sld.get("bullets", [])
    left_b = bullets[:4]
    right_b = bullets[4:8]
    y = Cm(3.1)
    for b in left_b:
        _rect(slide, Cm(0.9), y + Cm(0.28), Cm(0.28), Cm(0.28), bullet_c)
        _textbox(slide, b, Cm(1.4), y, Cm(14.5), Cm(1.45), body_c, 11)
        y += Cm(1.55)
    y = Cm(3.1)
    for b in right_b:
        _rect(slide, Cm(17.4), y + Cm(0.28), Cm(0.28), Cm(0.28), bullet_c)
        _textbox(slide, b, Cm(17.9), y, Cm(14.5), Cm(1.45), body_c, 11)
        y += Cm(1.55)

    if sld.get("notes"):
        slide.notes_slide.notes_text_frame.text = sld["notes"]


def _slide_quote(prs: Presentation, sld: dict, pal: tuple) -> None:
    """Iqtibos / ajoyib fakt slayd."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, bg)
    # katta qo'shtirnoq belgisi
    _textbox(slide, "\u201c", Cm(1.5), Cm(1.5), Cm(6), Cm(5), acc, 90, bold=True)
    bullets = sld.get("bullets", [])
    quote = bullets[0] if bullets else ""
    _textbox(slide, quote, Cm(4), Cm(4.5), Cm(25), Cm(6),
             wh, 20, align=PP_ALIGN.CENTER)
    _rect(slide, Cm(10), Cm(11.5), Cm(13), Cm(0.1), acc)
    _textbox(slide, sld.get("title", ""), Cm(3), Cm(12), Cm(27), Cm(2),
             _rgb_muted(acc), 13, align=PP_ALIGN.CENTER)

    if sld.get("notes"):
        slide.notes_slide.notes_text_frame.text = sld["notes"]


def _slide_conclusion(prs: Presentation, data: dict, pal: tuple) -> None:
    """Xulosa slayd."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, hdr)
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(3.2), bg)
    _textbox(slide, "XULOSA", Cm(1.5), Cm(0.6), Cm(30), Cm(2.2),
             wh, 28, bold=True, align=PP_ALIGN.CENTER)
    _rect(slide, Cm(3), Cm(3.3), Cm(27), Cm(0.1), acc)
    pts = data.get("conclusion", [])
    if isinstance(pts, str):
        pts = [pts]
    y = Cm(3.7)
    for p in pts[:7]:
        _rect(slide, Cm(2.8), y + Cm(0.32), Cm(0.35), Cm(0.35), wh)
        _textbox(slide, p, Cm(3.5), y, Cm(27), Cm(1.5), wh, 13)
        y += Cm(1.65)


def _slide_questions(prs: Presentation, data: dict, pal: tuple) -> None:
    """Savol-javob slayd."""
    qs = data.get("questions", [])
    if not qs:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, lt)
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(3), acc)
    _textbox(slide, "SAVOL VA MUHOKAMA", Cm(1.5), Cm(0.6), Cm(30), Cm(2),
             wh, 24, bold=True, align=PP_ALIGN.CENTER)
    y = Cm(3.5)
    for i, q in enumerate(qs[:6], 1):
        _rect(slide, Cm(1.5), y + Cm(0.2), Cm(0.5), Cm(0.5), acc)
        _textbox(slide, str(i), Cm(1.57), y + Cm(0.13), Cm(0.38), Cm(0.5),
                 wh, 10, bold=True, align=PP_ALIGN.CENTER)
        _textbox(slide, q, Cm(2.3), y, Cm(29), Cm(1.5), bg, 13)
        y += Cm(1.65)


def _slide_sources(prs: Presentation, data: dict, pal: tuple) -> None:
    """Foydalanilgan manbalar — FAQAT shu yerda, boshqa slaydlarda yo'q."""
    sources = data.get("sources", [])
    if not sources:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, "FAFAFA")
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(2.8), bg)
    _textbox(slide, "FOYDALANILGAN MANBALAR", Cm(1.5), Cm(0.55), Cm(30), Cm(2),
             wh, 22, bold=True, align=PP_ALIGN.CENTER)
    y = Cm(3.2)
    for i, src in enumerate(sources[:12], 1):
        title = src.get("title", "")
        url = src.get("url", "")
        desc = src.get("description", "")
        line = f"{i}. {title}"
        if desc:
            line += f" — {desc}"
        _textbox(slide, line, Cm(1.5), y, Cm(29), Cm(0.9), bg, 11, bold=False)
        if url:
            _textbox(slide, url, Cm(2.2), y + Cm(0.85), Cm(28), Cm(0.75), acc, 9)
            y += Cm(1.75)
        else:
            y += Cm(1.1)


def _slide_thankyou(prs: Presentation, pal: tuple) -> None:
    """Rahmat slayd."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg, hdr, acc, lt, wh, dot = pal
    _solid_bg(slide, bg)
    _rect(slide, Cm(0), SLIDE_H - Cm(0.5), SLIDE_W, Cm(0.5), acc)
    _rect(slide, Cm(0), Cm(0), SLIDE_W, Cm(0.25), acc)
    _textbox(slide, "E'TIBORINGIZ UCHUN", Cm(2), Cm(5.5), Cm(29), Cm(2.5),
             lt, 30, bold=False, align=PP_ALIGN.CENTER)
    _textbox(slide, "RAHMAT!", Cm(2), Cm(8.2), Cm(29), Cm(4),
             wh, 52, bold=True, align=PP_ALIGN.CENTER)


# ── Yordamchi funksiyalar ─────────────────────────────────────────────────────

def _rgb_txt(bg_hex: str) -> str:
    """Fon rangiga qarab matn rangi (qora yoki oq)."""
    r = int(bg_hex[:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "1C2833" if luminance > 0.5 else "FFFFFF"


def _rgb_muted(hex_color: str) -> str:
    """Rangni biroz ochiqroq ko'rinishda qaytaradi."""
    r = min(255, int(hex_color[:2], 16) + 60)
    g = min(255, int(hex_color[2:4], 16) + 60)
    b = min(255, int(hex_color[4:], 16) + 60)
    return f"{r:02X}{g:02X}{b:02X}"


def _pick_palette(idx: int) -> tuple:
    """Slayd indeksiga qarab palitra tanlaydi — ketma-ket aylanadi."""
    return PALETTES[idx % len(PALETTES)]


# ── Asosiy funksiya ───────────────────────────────────────────────────────────

def build_pptx(data: dict, images: dict, out_path: Path) -> Path:
    """
    data   — AIClient.presentation_outline() dan kelgan dict
    images — {image_query: local_filepath}
    """
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    # Muqova uchun birinchi palitra
    cover_pal = PALETTES[0]
    _slide_cover(prs, data, cover_pal)

    # Reja — ikkinchi palitra
    agenda_pal = PALETTES[2]
    _slide_agenda(prs, data, agenda_pal)

    # Statistika — uchinchi palitra (agar bor bo'lsa)
    if data.get("stats"):
        _slide_stats(prs, data, PALETTES[4])

    # Asosiy slaydlar — har biri uchun navbatma-navbat palitra
    content_palette_idx = 0
    for i, sld in enumerate(data.get("slides", [])):
        pal = _pick_palette(content_palette_idx + 1)  # 0 muqova uchun band
        layout = sld.get("layout", "bullets")
        if layout == "two_column":
            _slide_two_column(prs, sld, pal, i)
        elif layout == "quote":
            _slide_quote(prs, sld, pal)
        else:
            _slide_content(prs, sld, images, pal, i)
        content_palette_idx += 1

    # Xulosa
    _slide_conclusion(prs, data, PALETTES[1])

    # Savol-javob
    _slide_questions(prs, data, PALETTES[3])

    # Foydalanilgan manbalar — OXIRIDA bitta joyda
    _slide_sources(prs, data, PALETTES[6])

    # Rahmat
    _slide_thankyou(prs, PALETTES[7])

    prs.save(str(out_path))
    return out_path
