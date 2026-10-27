import asyncio
import unittest

from wizardtraining.screen import is_idle_box, visible_named


class StandIn:
    """A game window as the window tree is read: its name, whether it shows, and its children."""

    def __init__(self, name, visible=True, children=()):
        self._name, self._visible, self._children = name, visible, list(children)

    async def name(self):
        return self._name

    async def is_visible(self):
        return self._visible

    async def children(self):
        return self._children


class Unreadable(StandIn):
    async def name(self):
        raise RuntimeError("memory read failed")


class ScreenTest(unittest.TestCase):
    def test_finds_a_message_box_wherever_it_shows_but_not_under_a_hidden_window(self):
        idle_box = StandIn("MessageBoxModalWindow")
        hidden_box = StandIn("MessageBoxModalWindow")
        root = StandIn("root", children=[
            Unreadable("broken"),
            StandIn("WorldView", children=[StandIn("PlanningPhase", visible=False, children=[hidden_box]),
                                           StandIn("windowHUD"), idle_box])])
        self.assertEqual(asyncio.run(visible_named(root, "MessageBoxModalWindow", depth=4)), [idle_box])
        self.assertEqual(asyncio.run(visible_named(root, "MessageBoxModalWindow", depth=1)), [])

    def test_the_idle_box_is_told_by_either_line(self):
        self.assertTrue(is_idle_box("Would you like to return to combat?"))
        self.assertTrue(is_idle_box("You Are Idle"))
        self.assertFalse(is_idle_box("Are you sure you want to flee? You will lose all your Mana"))


if __name__ == "__main__":
    unittest.main()
