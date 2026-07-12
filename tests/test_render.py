import unittest

from app.game.board import create_board
from app.game.models import GameRoom, Phase, Player, PlayerStatus
from app.render import render_board


def _room() -> GameRoom:
    board = create_board()
    board[1].owner_id = 1
    board[6].owner_id = 2
    players = [
        Player(user_id=1, name="A", cash=12_000_000, position=1, property_indexes=[1]),
        Player(user_id=2, name="B", cash=9_000_000, position=6, property_indexes=[6]),
        Player(user_id=3, name="C", cash=0, position=10, status=PlayerStatus.BANKRUPT),
    ]
    return GameRoom(
        chat_id=1, host_id=1, players=players, board=board,
        starting_cash=15_000_000, pass_go_salary=2_000_000,
        min_players=2, max_players=6, phase=Phase.PLAYING, turn_index=0,
    )


class RenderTests(unittest.TestCase):
    def test_render_returns_png_bytes(self) -> None:
        data = render_board(_room())
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 1000)
        # Chữ ký file PNG
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_render_all_positions(self) -> None:
        room = _room()
        for pos in range(len(room.board)):
            room.players[0].position = pos
            self.assertTrue(render_board(room))


if __name__ == "__main__":
    unittest.main()
