from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        migration = Path("migrations/001_init.sql").read_text(encoding="utf-8")
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.executescript(migration)
            await db.commit()

    async def upsert_user(self, user_id: int, chat_id: int, username: str | None, name: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO users(telegram_id,chat_id,username,display_name) VALUES(?,?,?,?)
                ON CONFLICT(telegram_id,chat_id) DO UPDATE SET username=excluded.username,
                display_name=excluded.display_name,updated_at=CURRENT_TIMESTAMP""",
                (user_id, chat_id, username, name),
            )
            await db.commit()

    async def add_reward(self, user_id: int, chat_id: int, stars: int, won: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE users SET stars=stars+?,games_played=games_played+1,
                wins=wins+?,season_points=season_points+?,updated_at=CURRENT_TIMESTAMP
                WHERE telegram_id=? AND chat_id=?""",
                (stars, int(won), 3 if won else 0, user_id, chat_id),
            )
            await db.commit()

    async def profile(self, user_id: int, chat_id: int) -> tuple | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT display_name,stars,wins,games_played,season_points FROM users WHERE telegram_id=? AND chat_id=?",
                (user_id, chat_id),
            )
            return await cursor.fetchone()

    async def inventory(self, user_id: int, chat_id: int) -> list[tuple[str, int]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT item_id,qty FROM inventory WHERE telegram_id=? AND chat_id=? AND qty>0",
                (user_id, chat_id),
            )
            return await cursor.fetchall()

    async def buy_item(self, user_id: int, chat_id: int, item_id: str, cost: int) -> bool:
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "UPDATE users SET stars=stars-? WHERE telegram_id=? AND chat_id=? AND stars>=?",
                (cost, user_id, chat_id, cost),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return False
            await db.execute(
                """INSERT INTO inventory(telegram_id,chat_id,item_id,qty) VALUES(?,?,?,1)
                ON CONFLICT(telegram_id,chat_id,item_id) DO UPDATE SET qty=qty+1""",
                (user_id, chat_id, item_id),
            )
            await db.commit()
            return True

    async def leaderboard(self, chat_id: int) -> list[tuple]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """SELECT display_name,stars,wins,games_played FROM users WHERE chat_id=?
                ORDER BY stars DESC,wins DESC LIMIT 10""",
                (chat_id,),
            )
            return await cursor.fetchall()
