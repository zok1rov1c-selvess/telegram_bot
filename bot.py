"""Asosiy Telegram bot — /read, /presentation, /status, /mystats."""
from __future__ import annotations

import asyncio
import logging
import time
import tempfile
import uuid
from pathlib import Path

from telegram import Document, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from services.ai_client import AIClient
from services.database import db
from services.extractor import extract_text, is_supported
from services.pdf_builder import build_pdf
from services.pptx_builder import build_pptx
from services.research import fetch_images, gather_research

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

ai = AIClient()
PENDING: dict[int, dict] = {}
PENDING_TIMEOUT = 300  # 5 daqiqa


# ── Yordamchi funksiyalar ──────────────────────────────────────────────────────
def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _download_file(document: Document, dest: Path) -> Path:
    """Faylni yuklab olish. Local API bo'lsa 200MB+ ham ishlaydi."""
    tg_file = await document.get_file()
    path = dest / f"{_uid()}_{document.file_name or 'file'}"
    await tg_file.download_to_drive(str(path))
    return path


async def _safe_reply(msg: Message, text: str, **kw) -> None:
    try:
        await msg.reply_text(text, parse_mode=ParseMode.HTML, **kw)
    except Exception:
        await msg.reply_text(text[:4000])


async def _progress(msg: Message, text: str) -> Message:
    return await msg.reply_text(f"⏳ {text}")


async def _edit(prog: Message, text: str) -> None:
    try:
        await prog.edit_text(f"⏳ {text}")
    except Exception:
        pass


def _user_info(update: Update) -> tuple[int, str | None, str]:
    u = update.effective_user
    return u.id, u.username, (u.full_name or u.first_name or "Foydalanuvchi")


