import unittest

from wizardtraining.opportunities import (BUTTON, FEATURE, NEEDS_OPERATOR, PATTERN, USABLE, USED_HUD_BUTTONS, describe,
                                          from_dialog, from_tip, measured_patterns, note, unused_buttons)

WHEN = "2026-10-28T20:38:26"
FRIEND_FINDER = ("Click the Quest Friend Finder button when you would like to find friends to quest with. Players who "
                 "accept will be added to a Group and teleported to you.")


class TipTest(unittest.TestCase):
    def test_a_tip_naming_a_feature_is_one_and_one_bringing_in_players_needs_the_operator(self):
        found = from_tip("Quest Friend Finder", FRIEND_FINDER, WHEN)
        self.assertEqual(found.kind, FEATURE)
        self.assertEqual(found.status, NEEDS_OPERATOR)
        self.assertIn("Group", found.evidence)

    def test_a_plain_notice_is_none(self):
        self.assertIsNone(from_tip("INFO", "You cannot teleport to that location. The dungeon timer has ended.", WHEN))
        self.assertIsNone(from_tip("INFO", "The dungeon has been reset.", WHEN))


class DialogTest(unittest.TestCase):
    def test_hints_are_kept_and_story_is_not(self):
        pages = ["The King changed after the expedition beyond the river wall.",
                 "Press the button on your spellbook to train new spells."]
        found = from_dialog("Ambrose", pages, WHEN)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].status, USABLE)
        self.assertIn("spellbook", found[0].evidence)


class ButtonTest(unittest.TestCase):
    def test_only_buttons_never_pressed(self):
        names = ["GoHomeButton", "MarkButton", "btnFriends", "ClassEventButton", "XPBar", "btnFriends"]
        found = unused_buttons(names, USED_HUD_BUTTONS, WHEN)
        self.assertEqual([item.evidence.rsplit(": ", 1)[1] for item in found], ["btnFriends", "ClassEventButton"])
        self.assertTrue(all(item.kind == BUTTON and item.status == NEEDS_OPERATOR for item in found))


class PatternTest(unittest.TestCase):
    def test_quests_paying_far_more_than_fights_is_a_pattern(self):
        found = measured_patterns({"talk": [315, 270, 300], "battle": [33, 39, 36, 45, 27]}, [], [], WHEN)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kind, PATTERN)
        self.assertIn("avoid optional fights", found[0].evidence)

    def test_not_before_the_numbers_are_steady(self):
        self.assertEqual(measured_patterns({"talk": [315], "battle": [33, 39]}, [0.6], [False], WHEN), [])

    def test_costly_fights_and_taken_wisps(self):
        found = measured_patterns({}, [0.6, 0.55, 0.7, 0.4, 0.65], [False] * 6 + [True] * 4, WHEN)
        self.assertEqual(sorted(item.key for item in found),
                         ["pattern:fights cost much of the health", "pattern:wisps are often taken"])


class StoreTest(unittest.TestCase):
    def test_sightings_merge_by_key_and_the_stricter_status_stays(self):
        store = {}
        first = from_tip("Quest Friend Finder", FRIEND_FINDER, WHEN)
        self.assertTrue(note(store, first))
        self.assertFalse(note(store, first))
        self.assertEqual(store[first.key]["times_seen"], 2)
        self.assertEqual(store[first.key]["status"], NEEDS_OPERATOR)

    def test_a_line_for_the_reports_says_when_it_waits_for_the_operator(self):
        line = describe(from_tip("Quest Friend Finder", FRIEND_FINDER, WHEN))
        self.assertIn("needs the operator", line)


if __name__ == "__main__":
    unittest.main()
