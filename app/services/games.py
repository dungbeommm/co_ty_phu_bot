from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.config import Settings
from app.game.board import create_board
from app.game.engine import join_room
from app.game.models import GameRoom, Player


@dataclass(slots=True)
class RoomEntry:
    room: GameRoom
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class GameManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rooms: dict[int, RoomEntry] = {}
        self._index_lock = asyncio.Lock()

    async def create(self, chat_id: int, host_id: int, host_name: str) -> RoomEntry:
        async with self._index_lock:
            if chat_id in self._rooms:
                raise ValueError("Nhóm đang có phòng/ván. Dùng /status hoặc /cancel.")
            room = GameRoom(
                chat_id=chat_id,
                host_id=host_id,
                players=[Player(host_id, host_name, self.settings.starting_cash)],
                board=create_board(),
                starting_cash=self.settings.starting_cash,
                pass_go_salary=self.settings.pass_go_salary,
                min_players=self.settings.min_players,
                max_players=self.settings.max_players,
            )
            entry = RoomEntry(room)
            self._rooms[chat_id] = entry
            return entry

    def get(self, chat_id: int) -> RoomEntry | None:
        return self._rooms.get(chat_id)

    async def remove(self, chat_id: int) -> None:
        async with self._index_lock:
            self._rooms.pop(chat_id, None)

    async def join(self, chat_id: int, user_id: int, name: str) -> GameRoom:
        entry = self.get(chat_id)
        if not entry:
            raise ValueError("Chưa có phòng. Dùng /newgame trước.")
        async with entry.lock:
            join_room(entry.room, user_id, name)
            return entry.room
