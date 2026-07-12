from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.config import Settings
if TYPE_CHECKING:
    from app.db import Database
from app.game.board import create_board
from app.game.engine import join_room
from app.game.models import GameRoom, Player
from app.game.serialize import dumps_room, loads_room

RoomKey = tuple[int, int | None]


@dataclass(slots=True)
class RoomEntry:
    room: GameRoom
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Nhiều menu có thể cùng tồn tại (ví dụ /menu hoặc bảng trạng thái).
    # Mỗi message chỉ được xử lý đúng một callback để chống bấm đúp.
    active_menu_message_ids: set[int] = field(default_factory=set)
    consumed_menu_message_ids: set[int] = field(default_factory=set)


class GameManager:
    def __init__(self, settings: Settings, db: Database | None = None) -> None:
        self.settings = settings
        self.db = db
        self._rooms: dict[RoomKey, RoomEntry] = {}
        self._index_lock = asyncio.Lock()

    @staticmethod
    def _key(chat_id: int, topic_id: int | None) -> RoomKey:
        return chat_id, topic_id

    def topic_allowed(self, topic_id: int | None) -> bool:
        """Danh sách rỗng cho phép mọi topic; ngược lại chỉ cho ID đã cấu hình."""
        allowed = self.settings.allowed_topic_ids
        return not allowed or topic_id in allowed

    def arm_turn_deadline(self, room: GameRoom) -> None:
        if room.phase.value in {"playing", "awaiting_purchase"}:
            room.turn_deadline = time.time() + self.settings.turn_seconds
        else:
            room.turn_deadline = None

    async def persist(self, room: GameRoom) -> None:
        if not self.db:
            return
        if room.phase.value == "finished":
            await self.db.delete_active_game(room.chat_id, room.topic_id)
            return
        await self.db.save_active_game(room.chat_id, room.topic_id, dumps_room(room))

    async def load_persisted(self) -> int:
        if not self.db:
            return 0
        rows = await self.db.load_active_games()
        count = 0
        async with self._index_lock:
            for chat_id, topic_id, payload in rows:
                try:
                    room = loads_room(payload)
                except Exception:
                    continue
                key = self._key(chat_id, topic_id)
                self._rooms[key] = RoomEntry(room)
                count += 1
        return count

    async def create(
        self,
        chat_id: int,
        topic_id: int | None,
        host_id: int,
        host_name: str,
    ) -> RoomEntry:
        if not self.topic_allowed(topic_id):
            raise ValueError("Topic này không được phép tạo ván.")
        key = self._key(chat_id, topic_id)
        async with self._index_lock:
            if key in self._rooms:
                raise ValueError("Topic đang có phòng/ván. Dùng /status hoặc /cancel.")
            room = GameRoom(
                chat_id=chat_id,
                host_id=host_id,
                players=[Player(host_id, host_name, self.settings.starting_cash)],
                board=create_board(),
                starting_cash=self.settings.starting_cash,
                pass_go_salary=self.settings.pass_go_salary,
                min_players=self.settings.min_players,
                max_players=self.settings.max_players,
                topic_id=topic_id,
            )
            room.log(f"🕹 {host_name} tạo phòng")
            entry = RoomEntry(room)
            self._rooms[key] = entry
        await self.persist(room)
        return entry

    def get(self, chat_id: int, topic_id: int | None) -> RoomEntry | None:
        return self._rooms.get(self._key(chat_id, topic_id))

    async def remove(self, chat_id: int, topic_id: int | None) -> None:
        async with self._index_lock:
            self._rooms.pop(self._key(chat_id, topic_id), None)
        if self.db:
            await self.db.delete_active_game(chat_id, topic_id)

    async def join(
        self,
        chat_id: int,
        topic_id: int | None,
        user_id: int,
        name: str,
    ) -> GameRoom:
        entry = self.get(chat_id, topic_id)
        if not entry:
            raise ValueError("Chưa có phòng trong topic này. Dùng /newgame trước.")
        async with entry.lock:
            join_room(entry.room, user_id, name)
            entry.room.log(f"➕ {name} tham gia")
            await self.persist(entry.room)
            return entry.room

    def all_entries(self) -> list[RoomEntry]:
        return list(self._rooms.values())
