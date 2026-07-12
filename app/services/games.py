from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.config import Settings
from app.game.board import create_board
from app.game.engine import join_room
from app.game.models import GameRoom, Player

RoomKey = tuple[int, int | None]


@dataclass(slots=True)
class RoomEntry:
    room: GameRoom
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_menu_message_id: int | None = None


class GameManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rooms: dict[RoomKey, RoomEntry] = {}
        self._index_lock = asyncio.Lock()

    @staticmethod
    def _key(chat_id: int, topic_id: int | None) -> RoomKey:
        return chat_id, topic_id

    def topic_allowed(self, topic_id: int | None) -> bool:
        """Danh sách rỗng cho phép mọi topic; ngược lại chỉ cho ID đã cấu hình."""
        allowed = self.settings.allowed_topic_ids
        return not allowed or topic_id in allowed

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
            entry = RoomEntry(room)
            self._rooms[key] = entry
            return entry

    def get(self, chat_id: int, topic_id: int | None) -> RoomEntry | None:
        return self._rooms.get(self._key(chat_id, topic_id))

    async def remove(self, chat_id: int, topic_id: int | None) -> None:
        async with self._index_lock:
            self._rooms.pop(self._key(chat_id, topic_id), None)

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
            return entry.room
