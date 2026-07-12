from __future__ import annotations

import json
from typing import Any

from app.game.board import create_board
from app.game.models import GameRoom, Phase, Player, PlayerStatus, Tile, TileKind


def room_to_dict(room: GameRoom) -> dict[str, Any]:
    return {
        "chat_id": room.chat_id,
        "host_id": room.host_id,
        "topic_id": room.topic_id,
        "starting_cash": room.starting_cash,
        "pass_go_salary": room.pass_go_salary,
        "min_players": room.min_players,
        "max_players": room.max_players,
        "phase": room.phase.value,
        "turn_index": room.turn_index,
        "pending_tile_index": room.pending_tile_index,
        "pending_player_id": room.pending_player_id,
        "out_count": room.out_count,
        "used_turn_actions": sorted(room.used_turn_actions),
        "event_log": list(room.event_log[-40:]),
        "turn_deadline": room.turn_deadline,
        "pending_trade": room.pending_trade,
        "parking_fund": room.parking_fund,
        "market_event": room.market_event,
        "market_event_until": room.market_event_until,
        "safe_mode": room.safe_mode,
        "turns_played": room.turns_played,
        "max_turns": room.max_turns,
        "players": [
            {
                "user_id": p.user_id,
                "name": p.name,
                "cash": p.cash,
                "position": p.position,
                "property_indexes": list(p.property_indexes),
                "status": p.status.value,
                "jail_turns_left": p.jail_turns_left,
                "doubles_streak": p.doubles_streak,
                "rank": p.rank,
                "final_assets": p.final_assets,
                "mystery_used": p.mystery_used,
                "rent_shields": p.rent_shields,
                "lockpicks": p.lockpicks,
                "demolition_bombs": p.demolition_bombs,
                "getaway_cards": p.getaway_cards,
                "building_vouchers": p.building_vouchers,
                "bank_heist_used": p.bank_heist_used,
                "secret_mission": p.secret_mission,
                "mission_progress": p.mission_progress,
                "mission_done": p.mission_done,
                "insured_tiles": sorted(p.insured_tiles),
                "rent_collected": p.rent_collected,
                "lucky_points": p.lucky_points,
            }
            for p in room.players
        ],
        "board": [
            {
                "name": t.name,
                "kind": t.kind.value,
                "price": t.price,
                "rent": t.rent,
                "tax": t.tax,
                "color_group": t.color_group,
                "owner_id": t.owner_id,
                "houses": t.houses,
                "owner_landings": t.owner_landings,
                "mortgaged": t.mortgaged,
            }
            for t in room.board
        ],
    }


def room_from_dict(data: dict[str, Any]) -> GameRoom:
    board_data = data.get("board") or []
    if board_data:
        board = [
            Tile(
                name=item["name"],
                kind=TileKind(item["kind"]),
                price=int(item.get("price", 0)),
                rent=int(item.get("rent", 0)),
                tax=int(item.get("tax", 0)),
                color_group=item.get("color_group"),
                owner_id=item.get("owner_id"),
                houses=int(item.get("houses", 0)),
                owner_landings=int(item.get("owner_landings", 0)),
                mortgaged=bool(item.get("mortgaged", False)),
            )
            for item in board_data
        ]
    else:
        board = create_board()

    players = [
        Player(
            user_id=int(item["user_id"]),
            name=item["name"],
            cash=int(item["cash"]),
            position=int(item.get("position", 0)),
            property_indexes=list(item.get("property_indexes", [])),
            status=PlayerStatus(item.get("status", PlayerStatus.ACTIVE.value)),
            jail_turns_left=int(item.get("jail_turns_left", 0)),
            doubles_streak=int(item.get("doubles_streak", 0)),
            rank=item.get("rank"),
            final_assets=item.get("final_assets"),
            mystery_used=bool(item.get("mystery_used", False)),
            rent_shields=int(item.get("rent_shields", 0)),
            lockpicks=int(item.get("lockpicks", 0)),
            demolition_bombs=int(item.get("demolition_bombs", 0)),
            getaway_cards=int(item.get("getaway_cards", 0)),
            building_vouchers=int(item.get("building_vouchers", 0)),
            bank_heist_used=bool(item.get("bank_heist_used", False)),
            secret_mission=str(item.get("secret_mission", "")),
            mission_progress=int(item.get("mission_progress", 0)),
            mission_done=bool(item.get("mission_done", False)),
            insured_tiles=set(item.get("insured_tiles", [])),
            rent_collected=int(item.get("rent_collected", 0)),
            lucky_points=int(item.get("lucky_points", 0)),
        )
        for item in data.get("players", [])
    ]

    return GameRoom(
        chat_id=int(data["chat_id"]),
        host_id=int(data["host_id"]),
        players=players,
        board=board,
        starting_cash=int(data.get("starting_cash", 15_000_000)),
        pass_go_salary=int(data.get("pass_go_salary", 2_000_000)),
        min_players=int(data.get("min_players", 2)),
        max_players=int(data.get("max_players", 6)),
        topic_id=data.get("topic_id"),
        phase=Phase(data.get("phase", Phase.LOBBY.value)),
        turn_index=int(data.get("turn_index", 0)),
        pending_tile_index=data.get("pending_tile_index"),
        pending_player_id=data.get("pending_player_id"),
        out_count=int(data.get("out_count", 0)),
        used_turn_actions=set(data.get("used_turn_actions", [])),
        event_log=list(data.get("event_log", [])),
        turn_deadline=data.get("turn_deadline"),
        pending_trade=data.get("pending_trade"),
        parking_fund=int(data.get("parking_fund", 0)),
        market_event=str(data.get("market_event", "")),
        market_event_until=int(data.get("market_event_until", 0)),
        safe_mode=bool(data.get("safe_mode", False)),
        turns_played=int(data.get("turns_played", 0)),
        max_turns=int(data.get("max_turns", 50)),
    )


def dumps_room(room: GameRoom) -> str:
    return json.dumps(room_to_dict(room), ensure_ascii=False)


def loads_room(raw: str) -> GameRoom:
    return room_from_dict(json.loads(raw))
