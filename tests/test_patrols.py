import struct
import unittest

from wizardtraining.patrols import PatrolMap, is_enemy_path, parse_nodes, parse_paths


def node_record(node_id: int, x: float, y: float, z: float) -> bytes:
    record = bytearray(92)
    struct.pack_into("<fff", record, 36, x, y, z)
    struct.pack_into("<I", record, 68, node_id)
    return bytes(record)


def path_entry(name: str, ids: list[int]) -> bytes:
    entry = bytearray(name.encode("ascii") + b"`")
    for node_id in ids:
        entry += b"\x00" + struct.pack("<I", node_id) + b"\x00\x00\x00"
    return bytes(entry)


class ParseTest(unittest.TestCase):
    def test_reads_node_positions_and_ids(self):
        nodes = parse_nodes(node_record(1, 3903.7, -6713.0, 29.7) + node_record(2, 2201.0, -6726.1, 28.8))
        self.assertEqual(sorted(nodes), [1, 2])
        self.assertAlmostEqual(nodes[2][0], 2201.0, places=1)

    def test_reads_each_paths_node_ids(self):
        paths = parse_paths(path_entry("Path 10_Screamer", [388, 389, 390]) + path_entry("Path Wisps 01", [1, 2]))
        self.assertEqual(paths["Path 10_Screamer"], [388, 389, 390])
        self.assertEqual(paths["Path Wisps 01"], [1, 2])

    def test_enemy_paths(self):
        self.assertTrue(is_enemy_path("Path 10_Screamer"))
        self.assertTrue(is_enemy_path("Path 15"))
        self.assertFalse(is_enemy_path("Path Wisps 01"))
        self.assertFalse(is_enemy_path("Path_Flax_02"))
        self.assertFalse(is_enemy_path("Path_SilverChest_01"))


class PatrolMapTest(unittest.TestCase):
    def test_distance_to_the_nearest_patrol(self):
        nodes = {1: (0, 0, 0), 2: (1000, 0, 0), 3: (5000, 5000, 0)}
        patrols = PatrolMap.from_paths(nodes, {"Path 01_Eels": [1, 2], "Path Wisps 01": [3]})
        self.assertLess(patrols.distance((500, 30), 2000), 31)
        self.assertEqual(patrols.distance((5000, 5000), 2000), 2000)
        self.assertEqual(len(patrols.segments), 1)


if __name__ == "__main__":
    unittest.main()
