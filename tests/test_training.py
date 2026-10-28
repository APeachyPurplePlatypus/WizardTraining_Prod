import unittest

from wizardtraining.training import (COMMONS, CYCLOPS, FIRECAT, GATE, HAUNTED_CAVE, OLDE_TOWN, RAVENWOOD, SCHOOLS,
                                     SHOPPING_DISTRICT, TRAINER, TRITON, UNICORN_WAY, VOLUME, Way, in_dungeon,
                                     next_zone_toward, same_spell, spells_to_learn, way_out_toward_the_commons,
                                     way_to_school, way_toward_zone, zone_for_area)

ICE = SCHOOLS["Ice"]
KNOWN_AT_LEVEL_10 = ["Frost Beetle", "Pixie", "Freeze", "Snow Serpent", "Volcanic Shield"]


class SpellsToLearnTest(unittest.TestCase):
    def test_level_10_ice_wizard_can_learn_evil_snowman(self):
        self.assertEqual(spells_to_learn("Ice", 10, KNOWN_AT_LEVEL_10), ["Evil Snowman"])

    def test_nothing_once_known_or_before_its_level(self):
        self.assertEqual(spells_to_learn("Ice", 10, [*KNOWN_AT_LEVEL_10, "Evil Snowman"]), [])
        self.assertEqual(spells_to_learn("Ice", 9, KNOWN_AT_LEVEL_10), [])

    def test_names_spelled_without_spaces_are_the_same_spell(self):
        self.assertTrue(same_spell("Blood Bat", "Bloodbat"))
        self.assertEqual(spells_to_learn("Myth", 1, ["Bloodbat"]), [])

    def test_schools_without_a_known_way_learn_nothing(self):
        self.assertEqual(spells_to_learn("Life", 10, []), [])
        self.assertEqual(spells_to_learn(None, 10, []), [])


class DungeonTest(unittest.TestCase):
    def test_towers_and_dungeons_by_name(self):
        self.assertTrue(in_dungeon("WizardCity/WC_Streets/Interiors/WC_HauntedCave_T1", []))
        self.assertTrue(in_dungeon("WizardCity/WC_Streets/Interiors/WC_Cyclops_T2", []))
        self.assertTrue(in_dungeon("WizardCity/WC_Streets/WC_Golem_Tower/WC_Golem_Tower_3", []))
        self.assertFalse(in_dungeon("WizardCity/WC_Golem_Tower", []))
        self.assertFalse(in_dungeon("WizardCity/WC_Streets/Interiors/WC_Firecat_H2", []))
        self.assertFalse(in_dungeon("WizardCity/WC_Streets/WC_HauntedCave", []))
        self.assertFalse(in_dungeon(COMMONS, []))

    def test_zones_entered_with_x(self):
        self.assertTrue(in_dungeon("WizardCity/WC_Streets/Interiors/WC_Firecat_Theatre",
                                   ["WizardCity/WC_Streets/Interiors/WC_Firecat_Theatre"]))
        self.assertFalse(in_dungeon(None, []))