# ── Buyruqlar ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid, uname, fname = _user_info(update)
    await db.upsert_user(uid, uname, fname)

    await update.message.reply_text(
        f"👋 <b>Salom, {fname}!</b>\n\n"
        "Men <b>AI o'quv yordamchisiman</b>.\n\n"
        "📄 <b>/read</b> — Faylni tahlil qilib <b>PDF</b> ko'rinishida qaytaraman\n"
        "📊 <b>/presentation</b> — Fayldan <b>PowerPoint</b> taqdimot yarataman\n"
        "📊 <b>/mystats</b> — Sizning statistikangiz\n"
        "📡 <b>/status</b> — AI holati\n"
        "ℹ️ <b>/help</b> — Yordam\n\n"
        "<i>Buyruqni yuboring, keyin faylni yuklang.</i>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    providers = config.available_providers()
    ai_info = ("✅ " + ", ".join(p.capitalize() for p in providers)
               if providers else "⚠️ Kalit yo'q")
    await update.message.reply_text(
        f"<b>YORDAM</b>\n\n"
        f"AI: {ai_info}\n\n"
        f"<b>Buyruqlar:</b>\n"
        f"📄 /read — PDF tahlil\n"
        f"📊 /presentation — PowerPoint\n"
        f"📈 /mystats — Statistika\n"
        f"📡 /status — AI holati\n\n"
        f"<b>Fayl turlari:</b> PDF, DOCX, PPTX, TXT, XLSX, CSV, HTML, JSON\n"
        f"<b>Maksimal fayl:</b> {config.MAX_FILE_MB} MB",
        parse_mode=ParseMode.HTML,
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    providers = config.available_providers()
    lines = ["<b>🤖 AI PROVAYDERLAR</b>\n"]
    icons = {
        "gemini": "🤖 Gemini",
        "groq": "⚡ Groq",
        "openrouter": "🌐 OpenRouter",
        "deepseek": "🔍 DeepSeek",
        "openai": "💎 OpenAI",
    }
    for p in ["gemini", "groq", "openrouter", "deepseek", "openai"]:
        name = icons.get(p, p)
        if p in providers:
            stat = ai._stat(p)
            if stat.in_cooldown():
                rem = int(stat.cooldown_until - time.time())
                lines.append(f"⏸ {name} — cooldown {rem}s")
            elif stat.fail > 0 and stat.success == 0:
                lines.append(f"⚠️ {name} — xato")
            else:
                lines.append(f"✅ {name}")
        else:
            lines.append(f"○ {name} — kalit yo'q")

    # Database holati
    lines.append("")
    if db.enabled:
        stats = await db.get_global_stats()
        lines.append(
            f"🗄 <b>Database:</b> ✅ ulangan\n"
            f"   👥 Foydalanuvchilar: {stats.get('total_users', 0)}\n"
            f"   📄 Jami read: {stats.get('total_reads', 0)}\n"
            f"   📊 Jami taqdimot: {stats.get('total_pptx', 0)}"
        )
    else:
        lines.append("🗄 <b>Database:</b> ○ ulanmagan")

    lines.append(f"\n<i>Zanjir: {' → '.join(providers)}</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_mystats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid, uname, fname = _user_info(update)
    if not db.enabled:
        await update.message.reply_text(
            "📊 Statistika hozircha mavjud emas (database ulanmagan)."
        )
        return
    stats = await db.get_user_stats(uid)
    if not stats:
        await update.message.reply_text("Siz hali hech narsa qilmagansiz. /read yoki /presentation bilan boshlang.")
        return
    await update.message.reply_text(
        f"<b>📈 SIZNING STATISTIKANGIZ</b>\n\n"
        f"👤 {fname}\n"
        f"📄 PDF tahlillar: <b>{stats.get('read_count', 0)}</b>\n"
        f"📊 Taqdimotlar: <b>{stats.get('pptx_count', 0)}</b>\n"
        f"🕐 Birinchi marta: {str(stats.get('first_seen',''))[:10]}\n"
        f"🕐 Oxirgi marta: {str(stats.get('last_seen',''))[:10]}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_read(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid, uname, fname = _user_info(update)
    await db.upsert_user(uid, uname, fname)
    PENDING[uid] = {"cmd": "read", "expires": time.time() + PENDING_TIMEOUT}
    await update.message.reply_text(
        "📎 Faylni yuboring — <b>PDF tahlil hisobotini</b> tayyorlayman.\n"
        "<i>(5 daqiqa ichida)</i>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_presentation(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid, uname, fname = _user_info(update)
    await db.upsert_user(uid, uname, fname)
    PENDING[uid] = {"cmd": "presentation", "expires": time.time() + PENDING_TIMEOUT}
    await update.message.reply_text(
        f"📎 O'quv materialingizni yuboring — "
        f"<b>{config.MIN_SLIDES}+ slaydli PowerPoint</b> taqdimot yarataman.\n"
        "<i>(5 daqiqa ichida)</i>",
        parse_mode=ParseMode.HTML,
    )


# ── Fayl handler ──────────────────────────────────────────────────────────────
async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    uid, uname, fname = _user_info(update)
    doc = msg.document

    pending = PENDING.pop(uid, None)
    if not pending or time.time() > pending["expires"]:
        await _safe_reply(
            msg,
            "ℹ️ Avval buyruqni yuboring:\n"
            "📄 /read — PDF tahlil\n"
            "📊 /presentation — PowerPoint",
        )
        return

    cmd = pending["cmd"]
    filename = doc.file_name or "fayl"

    if not is_supported(filename):
        await _safe_reply(msg, f"❌ <b>{filename}</b> — bu format qo'llanmaydi.")
        return

    mb = (doc.file_size or 0) / 1_048_576
    if mb > config.MAX_FILE_MB:
        await _safe_reply(msg, f"❌ Fayl {mb:.1f} MB — maksimal {config.MAX_FILE_MB} MB.")
        return

    # Telegram standart API: 20 MB limit
    # Local API ishlatilsa: 200 MB+ qabul qiladi
    TELEGRAM_CLOUD_LIMIT = 20
    if mb > TELEGRAM_CLOUD_LIMIT and not config.LOCAL_API_URL:
        await _safe_reply(
            msg,
            f"❌ <b>Fayl hajmi {mb:.1f} MB</b>\n\n"
            f"Telegram standart API faqat <b>20 MB</b> gacha qabul qiladi.\n\n"
            f"<b>Yechim:</b>\n"
            f"• Faylni kichikroq qismlarga bo'lib yuboring\n"
            f"• Yoki matnni nusxa olib, .txt fayl sifatida yuboring\n\n"
            f"<i>200 MB gacha qabul qilish uchun server kerak (Railway deploy)</i>"
        )
        return

    prog = await _progress(msg, "Fayl yuklanmoqda...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        file_path = await _download_file(doc, tmp_path)
        await _edit(prog, "Matn ajratilmoqda...")

        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, extract_text, file_path
            )
        except Exception as exc:
            await prog.edit_text(f"❌ Faylni o'qib bo'lmadi: {exc}")
            await db.log_action(uid, cmd, filename, doc.file_size or 0, "", False)
            return

        if len(text.strip()) < 80:
            await prog.edit_text("❌ Fayl bo'sh yoki matn topilmadi.")
            return

        if cmd == "read":
            await _process_read(msg, prog, text, filename, tmp_path, uid, doc.file_size or 0)
        else:
            await _process_presentation(msg, prog, text, filename, tmp_path, uid, doc.file_size or 0)


# ── /read ─────────────────────────────────────────────────────────────────────
async def _process_read(
    msg: Message, prog: Message, text: str,
    filename: str, work_dir: Path, uid: int, file_size: int
) -> None:
    try:
        await _edit(prog, "AI tahlil qilmoqda...")
        data = await ai.analyze_document(text, filename)
        provider = ai._working_model or config.ai_provider()

        await _edit(prog, "PDF yaratilmoqda...")
        out = work_dir / f"tahlil_{_uid()}.pdf"
        await asyncio.get_event_loop().run_in_executor(None, build_pdf, data, out)

        await db.inc_count(uid, "read")
        await db.log_action(uid, "read", filename, file_size, provider, True)

        await prog.delete()
        caption = (
            f"📄 <b>{data.get('title', filename)}</b>\n\n"
            f"🏷 Tur: {data.get('document_type', '—')}\n"
            f"📌 {data.get('topic', '—')[:150]}\n\n"
            f"<i>Bo'limlar: {len(data.get('sections', []))} • "
            f"Atamalar: {len(data.get('terms', []))} • "
            f"Manbalar: {len(data.get('sources', []))}</i>"
        )
        await msg.reply_document(
            document=open(out, "rb"),
            filename=f"tahlil_{filename.rsplit('.', 1)[0]}.pdf",
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        log.exception("/read xato")
        await db.log_action(uid, "read", filename, file_size, "", False)
        try:
            await prog.edit_text(f"❌ Xato: {exc}")
        except Exception:
            await msg.reply_text(f"❌ Xato: {exc}")


# ── /presentation ─────────────────────────────────────────────────────────────
async def _process_presentation(
    msg: Message, prog: Message, text: str,
    filename: str, work_dir: Path, uid: int, file_size: int
) -> None:
    try:
        from services.textutils import keywords, guess_title

        await _edit(prog, "Internet manbalardan ma'lumot yig'ilmoqda...")
        topic = guess_title(text, filename)
        queries = [topic] + keywords(text, 6)[:3]
        research = await gather_research(queries, max_articles=6)

        await _edit(prog, "AI taqdimot rejasini tuzmoqda...")
        data = await ai.presentation_outline(text, filename, research, config.MIN_SLIDES)
        provider = ai._working_model or config.ai_provider()

        img_queries = list({
            s.get("image_query", "")
            for s in data.get("slides", [])
            if s.get("image_query")
        })[:20]

        images: dict[str, str] = {}
        if img_queries:
            await _edit(prog, f"Rasmlar yuklanmoqda ({len(img_queries)} ta)...")
            try:
                images = await fetch_images(img_queries, work_dir / "images", per_query=1)
            except Exception as exc:
                log.warning("Rasmlar yuklanmadi: %s", exc)

        await _edit(prog, "PowerPoint fayli yaratilmoqda...")
        out = work_dir / f"taqdimot_{_uid()}.pptx"
        await asyncio.get_event_loop().run_in_executor(None, build_pptx, data, images, out)

        await db.inc_count(uid, "presentation")
        await db.log_action(uid, "presentation", filename, file_size, provider, True)

        await prog.delete()
        n_slides = 2 + bool(data.get("stats")) + len(data.get("slides", [])) + 4
        caption = (
            f"📊 <b>{data.get('title', filename)}</b>\n\n"
            f"🗂 Slaydlar: <b>{n_slides}</b>\n"
            f"🖼 Rasmlar: <b>{len(images)}</b>\n"
            f"📚 Manbalar: <b>{len(research)}</b>\n\n"
            f"<i>{data.get('subtitle', '')}</i>"
        )
        await msg.reply_document(
            document=open(out, "rb"),
            filename=f"taqdimot_{filename.rsplit('.', 1)[0]}.pptx",
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        log.exception("/presentation xato")
        await db.log_action(uid, "presentation", filename, file_size, "", False)
        try:
            await prog.edit_text(f"❌ Xato: {exc}")
        except Exception:
            await msg.reply_text(f"❌ Xato: {exc}")


# ── Rasm handler ──────────────────────────────────────────────────────────────
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    uid, uname, fname = _user_info(update)
    pending = PENDING.pop(uid, None)
    if not pending or time.time() > pending["expires"]:
        await _safe_reply(msg, "ℹ️ Rasm uchun avval /read buyrug'ini yuboring.")
        return

    prog = await _progress(msg, "Rasm yuklanmoqda...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        photo = msg.photo[-1]
        tg_file = await photo.get_file()
        img_path = tmp_path / f"{_uid()}.jpg"
        await tg_file.download_to_drive(str(img_path))

        await _edit(prog, "Matn ajratilmoqda (OCR)...")
        from services.extractor import _from_image
        text = await asyncio.get_event_loop().run_in_executor(None, _from_image, img_path)

        if len(text.strip()) < 30:
            await prog.edit_text("❌ Rasmdan matn topilmadi.")
            return

        await _process_read(msg, prog, text, "rasm.jpg", tmp_path, uid, 0)


# ── Main ──────────────────────────────────────────────────────────────────────
async def post_init(app: Application) -> None:
    """Bot ishga tushganda database ga ulanish."""
    await db.connect()
    log.info("Database: %s", "ulangan" if db.enabled else "o'chirilgan")


def main() -> None:
    token = config.BOT_TOKEN
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida topilmadi!")

    providers = config.available_providers()
    log.info("Bot ishga tushmoqda | AI: %s", providers)
    log.info("Fayl limiti: %d MB | Local API: %s",
             config.MAX_FILE_MB,
             "HA" if config.LOCAL_API_URL else "YOQ (max 20MB)")

    builder = Application.builder().token(token).post_init(post_init)

    # Local Bot API Server ulangan bo'lsa — 200MB+ fayl qabul qiladi
    if config.LOCAL_API_URL:
        builder = builder.base_url(config.LOCAL_API_URL)
        log.info("Local API Server ishlatilmoqda: %s", config.LOCAL_API_URL)

    app = (
        builder
        .read_timeout(300)
        .write_timeout(300)
        .connect_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("mystats", cmd_mystats))
    app.add_handler(CommandHandler("read", cmd_read))
    app.add_handler(CommandHandler("presentation", cmd_presentation))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    log.info("Polling boshlandi...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
