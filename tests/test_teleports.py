import struct
import unittest

from wizardtraining.teleports import (LEFT_ZONE, NO_EFFECT, TeleportVolume, choose_crossing, describe_outcome,
                                      parse_teleport_volumes, volume_at)


def volume_bytes(name: str, x: float, y: float, z: float, radius: float, *, enter_event: bool = False) -> bytes:
    stored = (b"Enter_" if enter_event else b"") + name.encode("ascii")
    after = bytearray(64)
    for offset, value in ((8, x), (20, y), (32, z), (60, radius)):
        struct.pack_into("<f", after, offset, value)
    return b"\x00\x01" + bytes([len(stored) * 2]) + stored + bytes(after)


class ParseTest(unittest.TestCase):
    def test_reads_names_positions_and_radii(self):
        data = (volume_bytes("TeleportVol_Teleport location (Tele Up)", -16336.1, 1175.9, -1389.5, 177.4)
                + volume_bytes("TeleportVol_Teleport location (Tele Down)", -17513.7, 1145.2, -289.4, 188.4))
        volumes = parse_teleport_volumes(data)
        self.assertEqual([volume.name for volume in volumes],
                         ["TeleportVol_Teleport location (Tele Up)", "TeleportVol_Teleport location (Tele Down)"])
        self.assertAlmostEqual(volumes[0].x, -16336.1, places=1)
        self.assertAlmostEqual(volumes[1].radius, 188.4, places=1)

    def test_skips_enter_events_and_implausible_values(self):
        data = (volume_bytes("TeleportVol_Teleport x", 1, 2, 3, 100, enter_event=True)
                + volume_bytes("TeleportVol_Teleport y", 1e9, 2, 3, 100)
                + volume_bytes("TeleportVol_Teleport z", 1, 2, 3, 0.5))
        self.assertEqual(parse_teleport_volumes(data), [])


class CrossingTest(unittest.TestCase):
    up = TeleportVolume("Tele Up", -16336, 1176, -1389, 177)
    exit_ = TeleportVolume("Street2 Exit", 6, 2477, 40, 312)
    down = TeleportVolume("Tele Down", -17514, 1145, -289, 188)
    volumes = [(up, 1), (exit_, 1), (down, 0)]
    goal = (-28833, -8171)

    def choose(self, outcomes=None):
        return choose_crossing(self.volumes, start_piece=1, goal_piece=0, outcomes=outcomes or {}, goal=self.goal)

    def test_tries_the_untried_volume_in_the_wizards_piece_nearest_the_goal(self):
        self.assertEqual(self.choose(), self.up)

    def test_never_retries_one_that_left_the_zone_or_did_nothing(self):
        self.assertEqual(self.choose({"Tele Up": LEFT_ZONE}), self.exit_)
        self.assertIsNone(self.choose({"Tele Up": NO_EFFECT, "Street2 Exit": LEFT_ZONE}))

    def test_prefers_one_known_to_land_in_the_goals_piece(self):
        self.assertEqual(self.choose({"Tele Up": 0, "Street2 Exit": 7}), self.up)
        self.assertEqual(self.choose({"Tele Up": 3}), self.exit_)

    def test_follows_a_known_chain_out_of_a_piece_with_nothing_left_to_try(self):
        high_ledge = TeleportVolume("High_Ledge", -10541, -6779, 0, 150)
        volumes = [(high_ledge, 32), (self.down, 0), (self.up, 20), (self.exit_, 20)]
        outcomes = {"High_Ledge": 0, "Tele Down": 20}
        self.assertEqual(choose_crossing(volumes, start_piece=32, goal_piece=20, outcomes=outcomes,
                                         goal=(6, 2477)), high_ledge)
        self.assertEqual(choose_crossing(volumes, start_piece=0, goal_piece=20, outcomes=outcomes,
                                         goal=(6, 2477)), self.down)

    def test_goes_where_something_is_left_to_try(self):
        high_ledge = TeleportVolume("High_Ledge", -10541, -6779, 0, 150)
        volumes = [(high_ledge, 32), (self.down, 0)]
        self.assertEqual(choose_crossing(volumes, start_piece=32, goal_piece=20, outcomes={"High_Ledge": 0},
                                         goal=(6, 2477)), high_ledge)
        self.assertIsNone(choose_crossing(volumes, start_piece=32, goal_piece=20,
                                          outcomes={"High_Ledge": 0, "Tele Down": NO_EFFECT}, goal=(6, 2477)))

    def test_describe_outcome(self):
        self.assertEqual(describe_outcome(0), "landed in walkable piece 0")
        self.assertEqual(describe_outcome(None), "landed outside the known walkable area")
        self.assertEqual(describe_outcome(LEFT_ZONE), LEFT_ZONE)


class DoorTest(unittest.TestCase):
    def test_finds_the_volume_an_arrow_points_at(self):
        exit_volume = TeleportVolume("TeleportVol_ToStreet5", 760.0, 30.0, 0.0, 100.0)
        far = TeleportVolume("TeleportVol_Up", 5000.0, 0.0, 0.0, 100.0)
        self.assertEqual(volume_at([far, exit_volume], (677.9, 28.2)), exit_volume)
        self.assertIsNone(volume_at([far, exit_volume], (400.0, 28.2)))
        self.assertIsNone(volume_at([], (677.9, 28.2)))


if __name__ == "__main__":
    unittest.main()
