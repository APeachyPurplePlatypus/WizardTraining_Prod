import math
import unittest

from wizardtraining.targets import (ENEMY_CLEARANCE, STEP_AWAY_DISTANCE, bystanders, escape_point, measured, others,
                                    quest_targets, too_close)


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

    def test_escape_point_leads_directly_away(self):
        point = escape_point((0, 0), [enemy(1, "Ghost", 100, 0)])
        self.assertAlmostEqual(point[0], -STEP_AWAY_DISTANCE)
        self.assertAlmostEqual(point[1], 0)
        between = escape_point((0, 0), [enemy(1, "a", 100, 0), enemy(2, "b", 0, 100)])
        self.assertAlmostEqual(math.dist(between, (0, 0)), STEP_AWAY_DISTANCE)
        self.assertLess(between[0], 0)
        self.assertLess(between[1], 0)


if __name__ == "__main__":
    unittest.main()
