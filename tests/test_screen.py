import asyncio
import unittest

from wizardtraining.screen import (is_friend_request, is_game_notice, prompt_fits, TALK, USE, prompt_is_not_a_doors, plain_text, prompt_action, prompt_offers_talk, visible_named,
                                   visible_names_under, window_saying)


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

    def test_reads_a_friend_request_from_its_title_and_caption(self):
        title = plain_text("<center>Friend</center>")
        caption = plain_text("<center>Accept<br>Some Player Level 10 <image;Icons/Icon_Frame.dds;22;22;FFFFFFFF;b>"
                             "<image;Icons/Icon_Death.dds;22;22;FFFFFFFF><br>as your friend?</center>")
        self.assertEqual(caption, "Accept Some Player Level 10 as your friend?")
        self.assertTrue(is_friend_request(title, caption))
        self.assertFalse(is_friend_request("Combat", "Are you sure you want to flee? You will lose all your Mana"))

    def test_a_talk_needs_a_prompt_that_reads_to_talk(self):
        self.assertTrue(prompt_fits(True, "Press X or to Talk", wants=TALK))
        self.assertFalse(prompt_fits(True, "Press X or to Teleport", wants=TALK))
        self.assertTrue(prompt_fits(True, "Press X or to Use", wants=None))
        self.assertFalse(prompt_fits(False, "Press X or to Talk", wants=TALK))

    def test_a_reagents_or_persons_prompt_is_not_a_doors(self):
        self.assertTrue(prompt_is_not_a_doors("Press X or to Collect"))
        self.assertTrue(prompt_is_not_a_doors("Press X or to Talk"))
        self.assertFalse(prompt_is_not_a_doors("Press X or to Enter"))
        self.assertFalse(prompt_is_not_a_doors("Press X or to Teleport"))

    def test_a_persons_prompt_is_not_a_quest_objects(self):
        self.assertFalse(prompt_fits(True, "Press X or to Talk", wants=USE))
        self.assertTrue(prompt_fits(True, "Press X or to Collect", wants=USE))
        self.assertFalse(prompt_fits(False, "Press X or to Collect", wants=USE))

    def test_a_game_notice_is_a_box_titled_info_with_only_an_ok_button(self):
        self.assertTrue(is_game_notice("INFO", ["rightButton"]))
        self.assertFalse(is_game_notice("INFO", ["centerButton", "rightButton"]))
        self.assertFalse(is_game_notice("Friend", ["rightButton"]))
        self.assertFalse(is_game_notice("Trade", ["centerButton", "rightButton"]))
        self.assertFalse(is_game_notice("INFO", []))

    def test_reports_window_names_without_their_text(self):
        names = asyncio.run(visible_names_under(idle_box(), depth=3))
        self.assertEqual(names, ["messageBoxBG", "messageBoxBG/messageBoxLayout",
                                 "messageBoxBG/messageBoxLayout/TextArea",
                                 "messageBoxBG/messageBoxLayout/AdjustmentWindow"])

    def test_a_prompt_to_talk_is_a_persons_and_one_to_enter_is_a_door(self):
        talk = ("<center>Press <image;Art/Art_Keyboard_L.dds;16;32;0xFFFFFFFF;t><image;Art/Art_Keyboard_Mid.dds;-1;32;"
                "0xFFFFFFFF;bt><scale;0.700000><Xoffset;-5><Yoffset;-5>X<Yoffset;5></scale><Xoffset;-5>"
                "<image;Art/Art_Keyboard_R.dds;16;32;0xFFFFFFFF;t> or <image;GUI/Art/Art_Mouse_Left_Click.dds> "
                "to Talk</center>")
        self.assertTrue(prompt_offers_talk(talk))
        self.assertEqual(prompt_action(talk), "Talk")
        for door in ("<center>Press X to Enter</center>", "Press X to Teleport", "Press X to Use", "Press X to Open", ""):
            self.assertFalse(prompt_offers_talk(door))
        self.assertEqual(prompt_action("<center>Press X to Enter</center>"), "Enter")
        self.assertEqual(prompt_action(""), "")



class DungeonEntryBoxTest(unittest.TestCase):
    caption = ("You are about to enter a Dungeon! This Dungeon takes around 1 hour and 30 minutes to finish. "
               "Are you sure you want to enter this Dungeon?")

    def test_the_games_dungeon_entry_box_with_yes_and_no(self):
        from wizardtraining.screen import is_dungeon_entry
        self.assertTrue(is_dungeon_entry(self.caption, ["centerButton", "rightButton"]))
        self.assertTrue(is_dungeon_entry(self.caption, ["rightButton", "centerButton"]))

    def test_not_another_players_box_nor_one_with_other_buttons(self):
        from wizardtraining.screen import is_dungeon_entry
        self.assertFalse(is_dungeon_entry("Accept a player as your friend?", ["centerButton", "rightButton"]))
        self.assertFalse(is_dungeon_entry(self.caption, ["rightButton"]))
        self.assertFalse(is_dungeon_entry(self.caption, ["leftButton", "centerButton", "rightButton"]))


if __name__ == "__main__":
    unittest.main()
