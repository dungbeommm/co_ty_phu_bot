from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.db import Database
from app.game.engine import (
    GameError,
    MIN_CASH_RESERVE,
    asset_value,
    assign_secret_missions,
    buy_insurance,
    build_house,
    buildable_properties,
    building_name,
    buy_illegal_item,
    decide_purchase,
    demolish_house,
    final_stats,
    pay_bail,
    demolishable_properties,
    gamble,
    house_cost,
    mortgage_property,
    mortgage_value,
    mortgageable_properties,
    open_mystery_box,
    property_info,
    propose_trade,
    recent_events,
    respond_trade,
    roll_turn,
    sabotage_house,
    start_room,
    steal_from_player,
    surrender,
    unmortgage_cost,
    unmortgage_property,
    unmortgageable_properties,
)
from app.game.models import GameRoom, Phase, PlayerStatus
from app.handlers.common import final_rank, lobby_text, reward_for, status_text
from app.render import render_board
from app.services.games import GameManager
from app.shop import ITEMS, shop_text

router = Router()
T = TypeVar("T")
MENU_CONSUMED_MSG = "Nút này đã được xử lý. Hãy dùng /menu để mở lại menu."
HELP = """🎲 CỜ TỶ PHÚ BOT
/menu — mở menu nút bấm
/newgame — tạo ván trong topic
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


def _topic_id(message: Message) -> int | None:
    return message.message_thread_id if message.is_topic_message else None


def _topic_allowed(message: Message, games: GameManager) -> bool:
    if message.chat.type == "private":
        return True
    return games.topic_allowed(_topic_id(message))


def _room(message: Message, games: GameManager):
    return games.get(message.chat.id, _topic_id(message))


def _lobby_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Tham gia", callback_data="game:join")],
            [InlineKeyboardButton(text="🛡 Bật/Tắt chế độ an toàn", callback_data="game:safe")],
            [
                InlineKeyboardButton(text="🚀 Bắt đầu", callback_data="game:start"),
                InlineKeyboardButton(text="📋 Trạng thái", callback_data="game:status"),
            ],
            [InlineKeyboardButton(text="🗑 Huỷ ván", callback_data="game:cancel")],
        ]
    )


def _turn_menu(room: GameRoom) -> InlineKeyboardMarkup:
    if room.current_player.status is PlayerStatus.JAILED:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🔒 {room.current_player.name} thử ra tù", callback_data="game:roll")],
                [InlineKeyboardButton(text="💵 Nộp phạt ra tù · 500K", callback_data="game:bail")],
                [InlineKeyboardButton(text="📋 Trạng thái", callback_data="game:status")],
                [InlineKeyboardButton(text="🏳 Chịu thua", callback_data="game:surrender")],
            ]
        )
    strategic_available = "strategic" not in room.used_turn_actions
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"🎲 {room.current_player.name} đổ xúc xắc", callback_data="game:roll")]
    ]

    if strategic_available:
        property_actions: list[InlineKeyboardButton] = []
        if buildable_properties(room, room.current_player.user_id):
            property_actions.append(InlineKeyboardButton(text="🏠 Xây tại đất đang đứng", callback_data="game:build"))
        if demolishable_properties(room, room.current_player.user_id):
            property_actions.append(InlineKeyboardButton(text="🏚 Phá nhà", callback_data="game:demolish"))
        if mortgageable_properties(room, room.current_player.user_id):
            property_actions.append(InlineKeyboardButton(text="🏦 Thế chấp", callback_data="game:mortgage"))
        if unmortgageable_properties(room, room.current_player.user_id):
            property_actions.append(InlineKeyboardButton(text="🔓 Chuộc đất", callback_data="game:unmortgage"))
        if property_actions:
            rows.append(property_actions)

        special_actions: list[InlineKeyboardButton] = []
        if not room.current_player.mystery_used:
            special_actions.append(InlineKeyboardButton(text="🎁 Hộp bí ẩn", callback_data="game:mystery"))
        special_actions.append(InlineKeyboardButton(text="🥷 Trộm", callback_data="game:steal"))
        rows.append(special_actions)

    # Hai trò này được phép chơi nhiều lần trong cùng lượt.
    rows.append(
        [
            InlineKeyboardButton(text="🎡 Vòng quay", callback_data="game:wheel"),
            InlineKeyboardButton(text="🎲 Tài/Xỉu", callback_data="game:taixiu"),
        ]
    )

    if strategic_available:
        rows.append(
            [
                InlineKeyboardButton(text="🕶 Chợ đen", callback_data="game:blackmarket"),
                InlineKeyboardButton(text="💣 Phá hoại", callback_data="game:sabotage"),
            ]
        )

    if strategic_available:
        rows.append([InlineKeyboardButton(text="🛡 Bảo hiểm đất đang đứng", callback_data="game:insurance")])
    rows.append([InlineKeyboardButton(text="📋 Trạng thái", callback_data="game:status")])
    rows.append(
        [
            InlineKeyboardButton(text="📍 Thông tin đất", callback_data="game:info"),
            InlineKeyboardButton(text="📜 Nhật ký", callback_data="game:log"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🏳 Chịu thua", callback_data="game:surrender")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    indexes = buildable_properties(room, actor_id)
    if not indexes:
        return None
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"🏠 {room.board[index].name} "
                    f"→ {building_name(room.board[index].houses + 1)} · "
                    f"{'MIỄN PHÍ' if room.current_player.building_vouchers else str(house_cost(room.board[index]) // 1000) + 'K'}"
                ),
                callback_data=f"build:{index}",
            )
        ]
        for index in indexes
    ]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="build:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _demolish_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    indexes = demolishable_properties(room, actor_id)
    if not indexes:
        return None
    rows = [
        [InlineKeyboardButton(
            text=f"🏚 {room.board[i].name} ({building_name(room.board[i].houses)}) · +{house_cost(room.board[i]) // 2000}K",
            callback_data=f"extra:demolish:{i}",
        )]
        for i in indexes
    ]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mortgage_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    indexes = mortgageable_properties(room, actor_id)
    if not indexes:
        return None
    rows = [
        [InlineKeyboardButton(
            text=f"🏦 {room.board[i].name} · +{mortgage_value(room.board[i]) // 1000}K",
            callback_data=f"extra:mortgage:{i}",
        )]
        for i in indexes
    ]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _unmortgage_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    indexes = unmortgageable_properties(room, actor_id)
    if not indexes:
        return None
    rows = [
        [InlineKeyboardButton(
            text=f"🔓 {room.board[i].name} · -{unmortgage_cost(room.board[i]) // 1000}K",
            callback_data=f"extra:unmortgage:{i}",
        )]
        for i in indexes
    ]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _steal_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    targets = [p for p in room.active_players if p.user_id != actor_id]
    rows = [[InlineKeyboardButton(text=f"🥷 {p.name}", callback_data=f"extra:steal:{p.user_id}")] for p in targets]
    actor = room.find_player(actor_id)
    if actor and not actor.bank_heist_used:
        rows.append([InlineKeyboardButton(text="🏦 Trộm ngân hàng · thưởng 50 triệu", callback_data="extra:steal:0")])
    if not rows:
        return None
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _stake_values(cash: int) -> list[int]:
    maximum = cash - MIN_CASH_RESERVE
    return sorted(
        {
            value
            for value in (500_000, 1_000_000, 5_000_000, 10_000_000, maximum)
            if 0 < value <= maximum
        }
    )


def _wheel_menu(cash: int) -> InlineKeyboardMarkup | None:
    values = _stake_values(cash)
    if not values:
        return None
    rows = [[InlineKeyboardButton(text=f"🎡 Cược {value:,}₫", callback_data=f"extra:wheel:{value}")] for value in values]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _tai_xiu_menu(cash: int) -> InlineKeyboardMarkup | None:
    values = _stake_values(cash)
    if not values:
        return None
    rows = [[
        InlineKeyboardButton(text=f"🔼 Tài {value:,}", callback_data=f"extra:taixiu:tai:{value}"),
        InlineKeyboardButton(text=f"🔽 Xỉu {value:,}", callback_data=f"extra:taixiu:xiu:{value}"),
    ] for value in values]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _black_market_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Bộ phá khóa · 1M (+15% trộm)", callback_data="extra:illegal:lockpick")],
        [InlineKeyboardButton(text="💣 Bom phá nhà · 2M", callback_data="extra:illegal:bomb")],
        [InlineKeyboardButton(text="🚗 Thẻ tẩu thoát · 1,5M", callback_data="extra:illegal:getaway")],
        [InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")],
    ])


def _sabotage_menu(room: GameRoom, actor_id: int) -> InlineKeyboardMarkup | None:
    targets = [p for p in room.active_players if p.user_id != actor_id and any(room.board[i].houses for i in p.property_indexes)]
    if not targets:
        return None
    rows = [[InlineKeyboardButton(text=f"💣 {p.name}", callback_data=f"extra:sabotage:{p.user_id}")] for p in targets]
    rows.append([InlineKeyboardButton(text="↩️ Quay lại", callback_data="extra:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _surrender_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏳 Xác nhận chịu thua", callback_data="extra:surrender:yes"),
            InlineKeyboardButton(text="↩️ Không", callback_data="extra:back"),
        ]
    ])


def _purchase_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛒 Mua", callback_data="purchase:yes"),
                InlineKeyboardButton(text="⏭ Bỏ qua", callback_data="purchase:no"),
            ]
        ]
    )


async def _ensure(message: Message, db: Database) -> None:
    if message.from_user:
        await db.upsert_user(
            message.from_user.id,
            message.chat.id,
            message.from_user.username,
            _name(message),
        )


async def _remove_menu(message: Message) -> None:
    """Xoá menu do bot gửi; nếu không xoá được thì ẩn bàn phím."""
    try:
        await message.delete()
    except Exception:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _with_flood_retry(call: Callable[[], Awaitable[T]]) -> T:
    """Chờ đúng thời gian Telegram yêu cầu rồi thử lại, tối đa ba lần."""
    for attempt in range(3):
        try:
            return await call()
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(float(exc.retry_after) + 0.25)
    raise RuntimeError("Không thể gửi tin nhắn sau khi chờ flood control")


async def _answer(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    return await _with_flood_retry(
        lambda: message.answer(text, reply_markup=reply_markup)
    )


async def _send_board(
    message: Message,
    room: GameRoom,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Gửi ảnh bàn cờ 2D. Nếu render lỗi thì không làm gián đoạn ván."""
    try:
        png = render_board(room)
    except Exception:
        return await _answer(message, caption or "🎲 Bàn cờ", reply_markup)
    return await _with_flood_retry(
        lambda: message.answer_photo(
            BufferedInputFile(png, filename="board.png"),
            caption=caption,
            reply_markup=reply_markup,
        )
    )


