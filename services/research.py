"""Internetdagi ishonchli manbalardan ma'lumot va rasm yig'ish.

Manbalar:
  * Wikipedia (uz / ru / en) - REST API
  * Wikimedia Commons - erkin litsenziyali rasmlar
  * Openverse - ochiq litsenziyali rasmlar (zaxira)
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

UA = {"User-Agent": "EduBot/1.0 (Telegram education bot; contact: bot@example.com)"}
LANGS = ("uz", "ru", "en")


# ------------------------------------------------------------------ matn
async def _wiki_search(client: httpx.AsyncClient, lang: str, query: str, limit: int) -> list[str]:
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "format": "json", "srprop": "",
    }
    r = await client.get(url, params=params, headers=UA)
    r.raise_for_status()
    return [it["title"] for it in r.json().get("query", {}).get("search", [])]


async def _wiki_summary(client: httpx.AsyncClient, lang: str, title: str) -> dict | None:
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query", "prop": "extracts|info", "titles": title,
        "explaintext": 1, "exsectionformat": "plain", "inprop": "url", "format": "json",
    }
    try:
        r = await client.get(url, params=params, headers=UA)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            extract = (page.get("extract") or "").strip()
            if len(extract) > 250:
                return {
                    "title": page.get("title", title),
                    "url": page.get("fullurl", f"https://{lang}.wikipedia.org/wiki/{title}"),
                    "extract": re.sub(r"\n{2,}", "\n", extract)[:6000],
                    "lang": lang,
                }
    except Exception as exc:  # noqa: BLE001
        log.debug("wiki summary xato: %s", exc)
    return None


async def gather_research(queries: list[str], max_articles: int = 6) -> list[dict]:
    """Berilgan so'rovlar bo'yicha Wikipedia maqolalarini yig'adi."""
    results: list[dict] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        for query in queries[:4]:
            if len(results) >= max_articles:
                break
            for lang in LANGS:
                try:
                    titles = await _wiki_search(client, lang, query, 3)
                except Exception:  # noqa: BLE001
                    continue
                if not titles:
                    continue
                summaries = await asyncio.gather(
                    *(_wiki_summary(client, lang, t) for t in titles),
                    return_exceptions=True,
                )
                for s in summaries:
                    if isinstance(s, dict) and s["title"].lower() not in seen:
                        seen.add(s["title"].lower())
                        results.append(s)
                if results:
                    break  # shu so'rov uchun til topildi
    return results[:max_articles]


# ------------------------------------------------------------------ rasm
async def _commons_images(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    params = {
        "action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6", "gsrlimit": str(limit * 2), "prop": "imageinfo",
        "iiprop": "url|size|mime", "iiurlwidth": "1280", "format": "json",
    }
    r = await client.get("https://commons.wikimedia.org/w/api.php", params=params, headers=UA)
    r.raise_for_status()
    urls = []
    for page in r.json().get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            continue
        if info.get("width", 0) < 500:
            continue
        url = info.get("thumburl") or info.get("url")
        if url:
            urls.append(url)
    return urls[:limit]


async def _openverse_images(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    try:
        r = await client.get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": limit, "license_type": "all"},
            headers=UA,
        )
        r.raise_for_status()
        return [
            it["url"] for it in r.json().get("results", []) if it.get("url")
        ][:limit]
    except Exception:  # noqa: BLE001
        return []


async def fetch_images(queries: list[str], dest_dir: Path, per_query: int = 1) -> dict[str, str]:
    """Har bir so'rov uchun rasm yuklab oladi. {query: filepath} qaytaradi."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    used: set[str] = set()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        async def one(idx: int, query: str) -> None:
            q = (query or "").strip()
            if not q:
                return
            urls: list[str] = []
            try:
                urls = await _commons_images(client, q, 4)
            except Exception as exc:  # noqa: BLE001
                log.debug("commons xato (%s): %s", q, exc)
            if not urls:
                urls = await _openverse_images(client, q, 4)
            for url in urls:
                if url in used:
                    continue
                try:
                    resp = await client.get(url, headers=UA)
                    if resp.status_code != 200 or len(resp.content) < 12000:
                        continue
                    ext = ".png" if "png" in resp.headers.get("content-type", "") else ".jpg"
                    path = dest_dir / f"img_{idx}{ext}"
                    path.write_bytes(resp.content)
                    if _valid_image(path):
                        used.add(url)
                        out[query] = str(path)
                        return
                except Exception as exc:  # noqa: BLE001
                    log.debug("rasm yuklash xatosi: %s", exc)

        await asyncio.gather(*(one(i, q) for i, q in enumerate(queries)))
    return out


def _valid_image(path: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if im.width < 320 or im.height < 220:
                return False
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
                im.save(path)
        return True
    except Exception:  # noqa: BLE001
        return False
