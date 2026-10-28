import unittest

from wizardtraining.sidequests import QUEST_FINDER, finder_points_into, in_world, leads_to_the_world_door, next_quest_in_world, UNSUPPORTED, unsupported_reason


class UnsupportedQuestsTest(unittest.TestCase):
    def test_a_quest_that_needs_a_pet_is_unsupported_with_its_reason(self):
        self.assertIn("pet", unsupported_reason("You Can Dig It"))

    def test_a_quest_in_closed_colossus_boulevard_is_unsupported(self):
        self.assertIn("Colossus Boulevard", unsupported_reason("The Gravulum Order"))

    def test_a_reagent_gathering_quest_is_unsupported(self):
        self.assertIn("Mist Wood", unsupported_reason("Wizards in the Mist"))

    def test_a_title_with_a_trailing_space_matches(self):
        self.assertIn("Lord Nightshade", unsupported_reason("The Lore You Know "))

    def test_other_quests_and_no_title_are_not(self):
        self.assertIsNone(unsupported_reason("Looking Sharp!"))
        self.assertIsNone(unsupported_reason(None))
        self.assertTrue(all(reason for reason in UNSUPPORTED.values()))


class ClearWorldTest(unittest.TestCase):
    ZONES = {"Gather the Troops": "Krokotopia", "The Lore You Know": "Wizard City", "You Can Dig It": "Wizard City",
             "Quest Finder": "", "Mystery of the Moon": "Wizard City"}

    def test_the_next_quest_of_the_world_skips_the_unsupported_and_the_finder(self):
        self.assertEqual(next_quest_in_world(self.ZONES, "WizardCity", skip=set()), "Mystery of the Moon")
        self.assertIsNone(next_quest_in_world(self.ZONES, "WizardCity", skip={"Mystery of the Moon"}))
        self.assertEqual(next_quest_in_world(self.ZONES, "Krokotopia", skip=set()), "Gather the Troops")
        self.assertTrue(in_world("Wizard City", "WizardCity"))
        self.assertFalse(in_world("", "WizardCity"))

    def test_the_finder_points_into_a_world_by_its_goal_zone(self):
        self.assertTrue(finder_points_into("WizardCity/WC_Streets/WC_Triton", "WizardCity"))
        self.assertFalse(finder_points_into("Krokotopia/KT_WorldTeleporter", "WizardCity"))
        self.assertFalse(finder_points_into("", "WizardCity"))
        self.assertEqual(QUEST_FINDER, "Quest Finder")

    def test_volumes_toward_the_world_door(self):
        self.assertTrue(leads_to_the_world_door("TeleportVol_Teleport location (Krok_Hub WorldSpiral Entrance)"))
        self.assertFalse(leads_to_the_world_door("TeleportVol_Teleport (Street 2 WC_Shop_Area Exit)"))


if __name__ == "__main__":
    unittest.main()
