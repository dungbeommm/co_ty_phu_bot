from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db import Database
from app.game.engine import GameError, asset_value, decide_purchase, roll_turn, start_room
from app.game.models import Phase
from app.handlers.common import final_rank, lobby_text, reward_for, status_text
from app.services.games import GameManager
from app.shop import ITEMS, shop_text

router = Router()
HELP = """🎲 CỜ TỶ PHÚ BOT
/newgame — tạo ván trong nhóm
/join — tham gia
/startgame — bắt đầu
/roll — xúc xắc
/status — trạng thái
/cancel — huỷ ván (chủ phòng)
/profile — hồ sơ và túi đồ
/shop — cửa hàng
/buy ITEM_ID — mua vật phẩm
/leaderboard — bảng xếp hạng"""


def _name(message: Message) -> str:
    return message.from_user.full_name if message.from_user else "Người chơi"

async def _ensure(message: Message, db: Database) -> None:
    if message.from_user:
        await db.upsert_user(message.from_user.id, message.chat.id, message.from_user.username, _name(message))

@router.message(Command("start", "help"))
async def help_handler(message: Message, db: Database) -> None:
    await _ensure(message, db); await message.answer(HELP)

@router.message(Command("newgame"))
async def new_game(message: Message, db: Database, games: GameManager) -> None:
    await _ensure(message, db)
    if message.chat.type == "private":
        await message.answer("Hãy dùng lệnh này trong nhóm Telegram."); return
    try:
        entry = await games.create(message.chat.id, message.from_user.id, _name(message))
        await message.answer(lobby_text(entry.room))
    except ValueError as exc: await message.answer(str(exc))

@router.message(Command("join"))
async def join_game(message: Message, db: Database, games: GameManager) -> None:
    await _ensure(message, db)
    try:
        room = await games.join(message.chat.id, message.from_user.id, _name(message))
        await message.answer(lobby_text(room))
    except (ValueError, GameError) as exc: await message.answer(str(exc))

@router.message(Command("startgame"))
async def start_game(message: Message, games: GameManager) -> None:
    entry = games.get(message.chat.id)
    if not entry: await message.answer("Chưa có phòng."); return
    try:
        async with entry.lock:
            start_room(entry.room, message.from_user.id); first = entry.room.current_player.name
        await message.answer(f"🚀 Bắt đầu!\n➡️ Lượt đầu: {first}\nDùng /roll")
    except GameError as exc: await message.answer(str(exc))

@router.message(Command("roll"))
async def roll(message: Message, db: Database, games: GameManager) -> None:
    entry = games.get(message.chat.id)
    if not entry: await message.answer("Chưa có ván."); return
    try:
        async with entry.lock:
            result = roll_turn(entry.room, message.from_user.id)
            room = entry.room
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛒 Mua", callback_data="purchase:yes"), InlineKeyboardButton(text="⏭ Bỏ", callback_data="purchase:no")]]) if result.awaiting_purchase else None
            rewards = [(uid, reward_for(rank, assets), False) for uid, rank, assets in result.bankrupt]
            if result.winner_id:
                winner = room.find_player(result.winner_id); rewards.append((winner.user_id, reward_for(1, asset_value(room, winner)), True))
            ranking = final_rank(room) if result.finished else None
        await message.answer(result.text, reply_markup=keyboard)
        for uid, stars, won in rewards: await db.add_reward(uid, message.chat.id, stars, won)
        if ranking: await message.answer(ranking); await games.remove(message.chat.id)
        elif not result.awaiting_purchase: await message.answer(f"➡️ Lượt: {room.current_player.name}")
    except GameError as exc: await message.answer(str(exc))

@router.callback_query(F.data.startswith("purchase:"))
async def purchase(callback: CallbackQuery, games: GameManager) -> None:
    if not callback.message: return
    entry = games.get(callback.message.chat.id)
    if not entry: await callback.answer("Ván không còn.", show_alert=True); return
    try:
        async with entry.lock: text = decide_purchase(entry.room, callback.from_user.id, callback.data.endswith("yes"))
        await callback.answer(); await callback.message.edit_reply_markup(reply_markup=None); await callback.message.answer(text)
    except GameError as exc: await callback.answer(str(exc), show_alert=True)

@router.message(Command("status"))
async def status(message: Message, games: GameManager) -> None:
    entry = games.get(message.chat.id)
    if not entry: await message.answer("Không có ván."); return
    async with entry.lock: text = status_text(entry.room)
    await message.answer(text)

@router.message(Command("cancel"))
async def cancel(message: Message, games: GameManager) -> None:
    entry = games.get(message.chat.id)
    if not entry: await message.answer("Không có ván."); return
    if entry.room.host_id != message.from_user.id: await message.answer("Chỉ chủ phòng được huỷ."); return
    await games.remove(message.chat.id); await message.answer("🗑 Đã huỷ ván.")

@router.message(Command("profile"))
async def profile(message: Message, db: Database) -> None:
    await _ensure(message, db); row = await db.profile(message.from_user.id, message.chat.id); bag = await db.inventory(message.from_user.id, message.chat.id)
    name, stars, wins, games_count, points = row
    items = "\n".join(f"• {item} ×{qty}" for item, qty in bag) or "Túi đồ trống"
    await message.answer(f"👤 {name}\n⭐ {stars} · 🏆 {wins}/{games_count}\n📈 {points} điểm mùa\n\n🎒 {items}")

@router.message(Command("shop"))
async def shop(message: Message) -> None: await message.answer(shop_text())

@router.message(Command("buy"))
async def buy(message: Message, command: CommandObject, db: Database) -> None:
    await _ensure(message, db); item_id = (command.args or "").strip().upper(); item = ITEMS.get(item_id)
    if not item: await message.answer("Dùng /buy ITEM_ID — xem /shop"); return
    ok = await db.buy_item(message.from_user.id, message.chat.id, item.item_id, item.cost)
    await message.answer(f"✅ Đã mua {item.name} (-{item.cost}⭐)" if ok else "Không đủ ⭐.")

@router.message(Command("leaderboard"))
async def leaderboard(message: Message, db: Database) -> None:
    rows = await db.leaderboard(message.chat.id)
    lines = ["📊 BẢNG XẾP HẠNG"] + [f"{i}. {name} — {stars}⭐ · {wins}/{games_count}" for i,(name,stars,wins,games_count) in enumerate(rows,1)]
    await message.answer("\n".join(lines) if rows else "Chưa có dữ liệu.")
