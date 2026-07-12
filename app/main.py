from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand

from app.config import Settings
from app.db import Database
from app.handlers.router import router
from app.services.games import GameManager

logger = logging.getLogger("ty_phu_bot")

BOT_COMMANDS = [
    BotCommand(command="help", description="Hướng dẫn"),
    BotCommand(command="menu", description="Mở menu chơi"),
    BotCommand(command="newgame", description="Tạo ván"),
    BotCommand(command="join", description="Tham gia"),
    BotCommand(command="startgame", description="Bắt đầu"),
    BotCommand(command="roll", description="Xúc xắc"),
    BotCommand(command="status", description="Trạng thái ván"),
    BotCommand(command="profile", description="Hồ sơ"),
    BotCommand(command="shop", description="Cửa hàng"),
    BotCommand(command="leaderboard", description="Bảng xếp hạng"),
]


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows event loop does not support add_signal_handler.
            signal.signal(sig, lambda *_: stop_event.set())


async def run() -> None:
    settings = Settings.from_env()
    _configure_logging(settings.log_level)
    logger.info("Khởi động ty-phu-bot")

    db = Database(settings.database_path)
    await db.initialize()
    logger.info("Đã kết nối SQLite: %s", settings.database_path)

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    try:
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError:
            logger.error(
                "Token bị Telegram từ chối (Unauthorized). "
                "Token sai hoặc đã bị /revoke. "
                "Hãy lấy token MỚI từ @BotFather rồi điền lại."
            )
            return
        logger.info("Đăng nhập thành công: @%s", me.username)
        await bot.set_my_commands(BOT_COMMANDS)

        dp = Dispatcher()
        dp.include_router(router)

        stop_event = asyncio.Event()
        await _install_signal_handlers(stop_event)

        polling = asyncio.create_task(
            dp.start_polling(
                bot,
                db=db,
                games=GameManager(settings),
                handle_signals=False,
                allowed_updates=dp.resolve_used_update_types(),
            )
        )

        stop_wait = asyncio.create_task(stop_event.wait())
        done, _ = await asyncio.wait(
            {polling, stop_wait}, return_when=asyncio.FIRST_COMPLETED
        )

        if stop_wait in done:
            logger.info("Nhận tín hiệu dừng, đang tắt bot...")
            await dp.stop_polling()

        stop_wait.cancel()
        try:
            await polling
        except asyncio.CancelledError:
            pass
    finally:
        await bot.session.close()
        logger.info("Đã dừng bot an toàn.")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
