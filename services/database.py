"""PostgreSQL database xizmati — foydalanuvchilar va tarix."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# aiopg yoki asyncpg — Railway PostgreSQL uchun
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


class Database:
    """Async PostgreSQL wrapper. DATABASE_URL yo'q bo'lsa — silent, xato bermaydi."""

    def __init__(self) -> None:
        self._pool: Optional[object] = None
        self.enabled = bool(DATABASE_URL and HAS_ASYNCPG)
        if not HAS_ASYNCPG and DATABASE_URL:
            log.warning("asyncpg o'rnatilmagan. pip install asyncpg")
        if not DATABASE_URL:
            log.info("DATABASE_URL yo'q — database o'chirilgan rejim")

    async def connect(self) -> None:
        if not self.enabled:
            return
        try:
            import asyncpg
            # Railway PostgreSQL SSL talab qiladi
            url = DATABASE_URL
            if "railway" in url and "sslmode" not in url:
                url += "?sslmode=require"
            self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
            await self._init_tables()
            log.info("PostgreSQL ulanish muvaffaqiyatli")
        except Exception as e:
            log.error("PostgreSQL ulanmadi: %s", e)
            self.enabled = False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _init_tables(self) -> None:
        """Jadvallarni yaratish (agar yo'q bo'lsa)."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     BIGINT PRIMARY KEY,
                    username    TEXT,
                    full_name   TEXT,
                    first_seen  TIMESTAMPTZ DEFAULT NOW(),
                    last_seen   TIMESTAMPTZ DEFAULT NOW(),
                    read_count  INTEGER DEFAULT 0,
                    pptx_count  INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS history (
                    id          SERIAL PRIMARY KEY,
                    user_id     BIGINT REFERENCES users(user_id),
                    action      TEXT NOT NULL,       -- 'read' | 'presentation'
                    filename    TEXT,
                    file_size   BIGINT,
                    ai_provider TEXT,
                    success     BOOLEAN DEFAULT TRUE,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_history_user
                    ON history(user_id, created_at DESC);
            """)
        log.info("Jadvallar tayyor")

    # ── Foydalanuvchi ──────────────────────────────────────────
    async def upsert_user(
        self, user_id: int, username: str | None, full_name: str
    ) -> None:
        if not self.enabled:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO users (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE
                        SET username  = EXCLUDED.username,
                            full_name = EXCLUDED.full_name,
                            last_seen = NOW()
                """, user_id, username, full_name)
        except Exception as e:
            log.debug("upsert_user xato: %s", e)

    async def inc_count(self, user_id: int, action: str) -> None:
        """read_count yoki pptx_count ni 1 ga oshirish."""
        if not self.enabled:
            return
        col = "read_count" if action == "read" else "pptx_count"
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE users SET {col} = {col} + 1 WHERE user_id = $1",
                    user_id
                )
        except Exception as e:
            log.debug("inc_count xato: %s", e)

    # ── Tarix ──────────────────────────────────────────────────
    async def log_action(
        self,
        user_id: int,
        action: str,
        filename: str = "",
        file_size: int = 0,
        ai_provider: str = "",
        success: bool = True,
    ) -> None:
        if not self.enabled:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO history
                        (user_id, action, filename, file_size, ai_provider, success)
                    VALUES ($1,$2,$3,$4,$5,$6)
                """, user_id, action, filename, file_size, ai_provider, success)
        except Exception as e:
            log.debug("log_action xato: %s", e)

    async def get_user_stats(self, user_id: int) -> dict:
        if not self.enabled:
            return {}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1", user_id
                )
                if not row:
                    return {}
                return dict(row)
        except Exception as e:
            log.debug("get_user_stats xato: %s", e)
            return {}

    async def get_global_stats(self) -> dict:
        if not self.enabled:
            return {}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(DISTINCT user_id) AS total_users,
                        SUM(read_count)         AS total_reads,
                        SUM(pptx_count)         AS total_pptx
                    FROM users
                """)
                return dict(row) if row else {}
        except Exception as e:
            log.debug("get_global_stats xato: %s", e)
            return {}


# Global instance
db = Database()
