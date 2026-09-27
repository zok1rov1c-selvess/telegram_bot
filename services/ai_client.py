"""AI qatlami — ko'p provayderli, avtomatik fallback zanjiri.

Zanjir tartibi (kalit bo'lsa ishlatiladi):
  1. Gemini  (Google AI Studio — bepul)
  2. Groq    (bepul, eng tez)
  3. OpenRouter (300+ model, bepul tier)
  4. DeepSeek   (arzon, kuchli tahlil)
  5. OpenAI     (to'lovli, zaxira)

Offline rejimga HECH QACHON tushmaydi — faqat barcha kalit yo'q bo'lsa.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

import config
from services import textutils as tu

log = logging.getLogger(__name__)

SYSTEM = (
    "Sen professional o'zbek tilidagi ta'lim yordamchisisan. "
    "Javoblaringni FAQAT o'zbek tilida (lotin yozuvida), aniq, ilmiy va "
    "tushunarli qilib yozasan. "
    "Faqat so'ralgan JSON formatda javob qaytarasan, hech qanday "
    "qo'shimcha matn yozmaysan."
)

BASE_GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# Gemini model fallback zanjiri
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
]


class AIError(Exception):
    pass


# ──────────────────────────────────────────────────── JSON utils

def _extract_json(raw: str) -> dict:
    """Matndan JSON chiqarish — bir necha usulda urinadi."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise AIError(f"JSON topilmadi. Javob boshi: {raw[:200]}")
    snippet = raw[start: end + 1]

    # 1. To'g'ridan parse
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        pass

    # 2. Trailing comma tuzat
    fixed = re.sub(r",\s*([}\]])", r"\1", snippet)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 3. O'zbek apostrofi muammosi — ' → ʼ
    def _fix_quotes(m: re.Match) -> str:
        return m.group(0).replace("\\'", "\u02bc").replace("'", "\u02bc")

    fixed2 = re.sub(r'"(?:[^"\\]|\\.)*"', _fix_quotes, fixed)
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass

    # 4. So'z ichidagi apostrof
    fixed3 = re.sub(r"(?<=[a-zA-ZʻʼА-Яа-яA-Za-z])'(?=[a-zA-ZʻʼА-Яа-яA-Za-z])",
                    "\u02bc", fixed)
    try:
        return json.loads(fixed3)
    except json.JSONDecodeError as e:
        raise AIError(f"JSON parse xatosi: {e}. Snippet: {snippet[:400]}") from e


def _safe_text(data: dict) -> str:
    """Gemini javobidan matnni xavfsiz chiqarish."""
    candidates = data.get("candidates", [])
    if not candidates:
        if "promptFeedback" in data:
            block = data["promptFeedback"].get("blockReason", "noma'lum")
            raise AIError(f"So'rov bloklandi: {block}")
        raise AIError(f"candidates bo'sh: {str(data)[:200]}")

    c = candidates[0]
    finish = c.get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "OTHER"):
        raise AIError(f"Gemini blokadi: finishReason={finish}")

    content = c.get("content", {})
    parts = content.get("parts", [])
    if parts:
        return "".join(p.get("text", "") for p in parts)
    if "text" in c:
        return c["text"]
    raise AIError(f"Javobdan matn topilmadi. Kandidat: {str(c)[:300]}")


# ──────────────────────────────────────────────────── Provider stats

@dataclass
class ProviderStat:
    name: str
    success: int = 0
    fail: int = 0
    last_error: str = ""
    cooldown_until: float = 0.0  # timestamp

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def set_cooldown(self, seconds: float) -> None:
        self.cooldown_until = time.time() + seconds
        log.info("Provider %s cooldown %.0fs", self.name, seconds)


# ──────────────────────────────────────────────────── AIClient

