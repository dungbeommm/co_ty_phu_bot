import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.config import Settings
from app.db import Database
from app.handlers.router import router
from app.services.games import GameManager


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(settings.database_path)
    await db.initialize()
    bot = Bot(settings.bot_token)
    me = await bot.get_me()
    logging.info("Logged in as @%s", me.username)
    await bot.set_my_commands([BotCommand(command="newgame", description="Tạo ván"), BotCommand(command="join", description="Tham gia"), BotCommand(command="roll", description="Xúc xắc"), BotCommand(command="profile", description="Hồ sơ"), BotCommand(command="shop", description="Cửa hàng")])
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot, db=db, games=GameManager(settings), allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
