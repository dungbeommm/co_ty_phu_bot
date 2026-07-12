from app.game.engine import asset_value
from app.game.models import GameRoom, PlayerStatus
from app.game.money import format_vnd


def lobby_text(room: GameRoom) -> str:
    players = "\n".join(f"{i}. {p.name}" for i, p in enumerate(room.players, 1))
    return f"🕹 PHÒNG CHỜ ({len(room.players)}/{room.max_players})\n{players}\n\nChủ phòng dùng /startgame"


def status_text(room: GameRoom) -> str:
    lines = [f"📋 TRẠNG THÁI\n➡️ Lượt: {room.current_player.name}"]
    for p in room.players:
        icon = "💥" if p.status is PlayerStatus.BANKRUPT else "🔒" if p.status is PlayerStatus.JAILED else "✅"
        lines.append(
            f"{icon} {p.name}: {format_vnd(p.cash)} · "
            f"{len(p.property_indexes)} đất · ô {p.position}"
        )
    return "\n".join(lines)


def final_rank(room: GameRoom) -> str:
    players = sorted(room.players, key=lambda p: p.rank or 999)
    lines = ["🏆 BẢNG XẾP HẠNG"]
    for p in players:
        rank = p.rank or 1
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "•")
        lines.append(
            f"{medal} #{rank} {p.name} · tài sản {format_vnd(asset_value(room, p))}"
        )
    return "\n".join(lines)


def reward_for(rank: int, assets: int) -> int:
    return 10 + assets // 1_000_000 + {1: 100, 2: 50, 3: 30}.get(rank, 10)
