"""Matn bilan ishlovchi yordamchi funksiyalar (offline tahlil uchun ham)."""
from __future__ import annotations

import re
from collections import Counter

STOPWORDS = set("""
va ham bu shu u ular biz siz men sen uchun bilan lekin ammo yoki agar chunki
bo'ladi bolishi bo'lgan bo'lib edi emas kerak har bir barcha ba'zi keyin oldin
qanday qanaqa nima kim qachon qayerda yana esa deb degan kabi singari orqali
the a an and or but for with from this that these those is are was were be been
being of to in on at as by it its their his her our your my not no yes can will
would should could have has had do does did если это как что для при или так
также но его их она они это был была были есть нет
""".split())

SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
WORD_RE = re.compile(r"[\w'’ʻ`-]{3,}", re.UNICODE)


def sentences(text: str) -> list[str]:
    out = []
    for s in SENT_SPLIT.split(text):
        s = s.strip(" -–—•\t")
        if len(s) >= 25:
            out.append(re.sub(r"\s+", " ", s))
    return out


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOPWORDS]


def keywords(text: str, limit: int = 15) -> list[str]:
    return [w for w, _ in Counter(words(text)).most_common(limit)]


def summarize(text: str, max_sentences: int = 8) -> list[str]:
    """Oddiy ekstraktiv xulosa (AI kalitisiz ishlash uchun)."""
    sents = sentences(text)
    if not sents:
        return []
    freq = Counter(words(text))
    if not freq:
        return sents[:max_sentences]
    top = freq.most_common(1)[0][1] or 1
    scored = []
    for idx, s in enumerate(sents):
        sw = words(s)
        if not sw:
            continue
        score = sum(freq[w] / top for w in sw) / (len(sw) ** 0.6)
        if idx < len(sents) * 0.2:
            score *= 1.15  # boshidagi jumlalar odatda muhimroq
        scored.append((score, idx, s))
    scored.sort(reverse=True)
    chosen = sorted(scored[:max_sentences], key=lambda x: x[1])
    return [s for _, _, s in chosen]


def chunk_text(text: str, size: int) -> list[str]:
    """Matnni abzatslar chegarasi bo'yicha bo'laklarga ajratadi."""
    if len(text) <= size:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 > size and cur:
            parts.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur.strip():
        parts.append(cur)
    return parts


def guess_title(text: str, fallback: str = "Hujjat tahlili") -> str:
    for line in text.split("\n")[:25]:
        s = line.strip(" #*-•")
        if 8 <= len(s) <= 110 and not s.lower().startswith("---"):
            return s
    return fallback


def shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
