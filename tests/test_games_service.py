import unittest

from app.config import Settings
from app.services.games import GameManager


class GameManagerTests(unittest.IsolatedAsyncioTestCase):
    def make_manager(self, topics: tuple[int, ...] = ()) -> GameManager:
        return GameManager(Settings(bot_token="test", allowed_topic_ids=topics))

    async def test_rooms_are_isolated_by_topic(self) -> None:
        games = self.make_manager()
        first = await games.create(-100, 10, 1, "A")
        second = await games.create(-100, 20, 2, "B")

        self.assertIs(games.get(-100, 10), first)
        self.assertIs(games.get(-100, 20), second)
        self.assertIsNot(first, second)

    async def test_only_configured_topics_are_allowed(self) -> None:
        games = self.make_manager((10, 20))
        self.assertTrue(games.topic_allowed(10))
        self.assertFalse(games.topic_allowed(30))
        with self.assertRaisesRegex(ValueError, "không được phép"):
            await games.create(-100, 30, 1, "A")

    async def test_empty_topic_allowlist_allows_every_topic(self) -> None:
        games = self.make_manager()
        self.assertTrue(games.topic_allowed(None))
        self.assertTrue(games.topic_allowed(999))


if __name__ == "__main__":
    unittest.main()