def _activate_menu(entry, sent: Message) -> None:
    """Đăng ký menu mới mà không làm vô hiệu hóa các menu trước đó."""
    entry.active_menu_message_ids.add(sent.message_id)
    # Giới hạn lịch sử để không tăng bộ nhớ trong các ván dài.
    if len(entry.active_menu_message_ids) > 50:
        entry.active_menu_message_ids = set(sorted(entry.active_menu_message_ids)[-50:])


def _claim_active_menu(entry, message: Message) -> bool:
    """Nhận callback đúng một lần cho chính menu được bấm.

    Không dùng "menu gần nhất" toàn phòng: người chơi có thể mở /menu hoặc
    /status nhiều lần mà những menu trước đó vẫn hợp lệ cho tới khi được bấm.
    Luật lượt chơi vẫn được engine kiểm tra ở từng hành động.
    """
    message_id = message.message_id
    if message_id not in entry.active_menu_message_ids:
        return False
    entry.active_menu_message_ids.remove(message_id)
    entry.consumed_menu_message_ids.add(message_id)
    if len(entry.consumed_menu_message_ids) > 100:
        entry.consumed_menu_message_ids = set(sorted(entry.consumed_menu_message_ids)[-100:])
    return True


async def _show_menu(message: Message, games: GameManager) -> None:
    entry = _room(message, games)
    if not entry:
        await _answer(message, "Chưa có phòng. Hãy dùng /newgame trong topic này.")
        return
    if entry.room.phase is Phase.LOBBY:
        sent = await _answer(message, lobby_text(entry.room), _lobby_menu())
    elif entry.room.phase is Phase.AWAITING_PURCHASE:
        player = entry.room.find_player(entry.room.pending_player_id or 0)
        sent = await _answer(
            message,
            f"⏳ Đang chờ {player.name if player else 'người chơi'} quyết định mua.",
            _purchase_menu(),
        )
    else:
        sent = await _answer(
            message,
            f"➡️ Lượt: {entry.room.current_player.name}",
            _turn_menu(entry.room),
        )
    _activate_menu(entry, sent)


