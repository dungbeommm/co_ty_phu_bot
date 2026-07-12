from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"
    AWAITING_PURCHASE = "awaiting_purchase"
    FINISHED = "finished"


class PlayerStatus(str, Enum):
    ACTIVE = "active"
    JAILED = "jailed"
    BANKRUPT = "bankrupt"


class TileKind(str, Enum):
    GO = "go"
    PROPERTY = "property"
    RAILROAD = "railroad"
    UTILITY = "utility"
    CHANCE = "chance"
    TAX = "tax"
    JAIL_VISIT = "jail_visit"
    GO_TO_JAIL = "go_to_jail"
    FREE_PARKING = "free_parking"


@dataclass(slots=True)
class Tile:
    name: str
    kind: TileKind
    price: int = 0
    rent: int = 0
    tax: int = 0
    color_group: int | None = None
    owner_id: int | None = None
    houses: int = 0


@dataclass(slots=True)
class Player:
    user_id: int
    name: str
    cash: int
    position: int = 0
    property_indexes: list[int] = field(default_factory=list)
    status: PlayerStatus = PlayerStatus.ACTIVE
    jail_turns_left: int = 0
    doubles_streak: int = 0
    rank: int | None = None
    final_assets: int | None = None
    mystery_used: bool = False
    rent_shields: int = 0
    lockpicks: int = 0
    demolition_bombs: int = 0
    getaway_cards: int = 0

    @property
    def active(self) -> bool:
        return self.status is not PlayerStatus.BANKRUPT


@dataclass(slots=True)
class GameRoom:
    chat_id: int
    host_id: int
    players: list[Player]
    board: list[Tile]
    starting_cash: int
    pass_go_salary: int
    min_players: int
    max_players: int
    topic_id: int | None = None
    phase: Phase = Phase.LOBBY
    turn_index: int = 0
    pending_tile_index: int | None = None
    pending_player_id: int | None = None
    out_count: int = 0

    @property
    def current_player(self) -> Player:
        return self.players[self.turn_index]

    @property
    def active_players(self) -> list[Player]:
        return [player for player in self.players if player.active]

    def find_player(self, user_id: int) -> Player | None:
        return next((player for player in self.players if player.user_id == user_id), None)

    def advance_turn(self) -> None:
        if not self.active_players:
            return
        for _ in self.players:
            self.turn_index = (self.turn_index + 1) % len(self.players)
            if self.current_player.active:
                return


@dataclass(slots=True)
class TurnResult:
    text: str
    awaiting_purchase: bool = False
    bankrupt: list[tuple[int, int, int]] = field(default_factory=list)
    winner_id: int | None = None
    finished: bool = False
