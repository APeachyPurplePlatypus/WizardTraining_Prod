import struct
import unittest

from wizardtraining.placed import PlacedObject
from wizardtraining.untracked import TriggerVolume, parse_trigger_volumes, quest_words, spots_for_goal, volumes_for_quest

COGS = [PlacedObject("WC_TA_Cog", -18329, -6218, 0), PlacedObject("WC_TA_Cog", -24108, -7450, 1)]
COG_GOAL = {"type": "usage", "tags": ["WC_TA_Cog", "Ddl_WC_TA_Cogs"], "name_key": "WizardQuestGoals_Collect"}
SMITH_GOAL = {"type": "waypoint", "tags": [], "name_key": "WizardQuestGoals_Explore",
              "destination_zone": "WizardCity/WC_Shop_Area"}
SHOP_AREA_PLACED = [PlacedObject("WC_GateShop_ToCommons", 0, 0, 0), PlacedObject("ExploreObject_WC", -1778, 424, 0)]
SHOP_AREA_VOLUMES = [TriggerVolume("Amulete_ShopBell_ Volume", 100, 100, 0),
                     TriggerVolume("Shopping District Smith", -1789, 403, 0)]


def volume_record(name: bytes, x: float, y: float, z: float) -> bytes:
    """A name record as volumes.xml stores it: a byte of twice the name's length, the name, then x, y and z at 8, 20
    and 32 bytes past the name."""
    body = bytearray(40)
    struct.pack_into("<f", body, 8, x)
    struct.pack_into("<f", body, 20, y)
    struct.pack_into("<f", body, 32, z)
    return bytes([2 * len(name)]) + name + bytes(body)


class TriggerVolumeTest(unittest.TestCase):
    def test_a_volume_with_an_enter_event_is_read_by_its_center(self):
        enter = b"Enter_Colossus Boulevard Smith"
        data = (b"\x00" * 8 + volume_record(b"Colossus Boulevard Smith", 39950.0, 10837.0, -620.0) + b"\x00" * 8
                + bytes([2 * len(enter)]) + enter + b"\x00" * 8)
        self.assertEqual(parse_trigger_volumes(data), [TriggerVolume("Colossus Boulevard Smith", 39950.0, 10837.0, -620.0)])


class WalkInTeleportTest(unittest.TestCase):
    def test_a_volume_named_for_where_it_leads_is_a_walk_in_teleport(self):
        from wizardtraining.untracked import walk_in_teleports
        volumes = [TriggerVolume("Activator Volume To_Kraken", -11055, 265, -675),
                   TriggerVolume("Activator Volume Kraken", -13969, 208, -1994),
                   TriggerVolume("TeleportVol_Teleport location (Tele Up)", -16336, 1176, 0),
                   TriggerVolume("Triton Avenue Smith", -15946, -4534, -1400)]
        self.assertEqual([volume.name for volume in walk_in_teleports(volumes)], ["Activator Volume To_Kraken"])


class QuestWordsTest(unittest.TestCase):
    def test_telling_words_and_their_singulars(self):
        self.assertEqual(quest_words("Find the Smiths"), {"smiths", "smith"})
        self.assertEqual(volumes_for_quest(SHOP_AREA_VOLUMES, quest_words("Find the Smiths")), [SHOP_AREA_VOLUMES[1]])


class SpotsForGoalTest(unittest.TestCase):
    """Goals the quest arrow does not lead to: Triton Avenue's Cogs (by tag) and the Smiths (by trigger volume)."""

    def test_cogs_are_found_by_the_goals_tags_nearest_first(self):
        spots = spots_for_goal(COG_GOAL, quest_title="Clear as Crystal", tagged=COGS, placed=[], volumes=[],
                               me=(-25000, -7000))
        self.assertEqual([(spot.source, spot.placed) for spot in spots], [("tag", COGS[1]), ("tag", COGS[0])])

    def test_a_used_cog_is_left_out(self):
        spots = spots_for_goal(COG_GOAL, quest_title="Clear as Crystal", tagged=COGS, placed=[], volumes=[],
                               me=(0, 0), visited=[COGS[0].key])
        self.assertEqual([spot.placed for spot in spots], [COGS[1]])

    def test_a_smith_is_found_by_its_trigger_volume_before_the_explore_object(self):
        spots = spots_for_goal(SMITH_GOAL, quest_title="Find the Smiths", tagged=[], placed=SHOP_AREA_PLACED,
                               volumes=SHOP_AREA_VOLUMES, me=(0, 0))
        self.assertEqual([(spot.name, spot.source) for spot in spots], [("Shopping District Smith", "trigger volume")])

    def test_a_tried_spot_gives_way_to_the_next_source(self):
        spots = spots_for_goal(SMITH_GOAL, quest_title="Find the Smiths", tagged=[], placed=SHOP_AREA_PLACED,
                               volumes=SHOP_AREA_VOLUMES, me=(0, 0), tried={"-1789,403"})
        self.assertEqual([(spot.name, spot.source) for spot in spots], [("ExploreObject_WC", "explore object")])
        self.assertEqual(spots_for_goal(SMITH_GOAL, quest_title="Find the Smiths", tagged=[], placed=SHOP_AREA_PLACED,
                                        volumes=SHOP_AREA_VOLUMES, me=(0, 0), tried={"-1789,403", "-1778,424"}), [])


if __name__ == "__main__":
    unittest.main()