async def _run_roll(message: Message, actor_id: int, db: Database, games: GameManager) -> None:
    entry = _room(message, games)
    if not entry:
        raise GameError("Chưa có ván trong topic này.")
    async with entry.lock:
        result = roll_turn(entry.room, actor_id)
        room = entry.room
        rewards = [(uid, reward_for(rank, assets), False) for uid, rank, assets in result.bankrupt]
        if result.winner_id:
            winner = room.find_player(result.winner_id)
            if winner:
                rewards.append((winner.user_id, reward_for(1, asset_value(room, winner)), True))
        ranking = final_rank(room) if result.finished else None

    keyboard = _purchase_menu() if result.awaiting_purchase else _turn_menu(room)
    caption = result.text
    if ranking:
        caption = f"{caption}\n\n{ranking}{final_stats(room)}"
        keyboard = None
    elif not result.awaiting_purchase:
        caption = f"{caption}\n\n➡️ Lượt: {room.current_player.name}"
    sent = await _send_board(message, room, caption, keyboard)
    if keyboard:
        _activate_menu(entry, sent)
    for uid, stars, won in rewards:
        await db.add_reward(uid, message.chat.id, stars, won)
    if ranking:
        await games.remove(message.chat.id, _topic_id(message))


@router.message(Command("start", "help"))
async def help_handler(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    await _ensure(message, db)
    await _answer(message, HELP)


@router.message(Command("menu"))
async def menu_handler(message: Message, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    await _show_menu(message, games)


@router.message(Command("newgame"))
async def new_game(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    await _ensure(message, db)
    if message.chat.type == "private":
        await _answer(message, "Hãy dùng lệnh này trong topic nhóm Telegram.")
        return
    try:
        entry = await games.create(
            message.chat.id,
            _topic_id(message),
            message.from_user.id,
            _name(message),
        )
        sent = await _answer(message, lobby_text(entry.room), _lobby_menu())
        _activate_menu(entry, sent)
    except ValueError as exc:
        await _answer(message, str(exc))


@router.message(Command("join"))
async def join_game(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    await _ensure(message, db)
    try:
        room = await games.join(
            message.chat.id,
            _topic_id(message),
            message.from_user.id,
            _name(message),
        )
        entry = _room(message, games)
        sent = await _answer(message, lobby_text(room), _lobby_menu())
        if entry:
            _activate_menu(entry, sent)
    except (ValueError, GameError) as exc:
        await _answer(message, str(exc))


@router.message(Command("startgame"))
async def start_game(message: Message, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    entry = _room(message, games)
    if not entry:
        await _answer(message, "Chưa có phòng trong topic này.")
        return
    try:
        async with entry.lock:
            start_room(entry.room, message.from_user.id)
            first = entry.room.current_player.name
        sent = await _send_board(
            message,
            entry.room,
            f"🚀 Bắt đầu! Mỗi người nhận 1 🎁 Hộp bí ẩn.\n➡️ Lượt đầu: {first}",
            _turn_menu(entry.room),
        )
        _activate_menu(entry, sent)
    except GameError as exc:
        await _answer(message, str(exc))


@router.message(Command("roll"))
async def roll(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    try:
        await _run_roll(message, message.from_user.id, db, games)
    except GameError as exc:
        await _answer(message, str(exc))


@router.callback_query(F.data.startswith("purchase:"))
async def purchase(callback: CallbackQuery, games: GameManager) -> None:
    if not callback.message:
        return
    message = callback.message
    if not _topic_allowed(message, games):
        await callback.answer("Nút này không dùng được trong topic này.", show_alert=True)
        return
    entry = _room(message, games)
    if not entry:
        await callback.answer("Ván không còn.", show_alert=True)
        return
    if entry.room.pending_player_id != callback.from_user.id:
        await callback.answer("Không phải quyết định của bạn.", show_alert=True)
        return
    if not _claim_active_menu(entry, message):
        await callback.answer("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.", show_alert=True)
        return
    try:
        async with entry.lock:
            text = decide_purchase(
                entry.room,
                callback.from_user.id,
                callback.data.endswith("yes"),
            )
        await callback.answer()
        await _remove_menu(message)
        sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
        _activate_menu(entry, sent)
    except GameError as exc:
        _activate_menu(entry, message)
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("build:"))
async def build_action(callback: CallbackQuery, games: GameManager) -> None:
    if not callback.message:
        return
    message = callback.message
    entry = _room(message, games)
    if not entry or not entry.room.find_player(callback.from_user.id):
        await callback.answer("Bạn không ở trong ván này.", show_alert=True)
        return
    if entry.room.current_player.user_id != callback.from_user.id:
        await callback.answer("Chỉ người đang tới lượt được xây nhà.", show_alert=True)
        return
    if not _claim_active_menu(entry, message):
        await callback.answer("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.", show_alert=True)
        return
    await callback.answer()
    await _remove_menu(message)
    if callback.data == "build:back":
        sent = await _send_board(
            message,
            entry.room,
            f"➡️ Lượt: {entry.room.current_player.name}",
            _turn_menu(entry.room),
        )
        _activate_menu(entry, sent)
        return
    try:
        tile_index = int(callback.data.removeprefix("build:"))
        async with entry.lock:
            text = build_house(entry.room, callback.from_user.id, tile_index)
        sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
        _activate_menu(entry, sent)
    except (ValueError, GameError) as exc:
        sent = await _answer(message, str(exc), _turn_menu(entry.room))
        _activate_menu(entry, sent)


@router.callback_query(F.data.startswith("game:"))
async def game_action(
    callback: CallbackQuery,
    db: Database,
    games: GameManager,
) -> None:
    if not callback.message:
        return
    message = callback.message
    if not _topic_allowed(message, games):
        await callback.answer("Topic này không được phép chơi.", show_alert=True)
        return
    entry = _room(message, games)
    if not entry:
        await callback.answer("Ván không còn.", show_alert=True)
        await _remove_menu(message)
        return

    action = callback.data.removeprefix("game:")
    player = entry.room.find_player(callback.from_user.id)
    if action != "join" and not player:
        await callback.answer("Chỉ người trong ván mới được bấm.", show_alert=True)
        return

    try:
        if action == "join":
            if player:
                raise GameError("Bạn đã ở trong phòng chờ.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await db.upsert_user(
                callback.from_user.id,
                message.chat.id,
                callback.from_user.username,
                callback.from_user.full_name,
            )
            room = await games.join(
                message.chat.id,
                _topic_id(message),
                callback.from_user.id,
                callback.from_user.full_name,
            )
            await callback.answer("Đã tham gia!")
            await _remove_menu(message)
            sent = await _answer(message, lobby_text(room), _lobby_menu())
            _activate_menu(entry, sent)
        elif action == "safe":
            if entry.room.host_id != callback.from_user.id or entry.room.phase is not Phase.LOBBY:
                raise GameError("Chỉ chủ phòng có thể đổi chế độ an toàn trước khi bắt đầu.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            entry.room.safe_mode = not entry.room.safe_mode
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, f"🛡 Chế độ an toàn: {'BẬT' if entry.room.safe_mode else 'TẮT'} (bật sẽ khóa trộm/phá hoại/chợ đen).", _lobby_menu())
            _activate_menu(entry, sent)
        elif action == "start":
            if entry.room.host_id != callback.from_user.id:
                raise GameError("Chỉ chủ phòng được bắt đầu.")
            if entry.room.phase is not Phase.LOBBY:
                raise GameError("Ván không còn ở phòng chờ.")
            if len(entry.room.players) < entry.room.min_players:
                raise GameError(f"Cần ít nhất {entry.room.min_players} người.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            async with entry.lock:
                start_room(entry.room, callback.from_user.id)
                first = entry.room.current_player.name
            await callback.answer()
            await _remove_menu(message)
            sent = await _send_board(
                message,
                entry.room,
                f"🚀 Bắt đầu! Mỗi người nhận 1 🎁 Hộp bí ẩn.\n➡️ Lượt đầu: {first}",
                _turn_menu(entry.room),
            )
            _activate_menu(entry, sent)
        elif action == "roll":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError(f"Chưa tới lượt bạn. Đang tới lượt {entry.room.current_player.name}.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            await _run_roll(message, callback.from_user.id, db, games)
        elif action == "build":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được xây nhà.")
            menu = _build_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError(
                    "Chỉ xây được khi đang đứng trên đất của mình đã ghé ít nhất 2 lần."
                )
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🏠 Chọn khu đất muốn xây nhà:", menu)
            _activate_menu(entry, sent)
        elif action == "mortgage":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được thế chấp.")
            menu = _mortgage_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError("Bạn không có đất nào có thể thế chấp (cần phá hết nhà trước).")
            if not _claim_active_menu(entry, message):
                raise GameError(MENU_CONSUMED_MSG)
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🏦 Chọn đất muốn thế chấp:", menu)
            _activate_menu(entry, sent)
        elif action == "unmortgage":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được chuộc đất.")
            menu = _unmortgage_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError("Bạn không có đất nào có thể chuộc (hoặc không đủ tiền).")
            if not _claim_active_menu(entry, message):
                raise GameError(MENU_CONSUMED_MSG)
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🔓 Chọn đất muốn chuộc:", menu)
            _activate_menu(entry, sent)
        elif action == "info":
            text = property_info(entry.room, player.position)
            await callback.answer()
            await _answer(message, text)
        elif action == "log":
            text = recent_events(entry.room)
            await callback.answer()
            await _answer(message, text)
        elif action == "bail":
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            async with entry.lock:
                text = pay_bail(entry.room, callback.from_user.id)
            await callback.answer()
            await _remove_menu(message)
            sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
            _activate_menu(entry, sent)
        elif action == "insurance":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được mua bảo hiểm.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            async with entry.lock:
                text = buy_insurance(entry.room, callback.from_user.id)
            await callback.answer()
            await _remove_menu(message)
            sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
            _activate_menu(entry, sent)
        elif action == "mystery":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được mở hộp.")
            if player.mystery_used:
                raise GameError("Bạn đã mở hộp bí ẩn trong ván này rồi.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            async with entry.lock:
                text = open_mystery_box(entry.room, callback.from_user.id)
            await callback.answer("Mở quà!")
            await _remove_menu(message)
            sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
            _activate_menu(entry, sent)
        elif action == "demolish":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được phá nhà.")
            menu = _demolish_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError("Bạn chưa có nhà nào có thể phá.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🏚 Chọn nhà muốn phá (thu hồi 50% giá xây):", menu)
            _activate_menu(entry, sent)
        elif action == "steal":
            if entry.room.safe_mode:
                raise GameError("Chế độ an toàn đang bật: trộm bị tắt.")
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được trộm.")
            menu = _steal_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError("Không có mục tiêu để trộm.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🥷 Chọn người muốn trộm:", menu)
            _activate_menu(entry, sent)
        elif action == "wheel":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được quay.")
            menu = _wheel_menu(player.cash)
            if not menu:
                raise GameError("Bạn không có tiền để đặt cược.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(
                message,
                f"🎡 Chọn tiền cược · hiện có {player.cash:,}₫\n"
                "Tỉ lệ: lỗ 55%, lời 25%: 20%, hòa 20%, jackpot ×5: 5%.",
                menu,
            )
            _activate_menu(entry, sent)
        elif action == "taixiu":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được chơi Tài/Xỉu.")
            menu = _tai_xiu_menu(player.cash)
            if not menu:
                raise GameError("Bạn không có tiền để đặt cược.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, f"🎲 Chọn cửa và tiền cược · hiện có {player.cash:,}₫", menu)
            _activate_menu(entry, sent)
        elif action == "blackmarket":
            if entry.room.safe_mode:
                raise GameError("Chế độ an toàn đang bật: chợ đen bị tắt.")
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được vào chợ đen.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "🕶 CHỢ ĐEN — mua bằng tiền trong ván:", _black_market_menu())
            _activate_menu(entry, sent)
        elif action == "sabotage":
            if entry.room.safe_mode:
                raise GameError("Chế độ an toàn đang bật: phá hoại bị tắt.")
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Chỉ người đang tới lượt được phá hoại.")
            if player.demolition_bombs <= 0:
                raise GameError("Bạn chưa có Bom phá nhà. Hãy mua tại Chợ đen.")
            menu = _sabotage_menu(entry.room, callback.from_user.id)
            if not menu:
                raise GameError("Không có đối thủ sở hữu công trình để phá.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "💣 Chọn đối thủ để phá ngẫu nhiên một công trình:", menu)
            _activate_menu(entry, sent)
        elif action == "surrender":
            if entry.room.current_player.user_id != callback.from_user.id:
                raise GameError("Bạn có thể chịu thua khi đến lượt mình.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            sent = await _answer(message, "⚠️ Chịu thua sẽ bán toàn bộ tài sản và rời ván.", _surrender_menu())
            _activate_menu(entry, sent)
        elif action == "status":
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await callback.answer()
            await _remove_menu(message)
            async with entry.lock:
                text = status_text(entry.room)
            menu = _lobby_menu() if entry.room.phase is Phase.LOBBY else _turn_menu(entry.room)
            sent = await _send_board(message, entry.room, text, menu)
            _activate_menu(entry, sent)
        elif action == "cancel":
            if entry.room.host_id != callback.from_user.id:
                raise GameError("Chỉ chủ phòng được huỷ.")
            if not _claim_active_menu(entry, message):
                raise GameError("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.")
            await games.remove(message.chat.id, _topic_id(message))
            await callback.answer()
            await _remove_menu(message)
            await _answer(message, "🗑 Đã huỷ ván.")
        else:
            await callback.answer("Thao tác không khả dụng.", show_alert=True)
    except (ValueError, GameError) as exc:
        # Nếu hành động lỗi *sau khi* đã nhận menu, mở lại menu đang hiển thị để
        # người chơi bấm lại được, tránh báo nhầm "đã xử lý". Không hồi sinh
        # menu khi lỗi chính là do bấm đúp (chống bấm đúp vẫn hoạt động).
        if str(exc) != MENU_CONSUMED_MSG:
            _activate_menu(entry, message)
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("extra:"))
async def extra_action(callback: CallbackQuery, db: Database, games: GameManager) -> None:
    if not callback.message:
        return
    message = callback.message
    entry = _room(message, games)
    player = entry.room.find_player(callback.from_user.id) if entry else None
    if not entry or not player or not player.active:
        await callback.answer("Ván hoặc người chơi không còn.", show_alert=True)
        return
    if entry.room.current_player.user_id != callback.from_user.id:
        await callback.answer("Chỉ người đang tới lượt được thao tác.", show_alert=True)
        return
    if not _claim_active_menu(entry, message):
        await callback.answer("Nút này đã được xử lý. Hãy dùng /menu để mở lại menu.", show_alert=True)
        return
    await callback.answer()
    await _remove_menu(message)
    parts = callback.data.split(":")
    try:
        if parts[1] == "back":
            text = f"➡️ Lượt: {entry.room.current_player.name}"
        elif parts[1] == "demolish":
            async with entry.lock:
                text = demolish_house(entry.room, callback.from_user.id, int(parts[2]))
        elif parts[1] == "steal":
            async with entry.lock:
                text = steal_from_player(entry.room, callback.from_user.id, int(parts[2]))
        elif parts[1] == "wheel":
            async with entry.lock:
                text = gamble(entry.room, callback.from_user.id, "roulette", int(parts[2]))
        elif parts[1] == "taixiu":
            async with entry.lock:
                text = gamble(entry.room, callback.from_user.id, parts[2], int(parts[3]))
        elif parts[1] == "mortgage":
            async with entry.lock:
                text = mortgage_property(entry.room, callback.from_user.id, int(parts[2]))
        elif parts[1] == "unmortgage":
            async with entry.lock:
                text = unmortgage_property(entry.room, callback.from_user.id, int(parts[2]))
        elif parts[1] == "illegal":
            async with entry.lock:
                text = buy_illegal_item(entry.room, callback.from_user.id, parts[2])
        elif parts[1] == "sabotage":
            async with entry.lock:
                text = sabotage_house(entry.room, callback.from_user.id, int(parts[2]))
        elif parts[1] == "surrender" and parts[2] == "yes":
            async with entry.lock:
                result = surrender(entry.room, callback.from_user.id)
                ranking = final_rank(entry.room) if result.finished else None
                winner = entry.room.find_player(result.winner_id) if result.winner_id else None
            for uid, rank, assets in result.bankrupt:
                await db.add_reward(uid, message.chat.id, reward_for(rank, assets), False)
            if winner:
                await db.add_reward(
                    winner.user_id,
                    message.chat.id,
                    reward_for(1, asset_value(entry.room, winner)),
                    True,
                )
            text = result.text + (f"\n\n{ranking}" if ranking else "")
            if result.finished:
                await _send_board(message, entry.room, text)
                await games.remove(message.chat.id, _topic_id(message))
                return
        else:
            raise GameError("Thao tác không hợp lệ.")
        sent = await _send_board(message, entry.room, text, _turn_menu(entry.room))
        _activate_menu(entry, sent)
    except (ValueError, IndexError, GameError) as exc:
        sent = await _answer(message, str(exc), _turn_menu(entry.room))
        _activate_menu(entry, sent)


@router.message(Command("status"))
async def status(message: Message, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    entry = _room(message, games)
    if not entry:
        await _answer(message, "Không có ván trong topic này.")
        return
    if not entry.room.find_player(message.from_user.id):
        await _answer(message, "Chỉ người trong ván được xem trạng thái.")
        return
    async with entry.lock:
        text = status_text(entry.room)
    menu = _lobby_menu() if entry.room.phase is Phase.LOBBY else _turn_menu(entry.room)
    sent = await _send_board(message, entry.room, text, menu)
    _activate_menu(entry, sent)


@router.message(Command("cancel"))
async def cancel(message: Message, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    entry = _room(message, games)
    if not entry:
        await _answer(message, "Không có ván trong topic này.")
        return
    if entry.room.host_id != message.from_user.id:
        await _answer(message, "Chỉ chủ phòng được huỷ.")
        return
    await games.remove(message.chat.id, _topic_id(message))
    await _answer(message, "🗑 Đã huỷ ván.")


@router.message(Command("profile"))
async def profile(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    await _ensure(message, db)
    row = await db.profile(message.from_user.id, message.chat.id)
    bag = await db.inventory(message.from_user.id, message.chat.id)
    name, stars, wins, games_count, points = row
    items = "\n".join(f"• {item} ×{qty}" for item, qty in bag) or "Túi đồ trống"
    await _answer(
        message,
        f"👤 {name}\n⭐ {stars} · 🏆 {wins}/{games_count}\n"
        f"📈 {points} điểm mùa\n\n🎒 {items}",
    )


@router.message(Command("shop"))
async def shop(message: Message, games: GameManager) -> None:
    if _topic_allowed(message, games):
        await _answer(message, shop_text())


@router.message(Command("buy"))
async def buy(
    message: Message,
    command: CommandObject,
    db: Database,
    games: GameManager,
) -> None:
    if not _topic_allowed(message, games):
        return
    await _ensure(message, db)
    item_id = (command.args or "").strip().upper()
    item = ITEMS.get(item_id)
    if not item:
        await _answer(message, "Dùng /buy ITEM_ID — xem /shop")
        return
    ok = await db.buy_item(message.from_user.id, message.chat.id, item.item_id, item.cost)
    await _answer(message, f"✅ Đã mua {item.name} (-{item.cost}⭐)" if ok else "Không đủ ⭐.")


@router.message(Command("leaderboard"))
async def leaderboard(message: Message, db: Database, games: GameManager) -> None:
    if not _topic_allowed(message, games):
        return
    rows = await db.leaderboard(message.chat.id)
    lines = ["📊 BẢNG XẾP HẠNG"] + [
        f"{i}. {name} — {stars}⭐ · {wins}/{games_count}"
        for i, (name, stars, wins, games_count) in enumerate(rows, 1)
    ]
    await _answer(message, "\n".join(lines) if rows else "Chưa có dữ liệu.")


    sabotage_house,
