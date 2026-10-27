import asyncio
import unittest

from wizardtraining.screen import visible_named, visible_names_under, window_saying


class StandIn:
    """A game window as the window tree is read: its name, whether it shows, its text and its children."""

    def __init__(self, name, visible=True, children=(), text=""):
        self._name, self._visible, self._children, self._text = name, visible, list(children), text

    async def name(self):
        return self._name

    async def is_visible(self):
        return self._visible

    async def children(self):
        return self._children

    async def maybe_text(self):
        return self._text


class Unreadable(StandIn):
    async def name(self):
        raise RuntimeError("memory read failed")

    async def maybe_text(self):
        raise RuntimeError("no text")


def idle_box(visible=True):
    return StandIn("AFKWindow", visible=visible, children=[StandIn("messageBoxBG", children=[
        StandIn("messageBoxLayout", children=[
            StandIn("TextArea", children=[StandIn("CaptionText", text="<center>Would you like to return to "
                                                                       "combat?</center>")]),
            StandIn("AdjustmentWindow", children=[StandIn("Layout", children=[StandIn("centerButton")])])])])])


class ScreenTest(unittest.TestCase):
    def test_finds_a_message_box_wherever_it_shows_but_not_under_a_hidden_window(self):
        box = StandIn("MessageBoxModalWindow")
        hidden_box = StandIn("MessageBoxModalWindow")
        root = StandIn("root", children=[
            Unreadable("broken"),
            StandIn("WorldView", children=[StandIn("PlanningPhase", visible=False, children=[hidden_box]),
                                           StandIn("windowHUD"), box])])
        self.assertEqual(asyncio.run(visible_named(root, "MessageBoxModalWindow", depth=4)), [box])
        self.assertEqual(asyncio.run(visible_named(root, "MessageBoxModalWindow", depth=1)), [])

    def test_finds_the_idle_box_by_its_text_whatever_its_window_names(self):
        root = StandIn("root", children=[Unreadable("broken"), StandIn("WorldView", children=[
            StandIn("PlanningPhase", visible=False, children=[idle_box()]), idle_box()])])
        chain = asyncio.run(window_saying(root, ("return to combat", "you are idle"), depth=9))
        names = [asyncio.run(window.name()) for window in chain]
        self.assertEqual(names, ["WorldView", "AFKWindow", "messageBoxBG", "messageBoxLayout", "TextArea",
                                 "CaptionText"])
        self.assertIsNone(asyncio.run(window_saying(root, ("return to combat",), depth=5)))

    def test_reports_window_names_without_their_text(self):
        names = asyncio.run(visible_names_under(idle_box(), depth=3))
        self.assertEqual(names, ["messageBoxBG", "messageBoxBG/messageBoxLayout",
                                 "messageBoxBG/messageBoxLayout/TextArea",
                                 "messageBoxBG/messageBoxLayout/AdjustmentWindow"])


if __name__ == "__main__":
    unittest.main()
