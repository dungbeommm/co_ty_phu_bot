import random
import unittest

from app.game.board import create_board
from app.game.engine import (
    GameError,
    asset_value,
    decide_purchase,
    join_room,
    mark_bankrupt,
    roll_turn,
    start_room,
)
from app.game.models import GameRoom, Phase, Player


def make_room() -> GameRoom:
    return GameRoom(
        chat_id=1,
        host_id=1,
        players=[Player(1, "A", 15_000_000)],
        board=create_board(),
        starting_cash=15_000_000,
        pass_go_salary=2_000_000,
        min_players=2,
        max_players=6,
    )


class GameTests(unittest.TestCase):
    def test_lobby_and_start(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        self.assertIs(room.phase, Phase.PLAYING)

    def test_only_current_player_can_roll(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        with self.assertRaises(GameError):
            roll_turn(room, 2, roller=lambda: (1, 1))

    def test_buy_property(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.players[0].position = 23
        result = roll_turn(room, 1, roller=lambda: (1, 1))
        self.assertTrue(result.awaiting_purchase)
        decide_purchase(room, 1, True)
        self.assertEqual(room.board[1].owner_id, 1)
        self.assertIn(1, room.players[0].property_indexes)

    def test_bankruptcy_preserves_assets(self) -> None:
        room = make_room()
        player = room.players[0]
        room.board[1].owner_id = 1
        player.property_indexes = [1]
        player.cash = 1_000_000
        _, rank, assets = mark_bankrupt(room, player)
        self.assertEqual(rank, 1)
        self.assertEqual(assets, 1_600_000)
        self.assertEqual(asset_value(room, player), 1_600_000)
        self.assertIsNone(room.board[1].owner_id)

    def test_pass_go_salary(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.players[0].position = 23
        roll_turn(room, 1, roller=lambda: (1, 1), rng=random.Random(1))
        self.assertEqual(room.players[0].cash, 17_000_000)


if __name__ == "__main__":
    unittest.main()
