import math
import unittest

from wizardtraining.targets import (ENEMY_CLEARANCE, WISP_REACH, back_away, bystanders, measured, next_area_to_explore,
                                    others, quest_targets, safe_wisps, still_worth_dodging, threat_centre, too_close)


def enemy(id_, name, x, y):
    return {"id": id_, "name": name, "position": (x, y)}


class TargetsTest(unittest.TestCase):
    def setUp(self):
        self.enemies = measured([enemy(1, "Ghost", 1000, 0), enemy(2, "Ghost", 300, 0), enemy(3, "Pirate", 5000, 0)],
                                me=(0, 0), duel_circles=[(5100, 0)])

    def test_measured_sorts_by_distance_and_marks_duels(self):
        self.assertEqual([e["id"] for e in self.enemies], [2, 1, 3])
        self.assertEqual([e["in_a_duel"] for e in self.enemies], [False, False, True])

    def test_quest_targets_are_near_the_arrow_and_not_in_a_duel(self):
        self.assertEqual([e["id"] for e in quest_targets(self.enemies, arrow=(900, 0))], [2, 1])
        self.assertEqual(quest_targets(self.enemies, arrow=(5000, 0)), [])

    def test_bystanders_are_everyone_but_the_targets(self):
        targets = quest_targets(self.enemies, arrow=(1000, 0))
        self.assertEqual([e["id"] for e in bystanders(self.enemies, targets)], [3])

    def test_others_ignores_by_name(self):
        self.assertEqual([e["name"] for e in others(self.enemies, ignore=[{"name": "Ghost"}])], ["Pirate"])

    def test_too_close(self):
        self.assertEqual([e["id"] for e in too_close(self.enemies)], [2])
        self.assertLess(300, ENEMY_CLEARANCE)

    def test_safe_wisps_are_near_clear_untried_and_nearest_first(self):
        wisps = [{"id": "far", "position": (WISP_REACH + 1, 0)}, {"id": "guarded", "position": (1000, 0)},
                 {"id": "duel", "position": (0, 2000)}, {"id": "tried", "position": (0, -300)},
                 {"id": "near", "position": (0, 500)}, {"id": "nearer", "position": (0, -200)}]
        found = safe_wisps(wisps, me=(0, 0), enemies=[enemy(1, "Eel", 1100, 0)], duel_circles=[(0, 2100)],
                           tried=["tried"])
        self.assertEqual([wisp["id"] for wisp in found], ["nearer", "near"])

    def test_next_area_to_explore_is_the_nearest_not_yet_explored(self):
        points = [((0, 5000), 0), ((0, 1000), 0), ((0, 3000), 1)]
        self.assertEqual(next_area_to_explore(points, me=(0, 0)), ((0, 1000), 0))
        self.assertEqual(next_area_to_explore(points, me=(0, 0), explored=[(0, 1000)]), ((0, 3000), 1))
        self.assertIsNone(next_area_to_explore(points, me=(0, 0), explored=[(0, 1000), (0, 3000), (0, 5000)]))

    def test_preferred_pieces_are_explored_first(self):
        points = [((0, 5000), 0), ((0, 1000), 0), ((0, 3000), 1)]
        self.assertEqual(next_area_to_explore(points, me=(0, 0), prefer={1}), ((0, 3000), 1))
        self.assertEqual(next_area_to_explore(points, me=(0, 0), explored=[(0, 3000)], prefer={1}), ((0, 1000), 0))

    def test_an_enemy_dodged_often_is_faced_when_healthy(self):
        self.assertTrue(still_worth_dodging([10, 20], now=30, health=0.9))
        self.assertFalse(still_worth_dodging([10, 20, 25], now=30, health=0.9))
        self.assertTrue(still_worth_dodging([10, 20, 25], now=30, health=0.3))
        self.assertTrue(still_worth_dodging([10, 20, 25], now=200, health=0.9))
        self.assertTrue(still_worth_dodging([10, 20, 25], now=30, health=None))

    def test_threat_centre_is_the_average_position(self):
        self.assertEqual(threat_centre([enemy(1, "a", 0, 0), enemy(2, "b", 100, 50)]), (50.0, 25.0))

    def test_back_away_when_the_threat_is_in_front(self):
        self.assertTrue(back_away(1.0, 1.2))
        self.assertTrue(back_away(0.1, 2 * math.pi - 0.1))
        self.assertFalse(back_away(1.0, 1.0 + math.pi))
        self.assertFalse(back_away(0.0, 2.0))


if __name__ == "__main__":
    unittest.main()
