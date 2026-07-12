import random
import unittest

from app.game.board import create_board
from app.game.engine import (
    GameError,
    asset_value,
    build_house,
    buildable_properties,
    buy_illegal_item,
    decide_purchase,
    demolish_house,
    gamble,
    join_room,
    mark_bankrupt,
    open_mystery_box,
    roll_turn,
    sabotage_house,
    start_room,
    steal_from_player,
    surrender,
)
from app.game.models import GameRoom, Phase, Player, PlayerStatus


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


def next_round(room: GameRoom) -> None:
    """Đưa lượt qua người kế tiếp rồi quay lại người đầu để mô phỏng vòng mới."""
    room.advance_turn()
    room.advance_turn()


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
        self.assertEqual(room.board[1].owner_landings, 1)
        self.assertIn(1, room.players[0].property_indexes)

    def test_second_landing_unlocks_building(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.players[0].position = 23
        roll_turn(room, 1, roller=lambda: (1, 1))
        decide_purchase(room, 1, True)
        room.players[0].position = 23
        roll_turn(room, 1, roller=lambda: (1, 1))
        self.assertEqual(room.board[1].owner_landings, 2)
        self.assertEqual(buildable_properties(room, 1), [1])

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

    def test_build_house_only_requires_owned_property(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[1].owner_id = 1
        room.board[1].owner_landings = 1
        room.players[0].property_indexes = [1]
        room.players[0].position = 1
        self.assertEqual(buildable_properties(room, 1), [])
        room.board[1].owner_landings = 2
        self.assertEqual(buildable_properties(room, 1), [1])

    def test_build_house_increases_rent_and_asset_value(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        for index in (1, 3):
            room.board[index].owner_id = 1
            room.board[index].owner_landings = 2
        room.players[0].property_indexes = [1, 3]
        room.players[0].position = 1
        before_cash = room.players[0].cash
        before_assets = asset_value(room, room.players[0])
        text = build_house(room, 1, 1)
        self.assertIn("xây nhà #1", text)
        self.assertEqual(room.board[1].houses, 1)
        self.assertLess(room.players[0].cash, before_cash)
        self.assertEqual(asset_value(room, room.players[0]), before_assets)

    def test_can_build_again_on_later_turn_while_still_on_land(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        for index in (1, 3):
            room.board[index].owner_id = 1
            room.board[index].owner_landings = 2
        room.players[0].property_indexes = [1, 3]
        room.players[0].position = 1
        build_house(room, 1, 1)
        next_round(room)
        build_house(room, 1, 1)
        self.assertEqual(room.board[1].houses, 2)

    def test_four_houses_upgrade_to_hotel(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[1].owner_id = 1
        room.board[1].owner_landings = 2
        room.players[0].property_indexes = [1]
        room.players[0].position = 1
        for _ in range(5):
            build_house(room, 1, 1)
            next_round(room)
        self.assertEqual(room.board[1].houses, 5)
        self.assertEqual(buildable_properties(room, 1), [])

    def test_full_color_group_doubles_unbuilt_rent(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        for index in (1, 3):
            room.board[index].owner_id = 2
        room.players[1].property_indexes = [1, 3]
        room.players[0].position = 1
        before = room.players[0].cash
        roll_turn(room, 1, roller=lambda: (1, 1))
        self.assertEqual(room.players[0].cash, before - 120_000)

    def test_mystery_box_can_only_be_opened_once(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        text = open_mystery_box(room, 1, rng=random.Random(1))
        self.assertTrue(text)
        self.assertTrue(room.players[0].mystery_used)
        with self.assertRaises(GameError):
            open_mystery_box(room, 1, rng=random.Random(1))

    def test_rent_shield_blocks_one_payment(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[3].owner_id = 2
        room.players[1].property_indexes = [3]
        room.players[0].position = 1
        room.players[0].rent_shields = 1
        cash = room.players[0].cash
        result = roll_turn(room, 1, roller=lambda: (1, 1))
        self.assertIn("Khiên kích hoạt", result.text)
        self.assertEqual(room.players[0].cash, cash)
        self.assertEqual(room.players[0].rent_shields, 0)

    def test_demolish_house_refunds_half_cost(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        for index in (1, 3):
            room.board[index].owner_id = 1
            room.board[index].owner_landings = 2
        room.players[0].property_indexes = [1, 3]
        room.players[0].position = 1
        build_house(room, 1, 1)
        next_round(room)
        before = room.players[0].cash
        demolish_house(room, 1, 1)
        self.assertEqual(room.board[1].houses, 0)
        self.assertGreater(room.players[0].cash, before)

    def test_steal_is_limited_once_per_turn(self) -> None:
        class PlayerSuccessRng:
            def random(self) -> float:
                return 0.04  # Thành công dưới mốc trộm người chơi 5%.

            def randint(self, _start: int, _end: int) -> int:
                return 73

        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        before = room.players[0].cash
        target_before = room.players[1].cash
        steal_from_player(room, 1, 2, rng=PlayerSuccessRng())
        first_reward = target_before * 73 // 100
        self.assertEqual(room.players[0].cash, before + first_reward)
        self.assertEqual(room.players[1].cash, target_before - first_reward)
        with self.assertRaises(GameError):
            steal_from_player(room, 1, 2, rng=PlayerSuccessRng())
        next_round(room)
        second_before = room.players[1].cash
        steal_from_player(room, 1, 2, rng=PlayerSuccessRng())
        self.assertEqual(room.players[1].cash, second_before - second_before * 73 // 100)

    def test_gamble_uses_current_cash(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        main_cash = room.players[0].cash
        gamble(room, 1, "roulette", 500_000, rng=random.Random(1))
        self.assertEqual(room.players[0].cash, main_cash - 250_000)
        # Vòng quay và Tài/Xỉu không bị giới hạn theo lượt.
        gamble(room, 1, "roulette", 500_000, rng=random.Random(1))
        self.assertEqual(room.players[0].cash, main_cash - 500_000)
        with self.assertRaises(GameError):
            gamble(room, 1, "tai", room.players[0].cash, rng=random.Random(1))

    def test_only_one_strategic_action_per_turn(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[1].owner_id = 1
        room.board[1].owner_landings = 2
        room.players[0].property_indexes = [1]
        room.players[0].position = 1
        build_house(room, 1, 1)
        with self.assertRaises(GameError):
            build_house(room, 1, 1)
        with self.assertRaises(GameError):
            buy_illegal_item(room, 1, "lockpick")
        next_round(room)
        buy_illegal_item(room, 1, "getaway")
        with self.assertRaises(GameError):
            build_house(room, 1, 1)

    def test_bank_theft_rewards_fifty_million(self) -> None:
        class BankSuccessRng:
            def random(self) -> float:
                return 0.04  # Thành công với tỷ lệ ngân hàng mới: 5%.

        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        before = room.players[0].cash
        text = steal_from_player(room, 1, 0, rng=BankSuccessRng())
        self.assertIn("50.000.000", text)
        self.assertEqual(room.players[0].cash, before + 50_000_000)
        next_round(room)
        with self.assertRaises(GameError):
            steal_from_player(room, 1, 0, rng=random.Random(1))

    def test_failed_theft_loses_fee_land_and_goes_to_jail(self) -> None:
        class FailureRng:
            def choice(self, values):
                return values[0]

            def random(self):
                return 0.99

        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[1].owner_id = 1
        room.players[0].property_indexes = [1]
        before = room.players[0].cash
        steal_from_player(room, 1, 2, rng=FailureRng())
        self.assertEqual(room.players[0].cash, before * 4 // 5)
        self.assertEqual(room.players[0].property_indexes, [])
        self.assertIsNone(room.board[1].owner_id)
        self.assertEqual(room.players[0].jail_turns_left, 3)
        self.assertEqual(room.current_player.user_id, 2)

    def test_jailed_player_cannot_use_side_actions(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.players[0].status = PlayerStatus.JAILED
        room.players[0].jail_turns_left = 3
        self.assertEqual(buildable_properties(room, 1), [])
        with self.assertRaises(GameError):
            gamble(room, 1, "roulette", 500_000, rng=random.Random(1))
        with self.assertRaises(GameError):
            open_mystery_box(room, 1, rng=random.Random(1))
        with self.assertRaises(GameError):
            steal_from_player(room, 1, 2, rng=random.Random(1))
        with self.assertRaises(GameError):
            buy_illegal_item(room, 1, "lockpick")

    def test_mystery_building_voucher_does_not_require_cash(self) -> None:
        class HouseRng:
            def randint(self, _start, _end):
                return 91

            def choice(self, values):
                return values[0]

        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        room.board[1].owner_id = 1
        room.board[1].owner_landings = 2
        room.players[0].property_indexes = [1]
        room.players[0].position = 1
        room.players[0].cash = 0
        text = open_mystery_box(room, 1, rng=HouseRng())
        self.assertIn("Phiếu xây miễn phí", text)
        self.assertEqual(room.players[0].building_vouchers, 1)
        next_round(room)
        text = build_house(room, 1, 1)
        self.assertIn("Phiếu xây miễn phí", text)
        self.assertEqual(room.board[1].houses, 1)

    def test_black_market_and_sabotage(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        buy_illegal_item(room, 1, "bomb")
        next_round(room)
        room.board[3].owner_id = 2
        room.board[3].houses = 1
        room.players[1].property_indexes = [3]
        text = sabotage_house(room, 1, 2, rng=random.Random(1))
        self.assertIn("Đã phá", text)
        self.assertEqual(room.board[3].houses, 0)
        self.assertEqual(room.players[0].demolition_bombs, 0)

    def test_surrender_finishes_two_player_game(self) -> None:
        room = make_room()
        join_room(room, 2, "B")
        start_room(room, 1)
        result = surrender(room, 1)
        self.assertTrue(result.finished)
        self.assertEqual(result.winner_id, 2)


if __name__ == "__main__":
    unittest.main()