class AIClient:
    """Ko'p provayderli AI mijoz — avtomatik fallback."""

    def __init__(self) -> None:
        self._stats: dict[str, ProviderStat] = {}
        self._gemini_model: str | None = None  # ishlayotgan Gemini modeli

    @property
    def online(self) -> bool:
        return bool(config.available_providers())

    def _stat(self, name: str) -> ProviderStat:
        if name not in self._stats:
            self._stats[name] = ProviderStat(name)
        return self._stats[name]

    # ── Gemini ──────────────────────────────────────────────────
    async def _call_gemini(self, model: str, prompt: str, json_mode: bool) -> str:
        url = f"{BASE_GEMINI}/models/{model}:generateContent?key={config.GEMINI_API_KEY}"
        gen: dict = {"temperature": 0.4, "maxOutputTokens": 8192}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen,
        }
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as c:
            r = await c.post(url, json=payload)

        if r.status_code == 429:
            raise AIError(f"RATE_LIMIT gemini/{model}")
        if r.status_code == 503:
            raise AIError(f"UNAVAILABLE gemini/{model}")
        if r.status_code == 404:
            raise AIError(f"NOT_FOUND gemini/{model}")
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")[:200]
            except Exception:
                msg = r.text[:200]
            raise AIError(f"Gemini {r.status_code}/{model}: {msg}")
        return _safe_text(r.json())

    async def _gemini(self, prompt: str, json_mode: bool) -> str:
        """Gemini — fallback model zanjiri bilan."""
        models = []
        if self._gemini_model:
            models.append(self._gemini_model)
        if config.GEMINI_MODEL not in models:
            models.append(config.GEMINI_MODEL)
        for m in GEMINI_MODELS:
            if m not in models:
                models.append(m)

        last_err: Exception = AIError("Gemini modellari ishlamadi")
        for model in models:
            try:
                result = await self._call_gemini(model, prompt, json_mode)
                if self._gemini_model != model:
                    log.info("Gemini: ishlayotgan model = %s", model)
                    self._gemini_model = model
                return result
            except AIError as e:
                log.debug("Gemini model %s: %s", model, e)
                last_err = e
                if "503" in str(e) or "429" in str(e):
                    await asyncio.sleep(1.5)
        raise last_err

    # ── OpenAI-compatible (Groq, OpenRouter, DeepSeek, OpenAI) ──
    async def _call_openai_compat(
        self, base_url: str, api_key: str, model: str,
        prompt: str, json_mode: bool, provider_name: str
    ) -> str:
        payload: dict = {
            "model": model,
            "temperature": 0.4,
            "max_tokens": 8192,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in base_url:
            headers["HTTP-Referer"] = "https://t.me/zokirovicbbz3_bot"
            headers["X-Title"] = "EduBot"

        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as c:
            r = await c.post(
                f"{base_url}/chat/completions",
                json=payload, headers=headers
            )

        if r.status_code == 429:
            raise AIError(f"RATE_LIMIT {provider_name}")
        if r.status_code == 503 or r.status_code == 502:
            raise AIError(f"UNAVAILABLE {provider_name}")
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")[:200]
            except Exception:
                msg = r.text[:200]
            raise AIError(f"{provider_name} {r.status_code}: {msg}")

        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise AIError(f"{provider_name}: choices bo'sh — {str(data)[:200]}")
        content = choices[0].get("message", {}).get("content")
        if content is None:
            raise AIError(f"{provider_name}: content None — {str(choices[0])[:200]}")
        return content

    async def _groq_with_fallback(self, prompt: str, json_mode: bool) -> str:
        """Groq — fallback model zanjiri bilan."""
        models = [config.GROQ_MODEL] + [
            m for m in config.GROQ_FALLBACK_MODELS if m != config.GROQ_MODEL
        ]
        last_err: Exception = AIError("Groq modellari ishlamadi")
        for model in models:
            try:
                return await self._call_openai_compat(
                    config.GROQ_BASE_URL, config.GROQ_API_KEY,
                    model, prompt, json_mode, f"Groq/{model}"
                )
            except AIError as e:
                log.debug("Groq model %s: %s", model, e)
                last_err = e
                if "429" in str(e):
                    await asyncio.sleep(2)
        raise last_err

    async def _openrouter_with_fallback(self, prompt: str, json_mode: bool) -> str:
        """OpenRouter — fallback model zanjiri bilan."""
        models = [config.OPENROUTER_MODEL] + [
            m for m in config.OPENROUTER_FALLBACK_MODELS if m != config.OPENROUTER_MODEL
        ]
        last_err: Exception = AIError("OpenRouter modellari ishlamadi")
        for model in models:
            try:
                return await self._call_openai_compat(
                    config.OPENROUTER_BASE_URL, config.OPENROUTER_API_KEY,
                    model, prompt, json_mode, f"OpenRouter/{model}"
                )
            except AIError as e:
                log.debug("OpenRouter model %s: %s", model, e)
                last_err = e
                if "429" in str(e):
                    await asyncio.sleep(2)
        raise last_err

    # ── Asosiy ask ──────────────────────────────────────────────
    async def ask(self, prompt: str, json_mode: bool = True, retries: int = 2) -> str:
        """
        Barcha mavjud provayderlarni ketma-ket sinaydi.
        Offline rejimga HECH QACHON tushmaydi (faqat hamma kalit yo'q bo'lsa).
        """
        providers = config.available_providers()
        if not providers:
            raise AIError(
                "Hech qanday AI kaliti sozlanmagan. "
                ".env fayliga kamida bitta kalit qo'shing."
            )

        # Provider chaqiruv funksiyalari
        caller_map: dict[str, Callable] = {
            "gemini": lambda p, j: self._gemini(p, j),
            "groq": lambda p, j: self._groq_with_fallback(p, j),
            "openrouter": lambda p, j: self._openrouter_with_fallback(p, j),
            "deepseek": lambda p, j: self._call_openai_compat(
                config.DEEPSEEK_BASE_URL, config.DEEPSEEK_API_KEY,
                config.DEEPSEEK_MODEL, p, j, "DeepSeek"
            ),
            "openai": lambda p, j: self._call_openai_compat(
                config.OPENAI_BASE_URL, config.OPENAI_API_KEY,
                config.OPENAI_MODEL, p, j, "OpenAI"
            ),
        }

        last_err: Exception = AIError("Noma'lum xato")

        for attempt in range(retries + 1):
            for provider in providers:
                stat = self._stat(provider)
                if stat.in_cooldown():
                    log.debug("Provider %s cooldownda, o'tkazib yuborildi", provider)
                    continue

                caller = caller_map.get(provider)
                if not caller:
                    continue

                try:
                    result = await caller(prompt, json_mode)
                    stat.success += 1
                    log.info("AI [%s] muvaffaqiyatli", provider)
                    return result

                except AIError as e:
                    stat.fail += 1
                    stat.last_error = str(e)
                    last_err = e
                    log.warning("AI [%s] xato: %s", provider, e)

                    # Cooldown: rate limit yoki unavailable
                    err_str = str(e)
                    if "RATE_LIMIT" in err_str or "429" in err_str:
                        stat.set_cooldown(60)   # 1 daqiqa
                    elif "UNAVAILABLE" in err_str or "503" in err_str:
                        stat.set_cooldown(30)   # 30 soniya
                    # Keyingi provayderga o't

                except Exception as e:
                    stat.fail += 1
                    last_err = AIError(str(e))
                    log.warning("AI [%s] kutilmagan xato: %s", provider, e)

            # Barcha provayderlar ishlamadi — biroz kutib qayta urin
            if attempt < retries:
                wait = 5 + attempt * 5
                log.info("Barcha provayderlar ishlamadi, %ds kutilmoqda...", wait)
                await asyncio.sleep(wait)
                # Cooldown larni tozala (qayta urinish uchun)
                for stat in self._stats.values():
                    if stat.in_cooldown():
                        stat.cooldown_until = 0.0

        raise AIError(
            f"Barcha AI provayderlar ishlamadi. "
            f"Oxirgi xato: {last_err}"
        )

    async def ask_json(self, prompt: str) -> dict:
        return _extract_json(await self.ask(prompt, json_mode=True))

    def status_report(self) -> str:
        """Provayderlar holati haqida qisqa xabar."""
        providers = config.available_providers()
        if not providers:
            return "❌ Hech qanday AI kaliti yo'q"
        lines = []
        for p in providers:
            stat = self._stat(p)
            if stat.in_cooldown():
                remaining = int(stat.cooldown_until - time.time())
                lines.append(f"⏸ {p} (cooldown {remaining}s)")
            elif stat.fail > 0 and stat.success == 0:
                lines.append(f"⚠️ {p} (xato: {stat.last_error[:50]})")
            else:
                lines.append(f"✅ {p}")
        return "\n".join(lines)

    # ── Chunk map ───────────────────────────────────────────────
    async def _map_chunks(self, chunks: list[str]) -> list[str]:
        results = []
        for idx, ch in enumerate(chunks):
            prompt = (
                f"Quyidagi matn bo'lagidan ({idx + 1}-qism) eng muhim "
                "faktlarni 10-15 ta qisqa punkt qilib ajrat.\n"
                'JSON: {"points": ["..."]}\n\n'
                f'MATN:\n"""{ch[:config.AI_CHUNK_CHARS]}"""'
            )
            try:
                data = await self.ask_json(prompt)
                results.append("\n".join(f"- {p}" for p in data.get("points", [])))
            except Exception:
                results.append("\n".join(f"- {s}" for s in tu.summarize(ch, 8)))
            await asyncio.sleep(0.5)
        return results

    # ── /read tahlil ────────────────────────────────────────────
    async def analyze_document(self, text: str, filename: str) -> dict:
        if not self.online:
            return offline_analysis(text, filename)
        try:
            chunks = tu.chunk_text(text, config.AI_CHUNK_CHARS)
            if len(chunks) > 1:
                notes = await self._map_chunks(chunks[:6])
                source = "QISQARTIRILGAN KONSPEKT:\n" + "\n".join(notes)
            else:
                source = text

            prompt = f"""Quyidagi hujjatni chuqur tahlil qil.
Hozirgi yil 2025-2026 — eng yangi va ishonchli ma'lumotlardan foydalanib javob ber.

HUJJAT NOMI: {filename}

MATN:
\"\"\"{source[:config.AI_CHUNK_CHARS]}\"\"\"

Natijani FAQAT shu JSON sxemada qaytar:
{{
  "title": "hujjatning aniq sarlavhasi",
  "document_type": "hujjat turi",
  "topic": "asosiy mavzu 1 gapda",
  "summary": "10-15 gapdan iborat to'liq xulosa, zamonaviy bilimlarga asoslanib",
  "key_points": ["10-14 ta muhim fakt, to'liq gap"],
  "sections": [
    {{
      "heading": "bo'lim nomi",
      "content": "4-7 gapda mazmun, zamonaviy ma'lumotlar bilan",
      "highlights": ["3-5 ta muhim nuqta"]
    }}
  ],
  "terms": [{{"term": "atama", "definition": "to'liq ilmiy ta'rif"}}],
  "figures": ["muhim raqam va statistika"],
  "conclusion": "yakuniy xulosa 5-8 gap, kelajak istiqbollari",
  "questions": ["6 ta nazorat savoli"],
  "sources": [
    {{"title": "manba", "url": "https://...", "description": "tavsif"}}
  ]
}}
Kamida 6 ta section. sources da 4-6 ta ishonchli manba."""

            data = await self.ask_json(prompt)
            data.setdefault("title", tu.guess_title(text, filename))
            data.setdefault("sources", [])
            return data

        except AIError as exc:
            log.error("analyze_document AIError: %s", exc)
            res = offline_analysis(text, filename)
            res["ai_error"] = str(exc)[:300]
            return res
        except Exception as exc:
            log.exception("analyze_document kutilmagan xato")
            res = offline_analysis(text, filename)
            res["ai_error"] = str(exc)[:300]
            return res

    # ── /presentation ────────────────────────────────────────────
    async def presentation_outline(
        self, text: str, filename: str, research: list[dict], slides: int
    ) -> dict:
        if not self.online:
            return offline_outline(text, filename, research, slides)
        try:
            chunks = tu.chunk_text(text, config.AI_CHUNK_CHARS)
            if len(chunks) > 1:
                notes = await self._map_chunks(chunks[:5])
                source = "\n".join(notes)
            else:
                source = text

            source_list = []
            extra_parts = []
            for r in research[:6]:
                source_list.append({"title": r["title"], "url": r["url"]})
                extra_parts.append(f"[{r['title']}]\n{r['extract'][:1200]}")
            extra = "\n\n".join(extra_parts) or "(manba topilmadi)"

            content_slides = max(slides - 4, 12)
            prompt = f"""Sen tajribali metodist va taqdimot dizayneri sisan. Hozirgi yil 2025-2026.
Material asosida zamonaviy PowerPoint taqdimoti rejasini tuz.

MATERIAL ({filename}):
\"\"\"{source[:config.AI_CHUNK_CHARS]}\"\"\"

MANBALAR:
\"\"\"{extra[:5000]}\"\"\"

Talablar:
- Aynan {content_slides} ta mazmunli slayd.
- Har slaydda 4-6 ta bullet, 10-20 so'zli to'liq jumla.
- "notes" faqat ma'ruzachi uchun — slaydda ko'rinmaydi.
- Slaydlarda manba linki yozilmasin — faqat "sources" da.
- "image_query" ingliz tilida 3-5 so'z.
- 100% o'zbek tilida (lotin). Zamonaviy faktlar qo'sh.

FAQAT JSON qaytarish:
{{
  "title": "sarlavha",
  "subtitle": "tavsif",
  "topic_en": "inglizcha mavzu",
  "agenda": ["6-8 reja punkti"],
  "slides": [
    {{
      "title": "slayd sarlavhasi",
      "bullets": ["to'liq jumla", "..."],
      "notes": "ma'ruzachi izohi",
      "image_query": "english query",
      "layout": "bullets"
    }}
  ],
  "stats": [{{"value": "45%", "label": "tavsif"}}],
  "conclusion": ["5-6 xulosa punkti"],
  "questions": ["4 savol"],
  "sources": [
    {{"title": "manba", "url": "https://...", "description": "tavsif"}}
  ]
}}"""

            data = await self.ask_json(prompt)
            if not data.get("slides"):
                raise AIError("slides bo'sh qaytdi")

            if not data.get("sources"):
                data["sources"] = source_list
            else:
                existing = {s.get("url") for s in data["sources"]}
                for s in source_list:
                    if s.get("url") not in existing:
                        data["sources"].append(s)
            return data

        except AIError as exc:
            log.error("presentation_outline AIError: %s", exc)
            res = offline_outline(text, filename, research, slides)
            res["ai_error"] = str(exc)[:300]
            return res
        except Exception as exc:
            log.exception("presentation_outline kutilmagan xato")
            res = offline_outline(text, filename, research, slides)
            res["ai_error"] = str(exc)[:300]
            return res


# ──────────────────────────────────────────────────── OFFLINE (zaxira)

def offline_analysis(text: str, filename: str) -> dict:
    import re as _re
    title = tu.guess_title(text, filename)
    key   = tu.summarize(text, 12)
    blocks = [b for b in tu.chunk_text(text, 3500) if len(b.strip()) > 300][:6]
    sections = []
    for i, b in enumerate(blocks, 1):
        sents = tu.summarize(b, 5)
        sections.append({
            "heading":    tu.guess_title(b, f"{i}-bo'lim"),
            "content":    " ".join(sents[:4]),
            "highlights": sents[:4],
        })
    return {
        "title":         title,
        "document_type": "Hujjat",
        "topic":         tu.shorten(" ".join(tu.keywords(text, 8)), 120),
        "summary":       " ".join(key[:6]),
        "key_points":    key,
        "sections":      sections,
        "terms":         [{"term": k, "definition": "—"} for k in tu.keywords(text, 8)],
        "figures":       _re.findall(
            r"\b\d[\d\s.,]*\s?(?:%|foiz|yil|ming|mln|mlrd)\b", text
        )[:10],
        "conclusion":    " ".join(key[-4:]),
        "questions":     [],
        "sources":       [],
        "offline":       True,
    }


def offline_outline(text: str, filename: str, research: list[dict], slides: int) -> dict:
    title  = tu.guess_title(text, filename)
    blocks = [b for b in tu.chunk_text(text, 2200) if len(b.strip()) > 250]
    kws    = tu.keywords(text, 12)
    out_slides = []
    for i, b in enumerate(blocks[:max(slides - 4, 10)]):
        bullets = [tu.shorten(s, 160) for s in tu.summarize(b, 5)]
        if not bullets:
            continue
        out_slides.append({
            "title":       tu.shorten(tu.guess_title(b, f"{i + 1}-mavzu"), 70),
            "bullets":     bullets,
            "notes":       "",
            "image_query": kws[i % len(kws)] if kws else title,
            "layout":      "bullets",
        })
    sources = [
        {"title": r["title"], "url": r["url"], "description": ""}
        for r in research[:6]
    ]
    return {
        "title":    title,
        "subtitle": "O'quv materiali asosida taqdimot",
        "topic_en": title,
        "agenda":   [s["title"] for s in out_slides[:8]],
        "slides":   out_slides,
        "stats":    [],
        "conclusion": [tu.shorten(s, 150) for s in tu.summarize(text, 6)],
        "questions":  [],
        "sources":    sources,
        "offline":    True,
    }