class WayTest(unittest.TestCase):
    def test_streets_lead_back_toward_the_commons(self):
        cases = {
            "Triton Avenue": (["TeleportVol_Teleport (Street4 Street2 Exit)",
                               "TeleportVol_Teleport location (Street4 to Cavern)",
                               "TeleportVol_Teleport location (Tele Up)"], "TeleportVol_Teleport (Street4 Street2 Exit)"),
            "Olde Town": (["TeleportVol_Teleport (Street 2 WC_Shop_Area Exit)", "TeleportVol_ToBazaar",
                           "TeleportVol_Teleport-Foulgaze"], "TeleportVol_Teleport (Street 2 WC_Shop_Area Exit)"),
            "Shopping District": (["TeleportVol_Teleport location (Shop Area to Street2)",
                                   "TeleportVol_Teleport location (WC_Shop Hub)",
                                   "TeleportVol_Teleport location (WC_Shop Jewelry)"],
                                  "TeleportVol_Teleport location (WC_Shop Hub)"),
            "Unicorn Way": (["TeleportVol_Teleport location (Street1 Arena Entrance)",
                             "TeleportVol_Teleport location (Street1 Hub Exit)"],
                            "TeleportVol_Teleport location (Street1 Hub Exit)"),
            "Haunted Cave": (["TeleportVol_Teleport location (Cavern to Street4)"],
                             "TeleportVol_Teleport location (Cavern to Street4)"),
        }
        for zone, (volumes, expected) in cases.items():
            with self.subTest(zone):
                self.assertEqual(way_out_toward_the_commons(volumes), expected)

    def test_no_way_out_when_nothing_says_so(self):
        self.assertIsNone(way_out_toward_the_commons(["TeleportVol_Teleport location (Tele Up)",
                                                      "TeleportVol_Teleport location (Tele Down)"]))
        self.assertIsNone(way_out_toward_the_commons([]))

    def test_the_commons_ravenwood_and_the_school(self):
        self.assertEqual(way_to_school(COMMONS, ICE, ["TeleportVol_Teleport location (WC_Hub WC_Headmistress_House "
                                                      "Entrance)"]), Way(GATE, RAVENWOOD))
        ravenwood = ["TeleportVol_Teleport location (to MythSchool)", "TeleportVol_Teleport location (to IceSchool)",
                     "TeleportVol_Teleport location (to Commons)"]
        self.assertEqual(way_to_school(RAVENWOOD, ICE, ravenwood),
                         Way(VOLUME, "TeleportVol_Teleport location (to IceSchool)"))
        self.assertEqual(way_to_school(ICE.interior, ICE, []), Way(TRAINER, "Lydia Greyrose"))

    def test_from_ravenwood_the_way_to_the_commons_is_its_to_commons_volume(self):
        ravenwood = ["TeleportVol_Teleport location (to MythSchool)", "TeleportVol_Teleport location (to IceSchool)",
                     "TeleportVol_Teleport location (to Commons)", "TeleportVol_Teleport location (to StormSchool)",
                     "TeleportVol_Teleport location (to FireSchool)"]
        way = way_toward_zone("WizardCity/WC_Ravenwood", "WizardCity/WC_Hub", ravenwood)
        self.assertEqual(way.name, "TeleportVol_Teleport location (to Commons)")

    def test_from_the_dark_cave_the_way_out_is_toward_cyclops_lane(self):
        cave = ["TeleportVol_Teleport location (Cavern to Street3)", "TeleportVol_Teleport location (Cavern to Street5)",
                "TeleportVol_Teleport location"]
        way = way_toward_zone("WizardCity/WC_Streets/WC_DarkCave", "WizardCity/WC_Streets/WC_Firecat", cave)
        self.assertEqual(way.name, "TeleportVol_Teleport location (Cavern to Street3)")

    def test_from_golem_court_the_way_to_unicorn_way_is_its_hub_exit(self):
        golem = ["TeleportVol_Teleport location (WC_Golem_Tower Hub Exit)", "TeleportVol_Teleport location 7"]
        way = way_toward_zone("WizardCity/WC_Golem_Tower", "WizardCity/WC_Streets/WC_Unicorn", golem)
        self.assertEqual(way.name, "TeleportVol_Teleport location (WC_Golem_Tower Hub Exit)")

    def test_from_another_school_the_way_is_out_to_ravenwood(self):
        self.assertEqual(way_to_school("WizardCity/Interiors/WC_SchoolMyth", ICE,
                                       ["TeleportVol_Teleport location (MythSchool Ravenwood Exit)"]),
                         Way(VOLUME, "TeleportVol_Teleport location (MythSchool Ravenwood Exit)"))


