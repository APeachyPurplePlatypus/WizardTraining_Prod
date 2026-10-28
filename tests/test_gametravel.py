import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from wizardtraining import gametravel


class StandIn:
    def __init__(self, name, children=(), tip="", visible=True):
        self._name, self._children, self.tip, self._visible = name, list(children), tip, visible

    async def name(self):
        return self._name

    async def is_visible(self):
        return self._visible

    async def children(self):
        return self._children

    async def read_wide_string_from_offset(self, offset):
        assert offset == gametravel.TIP_OFFSET
        return self.tip


class Game:
    """The HUD's travel buttons, a zone name, and the clicks the code makes."""

    def __init__(self, zone="WizardCity/WC_Streets/WC_Cyclops", marked=False, hub_timer=False, recall_timer=False,
                 mana=84, refuses_marks=False):
        self.zone, self.clicked, self.loading, self.mana, self.refuses_marks = zone, [], False, mana, refuses_marks
        self.mark = StandIn("MarkButton", tip="Mark Location")
        self.hub = StandIn("GoHomeButton", [StandIn("txtGoHomeTimer", visible=hub_timer)], tip="Go to The Commons")
        self.recall = StandIn("RecallButton", [StandIn("txtRecallTimer", visible=recall_timer)],
                              tip="Recall Location" if marked else "No Mark Set")
        buttons = StandIn("compassAndTeleporterButtons", [self.mark, self.hub, self.recall, StandIn("GotoDormButton")])
        self.root = StandIn("root", [StandIn("WorldView", [StandIn("windowHUD", [buttons])])])

    def client(self):
        game = self

        async def zone_name():
            return game.zone

        async def is_loading():
            return game.loading

        async def current_mana():
            return game.mana

        return SimpleNamespace(root_window=self.root, zone_name=zone_name, is_loading=is_loading,
                               stats=SimpleNamespace(current_mana=current_mana))

    async def click(self, client, path):
        self.clicked.append(path[-1])
        if path[-1] == "MarkButton" and not self.refuses_marks:
            self.recall.tip = "Teleport to Cyclops Lane"
            self.mana -= 5
        if path[-1] in ("GoHomeButton", "RecallButton"):
            self.zone = "WizardCity/WC_Hub" if path[-1] == "GoHomeButton" else "WizardCity/WC_Streets/WC_Cyclops"


def run(game, function):
    patches = (mock.patch.object(gametravel, "click", game.click), mock.patch.object(gametravel, "MARK_SETTLE_SECONDS", 0),
               mock.patch.object(gametravel, "ZONE_CHANGE_WAIT_SECONDS", 0.2),
               mock.patch.object(gametravel, "ZONE_CHANGE_POLL_SECONDS", 0.01))
    for patch in patches:
        patch.start()
    try:
        return asyncio.run(function(game.client()))
    finally:
        for patch in patches:
            patch.stop()


class GameTravelTest(unittest.TestCase):
    def test_mark_location_is_pressed_and_the_recall_button_then_shows_a_mark(self):
        game = Game()
        self.assertIsNone(run(game, gametravel.mark_here))
        self.assertEqual(game.clicked, ["MarkButton"])

    def test_a_mark_that_cost_mana_and_changed_the_tooltip_counts(self):
        game = Game(mana=84)
        self.assertIsNone(run(game, gametravel.mark_here))
        self.assertEqual(game.mana, 79)

    def test_no_mark_at_all_is_reported(self):
        game = Game(refuses_marks=True)
        self.assertEqual(run(game, gametravel.mark_here), "the Recall button still shows no mark after Mark Location")

    def test_an_older_mark_is_not_a_new_one_when_the_game_refused(self):
        """On a Golem Tower floor, Mark did nothing: the tooltip kept the Cyclops Lane mark and mana stayed at 89."""
        game = Game(marked=True, mana=89, refuses_marks=True)
        game.recall.tip = "Teleport to Cyclops Lane"
        problem = run(game, gametravel.mark_here)
        self.assertTrue(problem.startswith("the game refused Mark Location here"))
        self.assertEqual(game.mana, 89)

    def test_go_to_the_commons_changes_the_zone(self):
        game = Game()
        self.assertIsNone(run(game, gametravel.go_to_the_commons))
        self.assertEqual(game.clicked, ["GoHomeButton"])
        self.assertEqual(game.zone, "WizardCity/WC_Hub")

    def test_go_to_the_commons_waits_out_its_cooldown(self):
        game = Game(hub_timer=True)
        self.assertEqual(run(game, gametravel.go_to_the_commons), "Go to The Commons is cooling down")
        self.assertEqual(game.clicked, [])

    def test_recall_needs_a_mark_and_no_cooldown(self):
        self.assertEqual(run(Game(), gametravel.recall), "no spot is marked")
        game = Game(marked=True, recall_timer=True)
        self.assertEqual(run(game, gametravel.recall), "Recall is cooling down")
        self.assertEqual(game.clicked, [])
        game = Game(zone="WizardCity/WC_Hub", marked=True)
        self.assertIsNone(run(game, gametravel.recall))
        self.assertEqual(game.clicked, ["RecallButton"])

    def test_only_the_three_travel_buttons_are_ever_clicked(self):
        game = Game()
        run(game, gametravel.mark_here)
        run(game, gametravel.go_to_the_commons)
        run(game, gametravel.recall)
        self.assertLessEqual(set(game.clicked), {"MarkButton", "GoHomeButton", "RecallButton"})
        self.assertNotIn("GotoDormButton", game.clicked)


if __name__ == "__main__":
    unittest.main()
