from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_path: str = "data/ty_phu.db"
    log_level: str = "INFO"
    min_players: int = 2
    max_players: int = 6
    starting_cash: int = 15_000_000
    pass_go_salary: int = 2_000_000

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or token.startswith("REPLACE_WITH"):
            raise RuntimeError("Thiếu BOT_TOKEN hợp lệ trong biến môi trường hoặc file .env")

        settings = cls(
            bot_token=token,
            database_path=os.getenv("DATABASE_PATH", "data/ty_phu.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            min_players=int(os.getenv("MIN_PLAYERS", "2")),
            max_players=int(os.getenv("MAX_PLAYERS", "6")),
            starting_cash=int(os.getenv("STARTING_CASH", "15000000")),
            pass_go_salary=int(os.getenv("PASS_GO_SALARY", "2000000")),
        )
        if settings.min_players < 2:
            raise RuntimeError("MIN_PLAYERS phải >= 2")
        if not settings.min_players <= settings.max_players <= 12:
            raise RuntimeError("MAX_PLAYERS phải từ MIN_PLAYERS đến 12")
        if settings.starting_cash <= 0 or settings.pass_go_salary < 0:
            raise RuntimeError("Cấu hình tiền không hợp lệ")
        return settings
