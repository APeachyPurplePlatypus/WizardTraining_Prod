import asyncio
import unittest

from wizardtraining.doors import (CHANGE_POLL_SECONDS, CHANGE_START_SECONDS, CHECK_AFTER_TAP_SECONDS,
                                  DOOR_PUSH_SECONDS, DOOR_TAP_SECONDS, change_begins, push_through)


class FakeGame:
    """A clock that moves only when the door code sleeps or taps W, and a zone change that begins once W has been
    held `taps_to_change` times (0: it had begun before the door code ran)."""

    def __init__(self, taps_to_change=None, begins_at=None):
        self.now = 0.0
        self.taps = []
        self.taps_to_change = taps_to_change
        self.begins_at = begins_at

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds

    async def tap_w(self, seconds):
        self.taps.append(seconds)
        self.now += seconds

    async def change_begun(self):
        if self.begins_at is not None:
            return self.now >= self.begins_at
        return self.taps_to_change is not None and len(self.taps) >= self.taps_to_change


def push(game):
    return asyncio.run(push_through(game.tap_w, game.change_begun, clock=game.clock, sleep=game.sleep))


def begins(game, seconds):
    return asyncio.run(change_begins(game.change_begun, seconds, clock=game.clock, sleep=game.sleep))


class ChangeBeginsTest(unittest.TestCase):
    def test_a_change_already_begun_is_seen_at_once(self):
        game = FakeGame(taps_to_change=0)
        self.assertTrue(begins(game, CHANGE_START_SECONDS))
        self.assertEqual(game.now, 0.0)

    def test_a_change_beginning_within_the_wait_is_seen(self):
        game = FakeGame(begins_at=0.3)
        self.assertTrue(begins(game, CHANGE_START_SECONDS))
        self.assertLess(game.now, 0.3 + CHANGE_POLL_SECONDS + 1e-9)

    def test_no_change_waits_the_whole_time_and_no_longer(self):
        game = FakeGame()
        self.assertFalse(begins(game, CHANGE_START_SECONDS))
        self.assertGreaterEqual(game.now, CHANGE_START_SECONDS)
        self.assertLess(game.now, CHANGE_START_SECONDS + CHANGE_POLL_SECONDS + 1e-9)


class PushThroughTest(unittest.TestCase):
    def test_stops_tapping_once_the_change_begins(self):
        """The Olde Town to Triton Avenue bounce: W went on for the whole 0.8 s after the change had begun."""
        game = FakeGame(taps_to_change=2)
        self.assertTrue(push(game))
        self.assertEqual(game.taps, [DOOR_TAP_SECONDS] * 2)

    def test_a_change_that_shows_after_the_tap_stops_the_next_one(self):
        game = FakeGame(begins_at=DOOR_TAP_SECONDS + CHECK_AFTER_TAP_SECONDS / 2)
        self.assertTrue(push(game))
        self.assertEqual(len(game.taps), 1)

    def test_holds_w_no_longer_than_the_push_in_all(self):
        game = FakeGame()
        self.assertFalse(push(game))
        self.assertAlmostEqual(sum(game.taps), DOOR_PUSH_SECONDS)
        self.assertTrue(all(seconds == DOOR_TAP_SECONDS for seconds in game.taps))

    def test_each_tap_is_short_enough_to_be_harmless_if_played_again(self):
        """A tap played again in the new zone moves the wizard about 600 units a second; Triton Avenue's arrival
        spot from Olde Town is 126 units outside the gate back."""
        self.assertLess(DOOR_TAP_SECONDS * 600, 126)


if __name__ == "__main__":
    unittest.main()
