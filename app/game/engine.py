from __future__ import annotations

import random
from collections.abc import Callable

from app.game.models import GameRoom, Phase, Player, PlayerStatus, TileKind, TurnResult
from app.game.money import format_vnd

Roller = Callable[[], tuple[int, int]]

# Giá nhà theo nhóm màu, mô phỏng các mức 50/100/150/200 của Monopoly.
HOUSE_COSTS = {1: 500_000, 2: 500_000, 3: 1_000_000, 4: 1_000_000, 5: 1_500_000, 6: 2_000_000}
RENT_MULTIPLIERS = {1: 5, 2: 15, 3: 45, 4: 80, 5: 125}
MIN_CASH_RESERVE = 100_000


class GameError(ValueError):
    pass


def join_room(room: GameRoom, user_id: int, name: str) -> None:
    if room.phase is not Phase.LOBBY:
        raise GameError("Ván đã bắt đầu, không thể tham gia.")
    if room.find_player(user_id):
        raise GameError("Bạn đã ở trong phòng chờ.")
    if len(room.players) >= room.max_players:
        raise GameError(f"Phòng đã đủ {room.max_players} người.")
    room.players.append(Player(user_id=user_id, name=name, cash=room.starting_cash))


def start_room(room: GameRoom, actor_id: int) -> None:
    if actor_id != room.host_id:
        raise GameError("Chỉ chủ phòng được bắt đầu.")
    if room.phase is not Phase.LOBBY:
        raise GameError("Ván không còn ở phòng chờ.")
    if len(room.players) < room.min_players:
        raise GameError(f"Cần ít nhất {room.min_players} người.")
    room.phase = Phase.PLAYING
    room.turn_index = 0
    room.used_turn_actions.clear()
    assign_secret_missions(room)


def _consume_turn_action(room: GameRoom, _action: str, label: str) -> None:
    if "strategic" in room.used_turn_actions:
        raise GameError(
            f"Không thể dùng {label}: bạn đã thực hiện một hành động chiến thuật trong lượt này."
        )
    room.used_turn_actions.add("strategic")


def asset_value(room: GameRoom, player: Player) -> int:
    if player.final_assets is not None:
        return player.final_assets
    land = sum(
        room.board[index].price + room.board[index].houses * house_cost(room.board[index])
        for index in player.property_indexes
    )
    return max(player.cash, 0) + land


def mark_bankrupt(room: GameRoom, player: Player) -> tuple[int, int, int]:
    if player.status is PlayerStatus.BANKRUPT:
        return player.user_id, player.rank or len(room.players), player.final_assets or 0
    assets = asset_value(room, player)
    room.out_count += 1
    rank = len(room.players) - room.out_count + 1
    for index in player.property_indexes:
        room.board[index].owner_id = None
        room.board[index].houses = 0
        room.board[index].owner_landings = 0
        room.board[index].mortgaged = False
    player.property_indexes.clear()
    player.cash = 0
    player.status = PlayerStatus.BANKRUPT
    player.rank = rank
    player.final_assets = assets
    return player.user_id, rank, assets


def _finish_if_needed(room: GameRoom) -> int | None:
    active = room.active_players
    if len(active) == 1:
        room.phase = Phase.FINISHED
        active[0].rank = 1
        return active[0].user_id
    if not active:
        room.phase = Phase.FINISHED
    return None


def _rent(room: GameRoom, tile_index: int) -> int:
    tile = room.board[tile_index]
    if tile.mortgaged:
        return 0
    if tile.kind is TileKind.RAILROAD:
        count = sum(
            candidate.kind is TileKind.RAILROAD and candidate.owner_id == tile.owner_id
            for candidate in room.board
        )
        return 250_000 * count
    if tile.kind is TileKind.PROPERTY:
        if tile.houses:
            return tile.rent * RENT_MULTIPLIERS[tile.houses]
        if _owns_full_group(room, tile.owner_id or 0, tile.color_group):
            base = tile.rent * 2
        else:
            base = tile.rent
        if room.market_event == "growth":
            return base * 120 // 100
        if room.market_event == "recession":
            return base * 80 // 100
        return base
    return tile.rent