class ZoneTreeTest(unittest.TestCase):
    def test_the_next_zone_goes_back_toward_the_commons_then_out_to_the_target(self):
        self.assertEqual(next_zone_toward(UNICORN_WAY, CYCLOPS), COMMONS)
        self.assertEqual(next_zone_toward(COMMONS, CYCLOPS), SHOPPING_DISTRICT)
        self.assertEqual(next_zone_toward(SHOPPING_DISTRICT, CYCLOPS), OLDE_TOWN)
        self.assertEqual(next_zone_toward(OLDE_TOWN, CYCLOPS), CYCLOPS)
        self.assertEqual(next_zone_toward(TRITON, CYCLOPS), OLDE_TOWN)
        self.assertEqual(next_zone_toward(HAUNTED_CAVE, CYCLOPS), TRITON)
        self.assertIsNone(next_zone_toward(CYCLOPS, CYCLOPS))
        self.assertIsNone(next_zone_toward("WizardCity/Interiors/WC_Library", CYCLOPS))

    def test_the_door_of_each_step_comes_from_the_zones_own_volumes_and_gates(self):
        cyclops = ["TeleportVol_Teleport (Street3 Street2 Exit)", "TeleportVol_Teleport location"]
        self.assertEqual(way_toward_zone(CYCLOPS, TRITON, cyclops).name, "TeleportVol_Teleport (Street3 Street2 Exit)")
        self.assertEqual(way_toward_zone(COMMONS, CYCLOPS, []), Way(GATE, SHOPPING_DISTRICT))
        shop = ["TeleportVol_Teleport location (Shop Area to Street2)", "TeleportVol_Teleport location (WC_Shop Hub)"]
        self.assertEqual(way_toward_zone(SHOPPING_DISTRICT, CYCLOPS, shop).name,
                         "TeleportVol_Teleport location (Shop Area to Street2)")
        self.assertEqual(way_toward_zone(OLDE_TOWN, CYCLOPS, ["TeleportVol_ToBazaar"]), Way(GATE, CYCLOPS))
        unicorn = ["TeleportVol_Teleport location (Street1 Arena Entrance)", "TeleportVol_Teleport location (Street1 Hub Exit)",
                   "TeleportVol_Teleport location-ThiefHouse"]
        self.assertEqual(way_toward_zone(UNICORN_WAY, CYCLOPS, unicorn).name,
                         "TeleportVol_Teleport location (Street1 Hub Exit)")

    def test_area_names_from_the_quest_page_name_zones(self):
        self.assertEqual(zone_for_area("Cyclops Lane"), CYCLOPS)
        self.assertEqual(zone_for_area(" Firecat Alley "), FIRECAT)
        self.assertIsNone(zone_for_area("Wizard City Library"))
        self.assertIsNone(zone_for_area(None))


class TowerTest(unittest.TestCase):
    def test_a_tower_floor_is_a_dungeon_named_for_a_tower(self):
        from wizardtraining.training import in_dungeon, in_tower
        golem = "WizardCity/WC_Streets/WC_Golem_Tower/WC_Golem_Tower_3"
        interior = "WizardCity/WC_Streets/Interiors/WC_OldeTown_T2"
        self.assertTrue(in_tower(golem, []) and in_dungeon(golem, []))
        self.assertFalse(in_tower(interior, []))
        self.assertTrue(in_dungeon(interior, []))
        self.assertFalse(in_tower("Krokotopia/KT_Pyramid/KT_Chamber", []))


class TravelButtonsAllowedTest(unittest.TestCase):
    def test_dungeons_are_refilled_in_place_unless_trips_out_are_allowed(self):
        from wizardtraining.training import travel_buttons_allowed
        street, dungeon = "WizardCity/WC_Streets/WC_Cyclops", "WizardCity/WC_Streets/Interiors/WC_Cyclops_T1"
        golem = "WizardCity/WC_Streets/WC_Golem_Tower/WC_Golem_Tower_3"
        on = {"use_travel_buttons": True, "leave_dungeons": False}
        self.assertTrue(travel_buttons_allowed(street, [], [], **on))
        self.assertFalse(travel_buttons_allowed(dungeon, [], [], **on))
        self.assertTrue(travel_buttons_allowed(dungeon, [], [], use_travel_buttons=True, leave_dungeons=True))
        self.assertFalse(travel_buttons_allowed(dungeon, [], [dungeon], use_travel_buttons=True, leave_dungeons=True))
        self.assertFalse(travel_buttons_allowed(golem, [], [], use_travel_buttons=True, leave_dungeons=True))
        self.assertFalse(travel_buttons_allowed(street, [], [], use_travel_buttons=False, leave_dungeons=True))


if __name__ == "__main__":
    unittest.main()
