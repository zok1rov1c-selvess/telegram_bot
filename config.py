"""Bot konfiguratsiyasi — barcha sozlamalar."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Local Bot API Server (200MB+ fayl qabul qilish uchun)
# Bo'sh bo'lsa — standart Telegram API ishlatiladi (max 20MB)
# Railway deploy qilinganda avtomatik o'rnatiladi
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "").strip()

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL    = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_FALLBACK_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_FALLBACK_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "thinkingmachines/inkling:free",
    "poolside/laguna-s-2.1:free",
    "liquid/lfm-2.5-2.6b:free",
]

# ── DeepSeek ──────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL    = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ── Limitlar ──────────────────────────────────────────────────────────────────
MAX_FILE_MB    = int(os.getenv("MAX_FILE_MB", "300"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "300000"))
AI_CHUNK_CHARS = int(os.getenv("AI_CHUNK_CHARS", "20000"))
MIN_SLIDES     = int(os.getenv("MIN_SLIDES", "16"))
HTTP_TIMEOUT   = float(os.getenv("HTTP_TIMEOUT", "120"))

# ── Papkalar ──────────────────────────────────────────────────────────────────
WORK_DIR   = BASE_DIR / "workdir"
ASSETS_DIR = BASE_DIR / "assets"
WORK_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# ── Dizayn ────────────────────────────────────────────────────────────────────
THEME = {
    "dark":    "0F2B46",
    "primary": "1B5E9B",
    "accent":  "2E86DE",
    "light":   "EAF2FA",
    "text":    "1C2833",
    "muted":   "5D6D7E",
    "white":   "FFFFFF",
}


def available_providers() -> list[str]:
    """Sozlangan provayderlar ro'yxati."""
    providers = []
    if GEMINI_API_KEY:
        providers.append("gemini")
    if GROQ_API_KEY:
        providers.append("groq")
    if OPENROUTER_API_KEY:
        providers.append("openrouter")
    if DEEPSEEK_API_KEY:
        providers.append("deepseek")
    if OPENAI_API_KEY:
        providers.append("openai")
    return providers


def ai_provider() -> str:
    p = available_providers()
    return p[0] if p else "offline"
