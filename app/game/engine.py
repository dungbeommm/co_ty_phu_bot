from __future__ import annotations

import random
from collections.abc import Callable

from app.game.models import GameRoom, Phase, Player, PlayerStatus, TileKind, TurnResult
from app.game.money import format_vnd

Roller = Callable[[], tuple[int, int]]

# Giá nhà theo nhóm màu, mô phỏng các mức 50/100/150/200 của Monopoly.
HOUSE_COSTS = {1: 500_000, 2: 500_000, 3: 1_000_000, 4: 1_000_000, 5: 1_500_000, 6: 2_000_000}
RENT_MULTIPLIERS = {1: 5, 2: 15, 3: 45, 4: 80, 5: 125}


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
            return tile.rent * 2
    return tile.rent


def house_cost(tile) -> int:
    """Giá xây theo nhóm màu như các bậc giá phổ biến của Monopoly."""
    return HOUSE_COSTS.get(tile.color_group, max(200_000, tile.price // 2))


def building_name(level: int) -> str:
    return "khách sạn" if level == 5 else f"nhà #{level}"


def _owns_full_group(room: GameRoom, user_id: int, group: int | None) -> bool:
    if group is None:
        return False
    group_tiles = [tile for tile in room.board if tile.color_group == group]
    return bool(group_tiles) and all(tile.owner_id == user_id for tile in group_tiles)


def buildable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if not player or room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        return []
    result: list[int] = []
    for index in player.property_indexes:
        tile = room.board[index]
        if tile.kind is not TileKind.PROPERTY or tile.houses >= 5:
            continue
        if player.cash < house_cost(tile):
            continue
        result.append(index)
    return result


def build_house(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if room.phase is not Phase.PLAYING:
        raise GameError("Chỉ được xây nhà khi ván đang chơi.")
    if room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được xây nhà.")
    player = room.find_player(actor_id)
    if not player or not player.active:
        raise GameError("Bạn không còn trong ván.")
    if tile_index not in buildable_properties(room, actor_id):
        raise GameError("Đất này chưa đủ điều kiện xây nhà.")
    tile = room.board[tile_index]
    cost = house_cost(tile)
    player.cash -= cost
    tile.houses += 1
    rent = _rent(room, tile_index)
    return (
        f"{'🏨' if tile.houses == 5 else '🏠'} {player.name} xây {building_name(tile.houses)} tại {tile.name}\n"
        f"💸 Chi phí: {format_vnd(cost)} · Tiền thuê mới: {format_vnd(rent)}"
    )


def demolishable_properties(room: GameRoom, actor_id: int) -> list[int]:
    player = room.find_player(actor_id)
    if not player or room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        return []
    result: list[int] = []
    for index in player.property_indexes:
        tile = room.board[index]
        if tile.kind is not TileKind.PROPERTY or tile.houses <= 0:
            continue
        result.append(index)
    return result


def demolish_house(room: GameRoom, actor_id: int, tile_index: int) -> str:
    if tile_index not in demolishable_properties(room, actor_id):
        raise GameError("Bạn không có công trình để phá trên đất này.")
    player = room.find_player(actor_id)
    assert player is not None
    tile = room.board[tile_index]
    refund = house_cost(tile) // 2
    tile.houses -= 1
    player.cash += refund
    return (
        f"🏚 {player.name} phá một nhà tại {tile.name}\n"
        f"💵 Thu hồi: {format_vnd(refund)} · Còn {building_name(tile.houses) if tile.houses else 'đất trống'}"
    )


def steal_from_player(
    room: GameRoom,
    actor_id: int,
    target_id: int,
    *,
    rng: random.Random | None = None,
) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được trộm.")
    thief = room.find_player(actor_id)
    target = room.find_player(target_id) if target_id else None
    if not thief or (target_id and (not target or not target.active or target_id == actor_id)):
        raise GameError("Mục tiêu không hợp lệ.")
    rng = rng or random.Random()
    fee = max(thief.cash, 0) // 5
    thief.cash -= fee
    collateral_index = rng.choice(thief.property_indexes) if thief.property_indexes else None
    used_lockpick = thief.lockpicks > 0
    if used_lockpick:
        thief.lockpicks -= 1
    success_chance = (0.15 if target_id == 0 else 0.30) + (0.15 if used_lockpick else 0)
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
        lost_land = f" và mất đất {tile.name}"
    if thief.getaway_cards > 0:
        thief.getaway_cards -= 1
        return (
            f"🚨 Trộm thất bại! Mất phí {format_vnd(fee)}{lost_land}.\n"
            "🚗 Thẻ tẩu thoát kích hoạt — không bị vào tù."
        )
    thief.status = PlayerStatus.JAILED
    thief.jail_turns_left = 3
    thief.position = _jail_index(room)
    return f"🚨 Trộm thất bại! Mất phí {format_vnd(fee)}{lost_land} và bị bắt vào tù."


def gamble(
    room: GameRoom,
    actor_id: int,
    game: str,
    stake: int,
    *,
    rng: random.Random | None = None,
) -> str:
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ người đang tới lượt được chơi đỏ đen.")
    player = room.find_player(actor_id)
    if not player:
        raise GameError("Không tìm thấy người chơi.")
    if stake <= 0 or player.cash < stake:
        raise GameError("Số tiền cược không hợp lệ hoặc vượt quá tiền hiện có.")
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
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ mua ở chợ đen khi đang tới lượt.")
    player = room.find_player(actor_id)
    item = ILLEGAL_ITEMS.get(item_id)
    if not player or not item:
        raise GameError("Vật phẩm phi pháp không hợp lệ.")
    name, price = item
    if player.cash < price:
        raise GameError(f"Không đủ {format_vnd(price)} để mua {name}.")
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
    if room.phase is not Phase.PLAYING or room.current_player.user_id != actor_id:
        raise GameError("Chỉ phá hoại khi đang tới lượt.")
    actor = room.find_player(actor_id)
    target = room.find_player(target_id)
    if not actor or not target or target_id == actor_id or actor.demolition_bombs <= 0:
        raise GameError("Không có bom hoặc mục tiêu không hợp lệ.")
    built = [index for index in target.property_indexes if room.board[index].houses > 0]
    if not built:
        raise GameError("Mục tiêu không có nhà hoặc khách sạn để phá.")
    actor.demolition_bombs -= 1
    rng = rng or random.Random()
    if rng.random() >= 0.55:
        return "💥 Bom phát nổ sai chỗ — đã mất bom nhưng công trình không hư hại."
    index = rng.choice(built)
    tile = room.board[index]
    old = building_name(tile.houses)
    tile.houses -= 1
    return f"💣 Đã phá {old} của {target.name} tại {tile.name}!"


def surrender(room: GameRoom, actor_id: int) -> TurnResult:
    if room.phase not in {Phase.PLAYING, Phase.AWAITING_PURCHASE}:
        raise GameError("Không có ván đang chơi để chịu thua.")
    player = room.find_player(actor_id)
    if not player or not player.active:
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
    if not player or not player.active:
        raise GameError("Bạn không còn trong ván.")
    if player.mystery_used:
        raise GameError("Bạn đã mở hộp bí ẩn trong ván này rồi.")

    player.mystery_used = True
    rng = rng or random.Random()
    event = rng.randint(1, 100)
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
        indexes = buildable_properties(room, actor_id)
        if indexes:
            tile = room.board[rng.choice(indexes)]
            tile.houses += 1
            return f"🏠 Trúng nhà miễn phí tại {tile.name}!"
        player.cash += 250_000
        return f"🎁 Chưa có đất xây nhà — đổi quà thành {format_vnd(250_000)}"
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
        player.cash += room.pass_go_salary
        lines.append(f"🏁 Qua Xuất phát: +{format_vnd(room.pass_go_salary)}")
    player.position = destination % len(room.board)
    tile_index = player.position
    tile = room.board[tile_index]
    lines.append(f"📍 Đến: {tile.name}")
    bankrupt: list[tuple[int, int, int]] = []

    if tile.kind in {TileKind.GO, TileKind.JAIL_VISIT, TileKind.FREE_PARKING}:
        lines.append("Không có hiệu ứng.")
    elif tile.kind is TileKind.TAX:
        player.cash -= tile.tax
        lines.append(f"💸 Đóng thuế: -{format_vnd(tile.tax)}")
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
            lines.append("Đây là tài sản của bạn.")
        else:
            owner = room.find_player(tile.owner_id)
            rent = _rent(room, tile_index)
            if player.rent_shields > 0:
                player.rent_shields -= 1
                lines.append(f"🛡 Khiên kích hoạt — không phải trả {format_vnd(rent)} tiền thuê!")
            else:
                player.cash -= rent
                if owner and owner.active:
                    owner.cash += rent
                lines.append(
                    f"💰 Trả {format_vnd(rent)} tiền thuê cho "
                    f"{owner.name if owner else 'ngân hàng'}."
                )

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
        text = f"🛒 {player.name} mua {tile.name} với {format_vnd(tile.price)}"
    else:
        text = f"⏭️ {player.name} bỏ qua {tile.name}"

    room.phase = Phase.PLAYING
    room.pending_player_id = None
    room.pending_tile_index = None
    if player.doubles_streak > 0 and player.active:
        return f"{text}\n🎯 Tiếp tục lượt do xúc xắc đôi!"
    room.advance_turn()
    return f"{text}\n➡️ Lượt: {room.current_player.name}"
