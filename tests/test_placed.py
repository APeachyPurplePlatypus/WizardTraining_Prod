import struct
import unittest

from wizardtraining.placed import (PlacedObject, gate_toward, objects_for_goal, parse_named_objects, parse_placed_objects,
                                  words)


def placed_bytes(name: str, x: float, y: float, z: float) -> bytes:
    before = bytearray(60)
    for offset, value in ((54, x), (50, y), (46, z)):
        struct.pack_into("<f", before, len(before) - offset, value)
    encoded = name.encode("ascii")
    return bytes(before[:-2]) + struct.pack("<H", len(encoded)) + encoded + b"\x00" * 8


class ParseTest(unittest.TestCase):
    def test_an_explore_goal_goes_to_the_zones_one_explore_object(self):
        from wizardtraining.placed import explore_spot
        spot = PlacedObject("ExploreObject_WC", -5089, -2734, 253)
        placed = [PlacedObject("WC_GateCommons_ToRavenWood", 0, 0, 0), spot]
        goal = {"name_key": "WizardQuestGoals_Explore", "type": "waypoint", "destination_zone": "WizardCity/WC_Hub",
                "tags": []}
        self.assertEqual(explore_spot(placed, goal), spot)
        self.assertIsNone(explore_spot(placed, {**goal, "name_key": "WizardQuestGoals_Other"}))
        self.assertIsNone(explore_spot(placed + [PlacedObject("ExploreObject_WC", 1, 1, 0)], goal))

    def test_reads_templates_and_positions(self):
        data = (placed_bytes("WC_TA_Cog instance", -18329.4, -6217.8, 0.5)
                + placed_bytes("WC_TA_LuminaCrystals instance (1)", 1544.5, -792.1, -151.1))
        placed = parse_placed_objects(data)
        self.assertEqual([thing.template for thing in placed], ["WC_TA_Cog", "WC_TA_LuminaCrystals"])
        self.assertAlmostEqual(placed[0].x, -18329.4, places=1)
        self.assertAlmostEqual(placed[1].z, -151.1, places=1)

    def test_reads_gates_named_without_the_instance_suffix(self):
        """The Commons' gates: "WC_GateCommons_ToRavenWood" is followed by a letter of the next field."""
        data = (placed_bytes("WC_GateCommons_ToRavenWood", -93.2, 1992.5, 223.1)[:-8] + b"P\x00\x00"
                + placed_bytes("WC-GateStreet_TritonLane instance", -7550.0, -388.0, -1398.0))
        placed = parse_placed_objects(data)
        self.assertEqual([thing.template for thing in placed], ["WC_GateCommons_ToRavenWood", "WC-GateStreet_TritonLane"])
        self.assertAlmostEqual(placed[0].y, 1992.5, places=1)
        self.assertEqual(gate_toward(placed, "WizardCity/WC_Ravenwood").template, "WC_GateCommons_ToRavenWood")

    def test_skips_names_with_a_wrong_length(self):
        good = placed_bytes("WC_TA_Cog instance", 1, 2, 3)
        broken = good.replace(struct.pack("<H", 18), struct.pack("<H", 5))
        self.assertEqual(parse_placed_objects(broken), [])


class NamedObjectsTest(unittest.TestCase):
    def test_reads_objects_stored_under_a_goal_tag_without_the_instance_suffix(self):
        data = (placed_bytes("WC_PetDirtMound-Cyclops1", -8829.7, 6869.2, 86.2)
                + placed_bytes("WC_PetDirtMound-Cyclops2", -7006.5, 17048.0, 33.5)
                + placed_bytes("WC_TA_Cog instance", 1, 2, 3))
        self.assertEqual(parse_placed_objects(data), [PlacedObject("WC_TA_Cog", 1.0, 2.0, 3.0)])
        found = parse_named_objects(data, ["WC_PetDirtMound-Cyclops2"])
        self.assertEqual([thing.template for thing in found], ["WC_PetDirtMound-Cyclops2"])
        self.assertAlmostEqual(found[0].x, -7006.5, places=1)
        self.assertAlmostEqual(found[0].y, 17048.0, places=1)

    def test_a_name_inside_a_longer_one_is_not_that_object(self):
        data = placed_bytes("WC_PetDirtMound-Cyclops22", 1, 2, 3)
        self.assertEqual(parse_named_objects(data, ["WC_PetDirtMound-Cyclops2"]), [])


class GoalObjectsTest(unittest.TestCase):
    cogs = [PlacedObject("WC_TA_Cog", -18329, -6218, 0), PlacedObject("WC_TA_Cog", -24108, -7450, 1),
            PlacedObject("WC_Leverl_Mill", -18922, -846, 97)]

    def test_matches_the_goals_tags_nearest_first(self):
        found = objects_for_goal(self.cogs, ["WC_TA_Cog", "Ddl_WC_TA_Cogs"], me=(-25000, -7000))
        self.assertEqual([(thing.x, thing.y) for thing in found], [(-24108, -7450), (-18329, -6218)])

    def test_leaves_out_visited_objects(self):
        found = objects_for_goal(self.cogs, ["WC_TA_Cog"], me=(0, 0), visited=[self.cogs[0].key])
        self.assertEqual(found, [self.cogs[1]])
        self.assertEqual(objects_for_goal(self.cogs, ["Nothing"], me=(0, 0)), [])


class GateTest(unittest.TestCase):
    gates = [PlacedObject("WC-GateStreet_FireCatAlley", -12284, -1806, -2199),
             PlacedObject("WC-GateStreet_TritonLane", -7550, -388, -1398),
             PlacedObject("WC-GateStreet_CyclopsLane", -5495, 3230, -598), PlacedObject("WC_TA_Cog", 0, 0, 0)]

    def test_words(self):
        self.assertEqual(words("WC-GateStreet_TritonLane"), {"wc", "gate", "street", "triton", "lane"})

    def test_finds_the_gate_named_like_the_zone(self):
        self.assertEqual(gate_toward(self.gates, "WizardCity/WC_Streets/WC_Triton").template, "WC-GateStreet_TritonLane")

    def test_falls_back_to_the_gate_nearest_the_arrival(self):
        self.assertEqual(gate_toward(self.gates, "WizardCity/WC_Streets/WC_Elsewhere", arrival=(-6000, 3000)).template,
                         "WC-GateStreet_CyclopsLane")
        self.assertIsNone(gate_toward(self.gates, "WizardCity/WC_Streets/WC_Elsewhere"))


if __name__ == "__main__":
    unittest.main()