def house_cost(tile) -> int:
    """Giá xây theo nhóm màu như các bậc giá phổ biến của Monopoly."""
    return HOUSE_COSTS.get(tile.color_group, max(200_000, tile.price // 2))


def building_name(level: int) -> str:
    return "khách sạn" if level == 5 else f"nhà #{level}"


def mortgage_value(tile) -> int:
    return tile.price // 2


def unmortgage_cost(tile) -> int:
    value = mortgage_value(tile)
    return value + value // 10


def property_info(room: GameRoom, tile_index: int) -> str:
    if not 0 <= tile_index < len(room.board):
        raise GameError("Ô đất không hợp lệ.")
    tile = room.board[tile_index]
    owner = room.find_player(tile.owner_id) if tile.owner_id is not None else None
    lines = [f"📍 {tile.name}", f"Loại: {tile.kind.value}"]
    if tile.price:
        lines.append(f"Giá mua: {format_vnd(tile.price)}")
    if tile.kind is TileKind.PROPERTY:
        lines.append(f"Tiền thuê gốc: {format_vnd(tile.rent)}")
        lines.append(f"Trọn bộ màu (chưa xây): {format_vnd(tile.rent * 2)}")
        for level in range(1, 6):
            lines.append(
                f"{building_name(level).capitalize()}: {format_vnd(tile.rent * RENT_MULTIPLIERS[level])}"
            )
        lines.append(f"Giá xây mỗi cấp: {format_vnd(house_cost(tile))}")
        lines.append(f"Thế chấp: {format_vnd(mortgage_value(tile))}")
        lines.append(f"Chuộc thế chấp: {format_vnd(unmortgage_cost(tile))}")
        lines.append(f"Công trình hiện tại: {building_name(tile.houses) if tile.houses else 'chưa xây'}")
        lines.append(f"Số lần chủ ghé: {tile.owner_landings}")
    elif tile.kind is TileKind.RAILROAD:
        lines.append("Tiền thuê: 250K × số ga sở hữu")
        lines.append(f"Thế chấp: {format_vnd(mortgage_value(tile))}")
    elif tile.kind is TileKind.UTILITY:
        lines.append(f"Tiền thuê: {format_vnd(tile.rent)}")
        lines.append(f"Thế chấp: {format_vnd(mortgage_value(tile))}")
    elif tile.kind is TileKind.TAX:
        lines.append(f"Thuế: {format_vnd(tile.tax)}")
    if owner:
        lines.append(f"Chủ: {owner.name}{' · đã thế chấp' if tile.mortgaged else ''}")
    elif tile.kind in {TileKind.PROPERTY, TileKind.RAILROAD, TileKind.UTILITY}:
        lines.append("Chủ: ngân hàng")
    if tile.kind in {TileKind.PROPERTY, TileKind.RAILROAD, TileKind.UTILITY}:
        lines.append(f"Tiền thuê hiện tại: {format_vnd(_rent(room, tile_index))}")
    return "\n".join(lines)


def mortgageable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        return []
    result: list[int] = []
    for index in player.property_indexes:
        tile = room.board[index]
        if tile.owner_id != actor_id or tile.mortgaged or tile.houses > 0:
            continue
        if tile.kind in {TileKind.PROPERTY, TileKind.RAILROAD, TileKind.UTILITY}:
            result.append(index)
    return result


def unmortgageable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        return []
    return [
        index
        for index in player.property_indexes
        if room.board[index].owner_id == actor_id
        and room.board[index].mortgaged
        and player.cash >= unmortgage_cost(room.board[index])
    ]


def mortgage_property(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ thế chấp khi đang tới lượt.")
    if tile_index not in mortgageable_properties(room, actor_id):
        raise GameError("Đất này không thể thế chấp (cần phá hết nhà trước).")
    player = room.find_player(actor_id)
    assert player is not None
    tile = room.board[tile_index]
    _consume_turn_action(room, "mortgage", "Thế chấp")
    value = mortgage_value(tile)
    tile.mortgaged = True
    player.cash += value
    text = f"🏦 {player.name} thế chấp {tile.name} · nhận {format_vnd(value)}"
    room.log(text)
    return text


def unmortgage_property(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ chuộc thế chấp khi đang tới lượt.")
    if tile_index not in unmortgageable_properties(room, actor_id):
        raise GameError("Không thể chuộc đất này.")
    player = room.find_player(actor_id)
    assert player is not None
    tile = room.board[tile_index]
    _consume_turn_action(room, "unmortgage", "Chuộc thế chấp")
    cost = unmortgage_cost(tile)
    player.cash -= cost
    tile.mortgaged = False
    text = f"🔓 {player.name} chuộc {tile.name} · trả {format_vnd(cost)}"
    room.log(text)
    return text


def propose_trade(
    room: GameRoom,
    actor_id: int,
    target_id: int,
    offer_cash: int,
    request_cash: int,
    offer_tile: int | None,
    request_tile: int | None,
) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ đề xuất giao dịch khi đang tới lượt.")
    if room.pending_trade:
        raise GameError("Đang có giao dịch chờ xác nhận.")
    actor = room.find_player(actor_id)
    target = room.find_player(target_id)
    if not actor or not target or not target.active or target_id == actor_id:
        raise GameError("Đối tác giao dịch không hợp lệ.")
    if offer_cash < 0 or request_cash < 0:
        raise GameError("Số tiền giao dịch không hợp lệ.")
    if offer_cash and actor.cash < offer_cash:
        raise GameError("Bạn không đủ tiền để đề xuất.")
    if offer_tile is not None:
        tile = room.board[offer_tile]
        if tile.owner_id != actor_id or tile.houses > 0 or tile.mortgaged:
            raise GameError("Chỉ giao dịch đất không nhà và không thế chấp của bạn.")
    if request_tile is not None:
        tile = room.board[request_tile]
        if tile.owner_id != target_id or tile.houses > 0 or tile.mortgaged:
            raise GameError("Chỉ yêu cầu đất không nhà và không thế chấp của đối tác.")
    if not offer_cash and not request_cash and offer_tile is None and request_tile is None:
        raise GameError("Giao dịch trống.")
    _consume_turn_action(room, "trade", "Giao dịch")
    room.pending_trade = {
        "from_id": actor_id,
        "to_id": target_id,
        "offer_cash": offer_cash,
        "request_cash": request_cash,
        "offer_tile": offer_tile,
        "request_tile": request_tile,
    }
    parts = [f"🤝 {actor.name} đề xuất giao dịch với {target.name}:"]
    if offer_cash:
        parts.append(f"• Đưa {format_vnd(offer_cash)}")
    if offer_tile is not None:
        parts.append(f"• Đưa đất {room.board[offer_tile].name}")
    if request_cash:
        parts.append(f"• Xin {format_vnd(request_cash)}")
    if request_tile is not None:
        parts.append(f"• Xin đất {room.board[request_tile].name}")
    parts.append("Đối tác bấm Xác nhận hoặc Từ chối.")
    text = "\n".join(parts)
    room.log(text.splitlines()[0])
    return text


def respond_trade(room: GameRoom, actor_id: int, accept: bool) -> str:
    trade = room.pending_trade
    if not trade:
        raise GameError("Không có giao dịch đang chờ.")
    if actor_id != trade["to_id"]:
        raise GameError("Chỉ đối tác được xác nhận giao dịch.")
    seller = room.find_player(trade["from_id"])
    buyer = room.find_player(trade["to_id"])
    if not seller or not buyer or not seller.active or not buyer.active:
        room.pending_trade = None
        raise GameError("Một bên không còn trong ván.")
    if not accept:
        room.pending_trade = None
        text = f"❌ {buyer.name} từ chối giao dịch của {seller.name}."
        room.log(text)
        return text

    offer_cash = int(trade["offer_cash"])
    request_cash = int(trade["request_cash"])
    offer_tile = trade["offer_tile"]
    request_tile = trade["request_tile"]
    if seller.cash < offer_cash or buyer.cash < request_cash:
        room.pending_trade = None
        raise GameError("Một bên không còn đủ tiền để hoàn tất giao dịch.")
    if offer_tile is not None and room.board[offer_tile].owner_id != seller.user_id:
        room.pending_trade = None
        raise GameError("Đất đề xuất không còn thuộc người gửi.")
    if request_tile is not None and room.board[request_tile].owner_id != buyer.user_id:
        room.pending_trade = None
        raise GameError("Đất yêu cầu không còn thuộc đối tác.")

    seller.cash -= offer_cash
    buyer.cash += offer_cash
    buyer.cash -= request_cash
    seller.cash += request_cash
    if offer_tile is not None:
        tile = room.board[offer_tile]
        seller.property_indexes.remove(offer_tile)
        buyer.property_indexes.append(offer_tile)
        tile.owner_id = buyer.user_id
        tile.owner_landings = 0
    if request_tile is not None:
        tile = room.board[request_tile]
        buyer.property_indexes.remove(request_tile)
        seller.property_indexes.append(request_tile)
        tile.owner_id = seller.user_id
        tile.owner_landings = 0
    room.pending_trade = None
    text = f"✅ {buyer.name} chấp nhận giao dịch với {seller.name}."
    room.log(text)
    return text


def force_skip_turn(room: GameRoom) -> str:
    if room.phase is Phase.AWAITING_PURCHASE:
        text = decide_purchase(room, room.pending_player_id or room.current_player.user_id, False)
        note = f"⏰ Hết giờ — tự bỏ mua.\n{text}"
        room.log("⏰ Hết giờ — tự bỏ mua.")
        return note
    if room.phase is not Phase.PLAYING:
        raise GameError("Không có lượt để bỏ.")
    player = room.current_player
    if player.status is PlayerStatus.JAILED:
        result = _resolve_jail(room, player, (1, 2))
        note = f"⏰ Hết giờ trong tù.\n{result.text}"
        room.log("⏰ Hết giờ trong tù.")
        return note
    room.pending_trade = None
    room.advance_turn()
    text = f"⏰ Hết {player.name} — bỏ lượt.\n➡️ Lượt: {room.current_player.name}"
    room.log(f"⏰ Hết giờ lượt của {player.name}")
    return text


def recent_events(room: GameRoom, limit: int = 12) -> str:
    events = room.event_log[-limit:]
    if not events:
        return "📜 Chưa có nhật ký giao dịch."
    return "📜 NHẬT KÝ GẦN ĐÂY\n" + "\n".join(f"• {item}" for item in events)


def _owns_full_group(room: GameRoom, user_id: int, group: int | None) -> bool:
    if group is None:
        return False
    group_tiles = [tile for tile in room.board if tile.color_group == group]
    return bool(group_tiles) and all(tile.owner_id == user_id for tile in group_tiles)


def buildable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if (
        not player
        or player.status is not PlayerStatus.ACTIVE
        or room.phase is not Phase.PLAYING
        or room.current_player.user_id != actor_id
    ):
        return []
    index = player.position
    if index not in player.property_indexes:
        return []
    tile = room.board[index]
    if (
        tile.owner_id != actor_id
        or tile.kind is not TileKind.PROPERTY
        or tile.houses >= 5
        or tile.owner_landings < 2
        or tile.mortgaged
    ):
        return []
    if player.building_vouchers <= 0 and player.cash < house_cost(tile):
        return []
    return [index]


def build_house(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if room.phase is not Phase.PLAYING:
        raise GameError("Chỉ được xây nhà khi ván đang chơi.")
    if room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được xây nhà.")
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        raise GameError("Bạn không còn trong ván.")
    if tile_index not in buildable_properties(room, actor_id):
        raise GameError("Đất này chưa đủ điều kiện xây nhà.")
    tile = room.board[tile_index]
    cost = house_cost(tile)
    _consume_turn_action(room, "build", "Xây nhà")
    used_voucher = player.building_vouchers > 0
    if used_voucher:
        player.building_vouchers -= 1
    else:
        player.cash -= cost
    tile.houses += 1
    rent = _rent(room, tile_index)
    text = (
        f"{'🏨' if tile.houses == 5 else '🏠'} {player.name} xây {building_name(tile.houses)} tại {tile.name}\n"
        f"💸 Chi phí: {'Phiếu xây miễn phí' if used_voucher else format_vnd(cost)}"
        f" · Tiền thuê mới: {format_vnd(rent)}"
    )
    room.log(text.splitlines()[0])
    return text


def demolishable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if (
        not player
        or player.status is not PlayerStatus.ACTIVE
        or room.phase is not Phase.PLAYING
        or room.current_player.user_id != actor_id
    ):
        return []
    result: list[int] = []
    for index in player.property_indexes:
        tile = room.board[index]
        if tile.owner_id != actor_id or tile.kind is not TileKind.PROPERTY or tile.houses <= 0:
            continue
        result.append(index)
    return result


def demolish_house(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if tile_index not in demolishable_properties(room, actor_id):
        raise GameError("Bạn không có công trình để phá trên đất này.")
    player = room.find_player(actor_id)
    assert player is not None
    tile = room.board[tile_index]
    _consume_turn_action(room, "demolish", "Phá nhà")
    removed = building_name(tile.houses)
    refund = house_cost(tile) // 2
    tile.houses -= 1
    player.cash += refund
    return (
        f"🏚 {player.name} phá {removed} tại {tile.name}\n"
        f"💵 Thu hồi: {format_vnd(refund)} · Còn {building_name(tile.houses) if tile.houses else 'đất trống'}"
    )


def steal_from_player(
    room: GameRoom,
    actor_id: int,
    target_id: int,
    *,
    rng: random.Random | None = None,
) -> str:
    if room.safe_mode:
        raise GameError("Chế độ an toàn đang bật: trộm bị tắt.")
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được trộm.")
    thief = room.find_player(actor_id)
    target = room.find_player(target_id) if target_id else None
    if (
        not thief
        or thief.status is not PlayerStatus.ACTIVE
        or (target_id and (not target or not target.active or target_id == actor_id))
    ):
        raise GameError("Mục tiêu không hợp lệ.")
    if target_id == 0 and thief.bank_heist_used:
        raise GameError("Bạn đã dùng lượt trộm ngân hàng duy nhất trong ván này.")
    _consume_turn_action(room, "steal", "Trộm")
    if target_id == 0:
        thief.bank_heist_used = True
    rng = rng or random.Random()
    fee = max(thief.cash, 0) // 5
    thief.cash -= fee
    collateral_index = rng.choice(thief.property_indexes) if thief.property_indexes else None
    used_lockpick = thief.lockpicks > 0
    if used_lockpick:
        thief.lockpicks -= 1
    # Trộm người chơi: 10%; trộm ngân hàng: 5%.
    # Bộ phá khóa vẫn cộng thêm 15 điểm phần trăm.
    success_chance = (0.05 if target_id == 0 else 0.10) + (0.15 if used_lockpick else 0)
    if rng.random() < success_chance:
        thief.cash += fee
        if target_id == 0:
            reward = 50_000_000
            thief.cash += reward
            return (
                f"🏦 Đột nhập ngân hàng thành công! +{format_vnd(reward)}\n"
                f"✅ Hoàn lại phí trộm {format_vnd(fee)}"
            )
        assert target is not None
        percent = rng.randint(25, 75)
        amount = max(target.cash, 0) * percent // 100
        target.cash -= amount
        thief.cash += amount
        return (
            f"🥷 Trộm thành công {percent}% tiền của {target.name}: {format_vnd(amount)}\n"
            f"✅ Hoàn lại phí trộm {format_vnd(fee)}"
        )

    lost_land = ""
    if collateral_index is not None:
        tile = room.board[collateral_index]
        thief.property_indexes.remove(collateral_index)
        tile.owner_id = None
        tile.houses = 0
        tile.owner_landings = 0
        lost_land = f" và mất đất {tile.name}"
    if thief.getaway_cards > 0:
        thief.getaway_cards -= 1
        return (
            f"🚨 Trộm thất bại! Mất phí {format_vnd(fee)}{lost_land}.\n"
            "🚗 Thẻ tẩu thoát kích hoạt — không bị vào tù."
        )
    thief.status = PlayerStatus.JAILED
    thief.jail_turns_left = 3
    thief.doubles_streak = 0
    thief.position = _jail_index(room)
    room.advance_turn()
    return (
        f"🚨 Trộm thất bại! Mất phí {format_vnd(fee)}{lost_land} và bị bắt vào tù.\n"
        f"➡️ Lượt: {room.current_player.name}"
    )


def gamble(
    room: GameRoom,
    actor_id: int,
    game: str,
    stake: int,
    *,
    rng: random.Random | None = None,
) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được chơi trò may rủi.")
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        raise GameError("Không tìm thấy người chơi.")
    if stake <= 0 or player.cash - stake < MIN_CASH_RESERVE:
        raise GameError(
            f"Cược không hợp lệ; phải giữ lại ít nhất {format_vnd(MIN_CASH_RESERVE)}."
        )
    rng = rng or random.Random()
    if game == "roulette":
        outcome = rng.randint(1, 100)
        if outcome <= 55:
            change = -(stake // 2)
            result = f"LỖ 50%: {format_vnd(change)}"
        elif outcome <= 75:
            change = stake // 4
            result = f"THẮNG 25%: +{format_vnd(change)}"
        elif outcome <= 95:
            change = 0
            result = "HÒA VỐN"
        else:
            change = stake * 4
            result = f"THẮNG ĐẬM ×5: +{format_vnd(change)} lợi nhuận"
        player.cash += change
        return f"🎡 Vòng quay: {result}\n💰 Tiền hiện tại: {format_vnd(player.cash)}"
    if game not in {"tai", "xiu"}:
        raise GameError("Trò đỏ đen không hợp lệ.")
    dice = [rng.randint(1, 6) for _ in range(3)]
    total = sum(dice)
    is_triple = len(set(dice)) == 1
    actual = "tai" if total >= 11 else "xiu"
    win = not is_triple and game == actual
    player.cash += stake if win else -stake
    label = "TÀI" if actual == "tai" else "XỈU"
    outcome = "THẮNG" if win else "THUA"
    return (
        f"🎲 {dice[0]} + {dice[1]} + {dice[2]} = {total} · {label}"
        f"{' · BỘ BA' if is_triple else ''}\n{outcome} {format_vnd(stake)}"
        f" · {'+' if win else '-'}{format_vnd(stake)}"
        f" · Tiền hiện tại: {format_vnd(player.cash)}"
    )


ILLEGAL_ITEMS = {
    "lockpick": ("Bộ phá khóa", 1_000_000),
    "bomb": ("Bom phá nhà", 2_000_000),
    "getaway": ("Thẻ tẩu thoát", 1_500_000),
}


def buy_illegal_item(room: GameRoom, actor_id: int, item_id: str) -> str:
    if room.safe_mode:
        raise GameError("Chế độ an toàn đang bật: chợ đen bị tắt.")
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ mua ở chợ đen khi đang tới lượt.")
    player = room.find_player(actor_id)
    item = ILLEGAL_ITEMS.get(item_id)
    if not player or player.status is not PlayerStatus.ACTIVE or not item:
        raise GameError("Vật phẩm phi pháp không hợp lệ.")
    name, price = item
    if player.cash < price:
        raise GameError(f"Không đủ {format_vnd(price)} để mua {name}.")
    _consume_turn_action(room, "blackmarket", "Chợ đen")
    player.cash -= price
    if item_id == "lockpick":
        player.lockpicks += 1
    elif item_id == "bomb":
        player.demolition_bombs += 1
    else:
        player.getaway_cards += 1
    return f"🕶 Đã mua {name} với {format_vnd(price)}"


def sabotage_house(
    room: GameRoom,
    actor_id: int,
    target_id: int,
    *,
    rng: random.Random | None = None,
) -> str:
    if room.safe_mode:
        raise GameError("Chế độ an toàn đang bật: phá hoại bị tắt.")
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ phá hoại khi đang tới lượt.")
    actor = room.find_player(actor_id)
    target = room.find_player(target_id)
    if (
        not actor
        or actor.status is not PlayerStatus.ACTIVE
        or not target
        or target_id == actor_id
        or actor.demolition_bombs <= 0
    ):
        raise GameError("Không có bom hoặc mục tiêu không hợp lệ.")
    built = [index for index in target.property_indexes if room.board[index].houses > 0]
    if not built:
        raise GameError("Mục tiêu không có nhà hoặc khách sạn để phá.")
    _consume_turn_action(room, "sabotage", "Phá hoại")
    actor.demolition_bombs -= 1
    rng = rng or random.Random()
    if rng.random() >= 0.55:
        return "💥 Bom phát nổ sai chỗ — đã mất bom nhưng công trình không hư hại."
    index = rng.choice(built)
    if index in target.insured_tiles:
        target.insured_tiles.remove(index)
        return f"🛡 Bảo hiểm của {target.name} đã chặn vụ phá hoại tại {room.board[index].name}!"
    tile = room.board[index]
    old = building_name(tile.houses)
    tile.houses -= 1
    return f"💣 Đã phá {old} của {target.name} tại {tile.name}!"


def surrender(room: GameRoom, actor_id: int) -> TurnResult:
    if room.phase not in {Phase.PLAYING, Phase.AWAITING_PURCHASE}:
        raise GameError("Không có ván đang chơi để chịu thua.")
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        raise GameError("Bạn không còn trong ván.")
    was_current = room.current_player.user_id == actor_id
    user_id, rank, assets = mark_bankrupt(room, player)
    if room.pending_player_id == actor_id:
        room.pending_player_id = None
        room.pending_tile_index = None
        room.phase = Phase.PLAYING
    winner = _finish_if_needed(room)
    if room.phase is not Phase.FINISHED and was_current:
        room.advance_turn()
    text = f"🏳 {player.name} đã chịu thua và xếp hạng #{rank}."
    if winner is not None:
        text += f"\n🏆 {room.find_player(winner).name} chiến thắng!"
    return TurnResult(
        text,
        bankrupt=[(user_id, rank, assets)],
        winner_id=winner,
        finished=room.phase is Phase.FINISHED,
    )


def open_mystery_box(
    room: GameRoom,
    actor_id: int,
    *,
    rng: random.Random | None = None,
) -> str:
    """Mỗi người được mở một hộp bí ẩn trong cả ván, không mất lượt."""
    if room.phase is not Phase.PLAYING:
        raise GameError("Chỉ mở hộp khi ván đang chơi.")
    if room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được mở hộp.")
    player = room.find_player(actor_id)
    if not player or player.status is not PlayerStatus.ACTIVE:
        raise GameError("Bạn không còn trong ván.")
    if player.mystery_used:
        raise GameError("Bạn đã mở hộp bí ẩn trong ván này rồi.")

    _consume_turn_action(room, "mystery", "Hộp bí ẩn")
    player.mystery_used = True
    rng = rng or random.Random()
    event = rng.randint(1, 100)
    player.lucky_points += event
    if event <= 45:
        return "📦 Hộp bí ẩn trống — chúc may mắn lần sau!"
    if event <= 70:
        player.cash += 500_000
        return f"🎁 Nhặt được phong bao: +{format_vnd(500_000)}"
    if event <= 82:
        player.cash += 1_000_000
        return f"🎁 Thưởng may mắn: +{format_vnd(1_000_000)}"
    if event <= 90:
        player.rent_shields += 1
        return "🛡 Nhận Khiên miễn tiền thuê: chặn một lần trả tiền thuê!"
    if event <= 97:
        player.building_vouchers += 1
        return "🎟 Nhận Phiếu xây miễn phí — dùng khi đứng trên đất đủ hai lần ghé!"
    if event <= 99:
        player.position = 0
        player.cash += room.pass_go_salary
        return f"🚀 Dịch chuyển về Xuất phát và nhận {format_vnd(room.pass_go_salary)}"
    player.cash += 2_000_000
    return f"🎁 JACKPOT! {player.name} nhận {format_vnd(2_000_000)}"


def _jail_index(room: GameRoom) -> int:
    return next(
        (index for index, tile in enumerate(room.board) if tile.kind is TileKind.JAIL_VISIT),
        9,
    )


def _chance(room: GameRoom, player: Player, rng: random.Random) -> str:
    event = rng.randrange(6)
    if event == 0:
        player.cash += 1_000_000
        return f"Ngân hàng chuyển nhầm: +{format_vnd(1_000_000)}"
    if event == 1:
        player.cash -= 500_000
        return f"Phạt giao thông: -{format_vnd(500_000)}"
    if event == 2:
        player.cash += 500_000
        return f"Hoàn thuế: +{format_vnd(500_000)}"
    if event == 3:
        player.status = PlayerStatus.JAILED
        player.jail_turns_left = 3
        player.position = _jail_index(room)
        return "Bị bắt: vào tù"
    if event == 4:
        player.cash -= 750_000
        return f"Quyên góp: -{format_vnd(750_000)}"
    player.cash += 250_000
    return f"Nhặt được tiền: +{format_vnd(250_000)}"


def _resolve_jail(
    room: GameRoom, player: Player, dice: tuple[int, int]
) -> TurnResult:
    d1, d2 = dice
    lines = [f"🔒 {player.name} trong tù — xúc xắc: {d1} + {d2}"]
    bankrupt: list[tuple[int, int, int]] = []
    if d1 == d2:
        player.status = PlayerStatus.ACTIVE
        player.jail_turns_left = 0
        lines.append("🎉 Ra đôi — được ra tù, hết lượt.")
    elif player.jail_turns_left <= 1:
        player.cash -= 500_000
        player.status = PlayerStatus.ACTIVE
        player.jail_turns_left = 0
        lines.append(f"💵 Hết hạn tù — trả {format_vnd(500_000)} để ra, hết lượt.")
        if player.cash < 0:
            bankrupt.append(mark_bankrupt(room, player))
            lines.append("💥 Không đủ tiền — phá sản!")
    else:
        player.jail_turns_left -= 1
        lines.append(f"Còn {player.jail_turns_left} lượt trong tù.")

    winner = _finish_if_needed(room)
    if room.phase is not Phase.FINISHED:
        room.advance_turn()
    return TurnResult(
        "\n".join(lines),
        bankrupt=bankrupt,
        winner_id=winner,
        finished=room.phase is Phase.FINISHED,
    )


def roll_turn(
    room: GameRoom,
    actor_id: int,
    *,
    rng: random.Random | None = None,
    roller: Roller | None = None,
) -> TurnResult:
    if room.phase is Phase.AWAITING_PURCHASE:
        raise GameError("Đang chờ quyết định Mua/Bỏ qua.")
    if room.phase is not Phase.PLAYING:
        raise GameError("Không có ván đang chơi.")
    player = room.current_player
    if player.user_id != actor_id:
        raise GameError(f"Chưa tới lượt bạn. Đang tới lượt {player.name}.")
    if not player.active:
        raise GameError("Bạn đã ra ngoài.")
    room.turns_played += 1
    if room.turns_played in {15, 30, 45}:
        room.market_event = "growth" if room.turns_played in {15, 45} else "recession"
        room.market_event_until = room.turns_played + 3
        room.log("📈 Thị trường tăng trưởng" if room.market_event == "growth" else "📉 Thị trường suy thoái")
    if room.market_event and room.turns_played > room.market_event_until:
        room.market_event = ""

    rng = rng or random.Random()
    d1, d2 = roller() if roller else (rng.randint(1, 6), rng.randint(1, 6))
    if player.status is PlayerStatus.JAILED:
        return _resolve_jail(room, player, (d1, d2))

    total = d1 + d2
    is_double = d1 == d2
    lines = [f"🎲 {player.name}: {d1} + {d2} = {total}"]
    player.doubles_streak = player.doubles_streak + 1 if is_double else 0
    if player.doubles_streak >= 3:
        player.doubles_streak = 0
        player.status = PlayerStatus.JAILED
        player.jail_turns_left = 3
        player.position = _jail_index(room)
        room.advance_turn()
        return TurnResult("\n".join([*lines, "🚨 Ba lần xúc xắc đôi — vào tù!"]))

    destination = player.position + total
    if destination >= len(room.board):
        salary = room.pass_go_salary
        player.cash += salary
        mission = _mission_progress(room, player, "go")
        lines.append(f"🏁 Qua Xuất phát: +{format_vnd(salary)}")
        if mission:
            lines.append(mission)
        if len(player.property_indexes) >= 5:
            levy = salary // 10
            player.cash -= levy
            room.parking_fund += levy
            lines.append(f"🏛 Thuế chống độc quyền: -{format_vnd(levy)} vào quỹ bãi đỗ")
    player.position = destination % len(room.board)
    tile_index = player.position
    tile = room.board[tile_index]
    lines.append(f"📍 Đến: {tile.name}")
    bankrupt: list[tuple[int, int, int]] = []

    if tile.kind in {TileKind.GO, TileKind.JAIL_VISIT}:
        lines.append("Không có hiệu ứng.")
    elif tile.kind is TileKind.FREE_PARKING:
        prize = room.parking_fund
        player.cash += prize
        room.parking_fund = 0
        lines.append(f"🅿 Nhận quỹ bãi đỗ: +{format_vnd(prize)}")
    elif tile.kind is TileKind.TAX:
        player.cash -= tile.tax
        room.parking_fund += tile.tax
        lines.append(f"💸 Đóng thuế: -{format_vnd(tile.tax)} vào quỹ bãi đỗ")
    elif tile.kind is TileKind.GO_TO_JAIL:
        player.status = PlayerStatus.JAILED
        player.jail_turns_left = 3
        player.doubles_streak = 0
        player.position = _jail_index(room)
        lines.append("🚔 Vào tù!")
    elif tile.kind is TileKind.CHANCE:
        lines.append(f"🃏 {_chance(room, player, rng)}")
    elif tile.kind in {TileKind.PROPERTY, TileKind.RAILROAD, TileKind.UTILITY}:
        if tile.owner_id is None:
            if player.cash >= tile.price:
                room.phase = Phase.AWAITING_PURCHASE
                room.pending_player_id = player.user_id
                room.pending_tile_index = tile_index
                lines.append(
                    f"🏘 Chưa có chủ — giá {format_vnd(tile.price)} "
                    f"(bạn có {format_vnd(player.cash)})"
                )
                return TurnResult("\n".join(lines), awaiting_purchase=True)
            lines.append("Không đủ tiền mua — tự động bỏ qua.")
        elif tile.owner_id == player.user_id:
            tile.owner_landings += 1
            lines.append(f"Đây là tài sản của bạn · lần ghé #{tile.owner_landings}.")
            if (
                tile.kind is TileKind.PROPERTY
                and tile.owner_landings >= 2
                and tile.houses < 5
            ):
                lines.append("🏠 Từ lượt kế tiếp, bạn có thể xây khi vẫn đứng tại đây.")
        else:
            owner = room.find_player(tile.owner_id)
            if tile.mortgaged:
                lines.append("Đất đang thế chấp — không thu tiền thuê.")
            else:
                rent = _rent(room, tile_index)
                if player.rent_shields > 0:
                    player.rent_shields -= 1
                    lines.append(f"🛡 Khiên kích hoạt — không phải trả {format_vnd(rent)} tiền thuê!")
                else:
                    player.cash -= rent
                    if owner and owner.active:
                        owner.cash += rent
                        owner.rent_collected += rent
                        mission = _mission_progress(room, owner, "rent", rent)
                        if mission:
                            lines.append(mission)
                    lines.append(
                        f"💰 Trả {format_vnd(rent)} tiền thuê cho "
                        f"{owner.name if owner else 'ngân hàng'}."
                    )
                    room.log(f"💰 {player.name} trả thuê {format_vnd(rent)} cho {owner.name if owner else 'ngân hàng'}")

    if player.cash < 0 and player.active:
        user_id, rank, assets = mark_bankrupt(room, player)
        bankrupt.append((user_id, rank, assets))
        lines.append(f"💥 Phá sản — hạng #{rank}!")

    winner = _finish_if_needed(room)
    if winner is not None:
        lines.append(f"🏆 {room.find_player(winner).name} chiến thắng!")
    elif room.phase is not Phase.FINISHED:
        extra = is_double and player.active and player.status is not PlayerStatus.JAILED
        if extra:
            lines.append("🎯 Xúc xắc đôi — được đi thêm lượt!")
        else:
            room.advance_turn()

    return TurnResult(
        "\n".join(lines),
        bankrupt=bankrupt,
        winner_id=winner,
        finished=room.phase is Phase.FINISHED,
    )


def decide_purchase(room: GameRoom, actor_id: int, buy: bool) -> str:
    if room.phase is not Phase.AWAITING_PURCHASE:
        raise GameError("Không có quyết định mua đang chờ.")
    if actor_id != room.pending_player_id:
        raise GameError("Không phải quyết định của bạn.")
    assert room.pending_tile_index is not None
    tile_index = room.pending_tile_index
    tile = room.board[tile_index]
    player = room.find_player(actor_id)
    if player is None:
        raise GameError("Không tìm thấy người chơi.")

    if buy:
        if tile.owner_id is not None:
            raise GameError("Tài sản đã có chủ.")
        if player.cash < tile.price:
            raise GameError("Không đủ tiền mua.")
        player.cash -= tile.price
        player.property_indexes.append(tile_index)
        tile.owner_id = player.user_id
        tile.owner_landings = 1
        text = f"🛒 {player.name} mua {tile.name} với {format_vnd(tile.price)}"
        mission = _mission_progress(room, player, "lands")
        if mission:
            text += f"\n{mission}"
        room.log(text)
    else:
        text = f"⏭️ {player.name} bỏ qua {tile.name}"
        room.log(text)

    room.phase = Phase.PLAYING
    room.pending_player_id = None
    room.pending_tile_index = None
    if player.doubles_streak > 0 and player.active:
        return f"{text}\n🎯 Tiếp tục lượt do xúc xắc đôi!"
    room.advance_turn()
    return f"{text}\n➡️ Lượt: {room.current_player.name}"

# ===== Chế độ mở rộng: sự kiện, nhiệm vụ, bảo hiểm và quỹ chung =====
MISSION_TEXT = {
    "lands": "Mua 3 khu đất",
    "rent": "Thu tổng cộng 2 triệu tiền thuê",
    "houses": "Xây 2 cấp nhà",
    "go": "Đi qua Xuất phát 3 lần",
}


def assign_secret_missions(room: GameRoom) -> None:
    choices = list(MISSION_TEXT)
    for pos, player in enumerate(room.players):
        player.secret_mission = choices[pos % len(choices)]
        player.mission_progress = 0
        player.mission_done = False


def _mission_progress(room: GameRoom, player: Player, key: str, amount: int = 1) -> str | None:
    if getattr(player, "mission_done", False) or getattr(player, "secret_mission", "") != key:
        return None
    player.mission_progress = getattr(player, "mission_progress", 0) + amount
    targets = {"lands": 3, "rent": 2_000_000, "houses": 2, "go": 3}
    if player.mission_progress >= targets[key]:
        player.mission_done = True
        player.cash += 1_000_000
        return f"🎯 {player.name} hoàn thành nhiệm vụ bí mật “{MISSION_TEXT[key]}” · +{format_vnd(1_000_000)}"
    return None


def buy_insurance(room: GameRoom, actor_id: int) -> str:
    player = room.find_player(actor_id)
    if room.phase is not Phase.PLAYING or not player or player.status is not PlayerStatus.ACTIVE:
        raise GameError("Chỉ mua bảo hiểm khi đang tới lượt và không ở tù.")
    index = player.position
    if index not in player.property_indexes:
        raise GameError("Bạn phải đứng trên khu đất của mình để mua bảo hiểm.")
    if index in player.insured_tiles:
        raise GameError("Khu đất này đã có bảo hiểm.")
    cost = max(200_000, room.board[index].price // 10)
    if player.cash < cost:
        raise GameError("Không đủ tiền mua bảo hiểm.")
    _consume_turn_action(room, "insurance", "Bảo hiểm")
    player.cash -= cost
    player.insured_tiles.add(index)
    return f"🛡 Đã bảo hiểm {room.board[index].name} với phí {format_vnd(cost)}. Lần phá hoại đầu tiên sẽ được chặn."


def pay_bail(room: GameRoom, actor_id: int) -> str:
    player = room.find_player(actor_id)
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chưa tới lượt bạn.")
    if not player or player.status is not PlayerStatus.JAILED:
        raise GameError("Bạn không ở trong tù.")
    fee = 500_000
    if player.cash < fee:
        raise GameError("Không đủ tiền nộp phạt ra tù.")
    player.cash -= fee
    player.status = PlayerStatus.ACTIVE
    player.jail_turns_left = 0
    room.advance_turn()
    return f"🔓 {player.name} nộp {format_vnd(fee)} và ra tù. ➡️ Lượt: {room.current_player.name}"


def final_stats(room: GameRoom) -> str:
    if not room.players:
        return ""
    richest_rent = max(room.players, key=lambda p: getattr(p, "rent_collected", 0))
    most_lands = max(room.players, key=lambda p: len(p.property_indexes))
    most_lucky = max(room.players, key=lambda p: getattr(p, "lucky_points", 0))
    return (
        "\n\n📊 DANH HIỆU CUỐI TRẬN"
        f"\n💰 Đại gia tiền thuê: {richest_rent.name}"
        f"\n🏘 Nhà đầu tư: {most_lands.name}"
        f"\n🍀 May mắn: {most_lucky.name}"
    )
