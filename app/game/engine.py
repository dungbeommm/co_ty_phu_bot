from __future__ import annotations

import random
from collections.abc import Callable

from app.game.models import GameRoom, Phase, Player, PlayerStatus, TileKind, TurnResult
from app.game.money import format_vnd

Roller = Callable[[], tuple[int, int]]


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
    land = sum(room.board[index].price for index in player.property_indexes)
    return max(player.cash, 0) + land


def mark_bankrupt(room: GameRoom, player: Player) -> tuple[int, int, int]:
    if player.status is PlayerStatus.BANKRUPT:
        return player.user_id, player.rank or len(room.players), player.final_assets or 0
    assets = asset_value(room, player)
    room.out_count += 1
    rank = len(room.players) - room.out_count + 1
    for index in player.property_indexes:
        room.board[index].owner_id = None
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
    return tile.rent


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
