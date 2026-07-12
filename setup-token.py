from __future__ import annotations

import getpass
import os
from pathlib import Path


def main() -> None:
    path = Path(__file__).resolve().parent / "bot_token.txt"
    token = getpass.getpass("Dán BOT_TOKEN từ @BotFather: ").strip()
    if not token or ":" not in token:
        raise SystemExit("Token không hợp lệ; token Telegram phải có dạng ID:CHUOI_BI_MAT")
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows không hỗ trợ đầy đủ chmod kiểu Unix.
        pass
    print(f"Đã lưu token cục bộ tại {path.name}. File này đã được .gitignore bỏ qua.")


if __name__ == "__main__":
    main()
