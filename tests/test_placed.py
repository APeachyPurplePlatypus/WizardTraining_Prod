import struct
import unittest

from wizardtraining.placed import PlacedObject, objects_for_goal, parse_placed_objects


def placed_bytes(name: str, x: float, y: float, z: float) -> bytes:
    before = bytearray(60)
    for offset, value in ((54, x), (50, y), (46, z)):
        struct.pack_into("<f", before, len(before) - offset, value)
    encoded = name.encode("ascii")
    return bytes(before[:-2]) + struct.pack("<H", len(encoded)) + encoded + b"\x00" * 8


class ParseTest(unittest.TestCase):
    def test_reads_templates_and_positions(self):
        data = (placed_bytes("WC_TA_Cog instance", -18329.4, -6217.8, 0.5)
                + placed_bytes("WC_TA_LuminaCrystals instance (1)", 1544.5, -792.1, -151.1))
        placed = parse_placed_objects(data)
        self.assertEqual([thing.template for thing in placed], ["WC_TA_Cog", "WC_TA_LuminaCrystals"])
        self.assertAlmostEqual(placed[0].x, -18329.4, places=1)
        self.assertAlmostEqual(placed[1].z, -151.1, places=1)

    def test_skips_names_with_a_wrong_length(self):
        good = placed_bytes("WC_TA_Cog instance", 1, 2, 3)
        broken = good.replace(struct.pack("<H", 18), struct.pack("<H", 5))
        self.assertEqual(parse_placed_objects(broken), [])


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


if __name__ == "__main__":
    unittest.main()
