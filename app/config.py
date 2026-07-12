from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# =====================================================================
#  Tùy chọn cuối cùng: điền token trực tiếp nếu không dùng bot_token.txt.
#  Dán token MỚI từ @BotFather vào giữa hai dấu ngoặc kép bên dưới.
#  Ví dụ: TOKEN = "123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#  ⚠️ CẢNH BÁO BẢO MẬT:
#    - KHÔNG commit / đẩy file này lên GitHub khi đã có token.
#    - Nếu token từng bị lộ, hãy /revoke trong @BotFather rồi lấy token mới.
#    - Cách an toàn hơn là chạy: python setup-token.py
# =====================================================================
TOKEN = "8725367595:AAFFZE6MF1zM1DJH4Tdtc8RN4ChiOyXvqL4"


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_path: str = "data/ty_phu.db"
    log_level: str = "INFO"
    min_players: int = 2
    max_players: int = 6
    starting_cash: int = 15_000_000
    pass_go_salary: int = 2_000_000
    allowed_topic_ids: tuple[int, ...] = ()
    turn_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        # Không cần Secret Manager: server có thể lưu token trong bot_token.txt (chmod 600).
        token_file = Path(os.getenv("BOT_TOKEN_FILE", "bot_token.txt"))
        file_token = token_file.read_text(encoding="utf-8").strip() if token_file.is_file() else ""
        token = os.getenv("BOT_TOKEN", "").strip() or file_token or TOKEN.strip()
        if not token or token.startswith("REPLACE_WITH"):
            raise RuntimeError(
                "Thiếu token. Hãy chạy deploy/install-server.sh để tạo bot_token.txt, "
                "hoặc tự tạo file bot_token.txt chỉ chứa token BotFather."
            )

        topic_ids_raw = os.getenv("ALLOWED_TOPIC_IDS", "").strip()
        try:
            allowed_topic_ids = tuple(
                int(value.strip())
                for value in topic_ids_raw.split(",")
                if value.strip()
            )
        except ValueError as exc:
            raise RuntimeError("ALLOWED_TOPIC_IDS phải là các số, cách nhau bằng dấu phẩy") from exc

        settings = cls(
            bot_token=token,
            database_path=os.getenv("DATABASE_PATH", "data/ty_phu.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            min_players=int(os.getenv("MIN_PLAYERS", "2")),
            max_players=int(os.getenv("MAX_PLAYERS", "6")),
            starting_cash=int(os.getenv("STARTING_CASH", "15000000")),
            pass_go_salary=int(os.getenv("PASS_GO_SALARY", "2000000")),
            allowed_topic_ids=allowed_topic_ids,
            turn_seconds=max(30, int(os.getenv("TURN_SECONDS", "300"))),
        )
        if settings.min_players < 2:
            raise RuntimeError("MIN_PLAYERS phải >= 2")
        if not settings.min_players <= settings.max_players <= 12:
            raise RuntimeError("MAX_PLAYERS phải từ MIN_PLAYERS đến 12")
        if settings.starting_cash <= 0 or settings.pass_go_salary < 0:
            raise RuntimeError("Cấu hình tiền không hợp lệ")
        return settings
