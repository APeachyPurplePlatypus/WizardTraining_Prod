import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from wizardtraining import questbook


class StandIn:
    """A game window as the window tree is read: its name, whether it shows, its text and its children."""

    def __init__(self, name, children=(), text="", visible=True):
        self._name, self._children, self._text, self._visible = name, list(children), text, visible

    async def name(self):
        return self._name

    async def is_visible(self):
        return self._visible

    async def maybe_text(self):
        return self._text

    async def children(self):
        return self._children


def entry(index, title):
    buttons = [StandIn("btnActivate"), StandIn("btnHideQuest")]
    info = StandIn("wndQuestInfo", [StandIn("txtName", text=f"<center>{title}</center>"),
                                    StandIn("txtWorld", text="<center>Cyclops Lane</center>"), *buttons])
    return StandIn(f"wndQuestInfo{index}", [StandIn("questInfoWindow", [info])])


class QuestBook:
    """The spellbook's quest page over a list of pages of titles, with the clicks the code makes recorded."""

    def __init__(self, pages):
        self.pages = [[entry(i, title) for i, title in enumerate(titles)] for titles in pages]
        self.page = 0
        self.clicked = []
        self.book_open = False
        self.list = StandIn("wndQuestList")
        self.refresh()

    def refresh(self):
        self.list._children = list(self.pages[self.page]) + [StandIn("btnPrevPage"), StandIn("btnNextPage")]

    def client(self):
        tree = StandIn("WorldView", [
            StandIn("windowHUD", [StandIn("btnSpellbook")]),
            StandIn("DeckConfiguration", [StandIn("Quest"), StandIn("Close_Button"), self.list])])
        self.deck = tree._children[1]
        return SimpleNamespace(root_window=StandIn("root", [tree]))

    async def click(self, client, path):
        self.clicked.append(path[-1])
        if path[-1] == "btnSpellbook":
            self.book_open = True
        if path[-1] == "Close_Button":
            self.book_open = False
        if path[-1] == "btnNextPage":
            self.page = min(self.page + 1, len(self.pages) - 1)
        if path[-1] == "btnPrevPage":
            self.page = max(self.page - 1, 0)
        self.refresh()

    async def click_window(self, client, window):
        self.clicked.append(window._name)

    async def showing(self, client, path):
        return self.book_open


def run(book, title):
    client = book.client()
    patches = (mock.patch.object(questbook, "click", book.click), mock.patch.object(questbook, "click_window", book.click_window),
               mock.patch.object(questbook, "showing", book.showing),
               mock.patch.object(questbook, "PAGE_SETTLE_SECONDS", 0), mock.patch.object(questbook, "BOOK_OPEN_SECONDS", 0),
               mock.patch.object(questbook, "ACTIVATE_SETTLE_SECONDS", 0))
    for patch in patches:
        patch.start()
    try:
        return asyncio.run(questbook.activate_quest(client, title))
    finally:
        for patch in patches:
            patch.stop()


class ActivateQuestTest(unittest.TestCase):
    def test_a_quest_on_the_first_page_is_activated_and_the_book_closed(self):
        book = QuestBook([["A Whole New World", "Looking Sharp!", "You Can Dig It", "Walkabout"]])
        activation = run(book, "Looking Sharp!")
        self.assertIsNone(activation.problem)
        self.assertEqual(activation.area, "Cyclops Lane")
        self.assertEqual(book.clicked[0:2], ["btnSpellbook", "Quest"])
        self.assertIn("btnActivate", book.clicked)
        self.assertEqual(book.clicked[-1], "Close_Button")
        self.assertFalse(book.book_open)

    def test_the_area_can_be_read_without_activating_anything(self):
        book = QuestBook([["A Whole New World", "Looking Sharp!"]])
        client = book.client()
        with mock.patch.object(questbook, "click", book.click), mock.patch.object(questbook, "click_window", book.click_window), \
                mock.patch.object(questbook, "showing", book.showing), mock.patch.object(questbook, "PAGE_SETTLE_SECONDS", 0), \
                mock.patch.object(questbook, "BOOK_OPEN_SECONDS", 0), mock.patch.object(questbook, "ACTIVATE_SETTLE_SECONDS", 0):
            activation = asyncio.run(questbook.activate_quest(client, "Looking Sharp!", click_activate=False))
        self.assertEqual((activation.problem, activation.area), (None, "Cyclops Lane"))
        self.assertNotIn("btnActivate", book.clicked)
        self.assertFalse(book.book_open)

    def test_a_quest_on_a_later_page_is_found_by_turning_pages(self):
        book = QuestBook([["A Whole New World", "Looking Sharp!", "You Can Dig It", "Walkabout"],
                          ["Diego the Duelmaster"]])
        self.assertIsNone(run(book, "Diego the Duelmaster").problem)
        self.assertEqual(book.page, 1)
        self.assertEqual(book.clicked.count("btnActivate"), 1)

    def test_a_quest_not_in_the_book_is_reported_and_nothing_is_activated(self):
        book = QuestBook([["A Whole New World", "Walkabout"], ["Diego the Duelmaster"]])
        self.assertEqual(run(book, "Colossal Trouble").problem, "Colossal Trouble is not on the quest page")
        self.assertNotIn("btnActivate", book.clicked)
        self.assertFalse(book.book_open)

    def test_only_the_allowed_buttons_are_ever_clicked(self):
        book = QuestBook([["A Whole New World", "Looking Sharp!"], ["Diego the Duelmaster"]])
        run(book, "Diego the Duelmaster")
        allowed = {"btnSpellbook", "Quest", "btnPrevPage", "btnNextPage", "btnActivate", "Close_Button"}
        self.assertLessEqual(set(book.clicked), allowed)
        for forbidden in questbook.FORBIDDEN_BUTTONS:
            self.assertNotIn(forbidden, book.clicked)


if __name__ == "__main__":
    unittest.main()
