import math
import unittest

from wizardtraining.routes import ENEMY_KEEP_OUT
from wizardtraining.targets import (AFTER_BATTLE_GRACE_SECONDS, ENEMY_CLEARANCE, WISP_DETOUR, WISP_REACH,
                                    back_away, bystanders, detour, enemies_to_route_around, in_grace_after_battle,
                                    is_duel_circle, is_dungeon_entrance, keeps_blocking, measured,
                                    next_area_to_explore, others, quest_targets,
                                    refill_reach, safe_wisps, threat_centre, too_close)


def enemy(id_, name, x, y):
    return {"id": id_, "name": name, "position": (x, y)}


class TargetsTest(unittest.TestCase):
    def setUp(self):
        self.enemies = measured([enemy(1, "Ghost", 1000, 0), enemy(2, "Ghost", 300, 0), enemy(3, "Pirate", 5000, 0)],
                                me=(0, 0), duel_circles=[(5100, 0)])

    def test_measured_sorts_by_distance_and_marks_duels(self):
        self.assertEqual([e["id"] for e in self.enemies], [2, 1, 3])
        self.assertEqual([e["in_a_duel"] for e in self.enemies], [False, False, True])

    def test_a_fight_in_progress_is_a_duel_circle_with_its_fighters_seated_round_it(self):
        self.assertTrue(is_duel_circle("Duel Circle"))
        self.assertFalse(is_duel_circle("Ghost-Blue-L02-B"))
        seated = measured([enemy(1, "Ghost", 600, 0)], me=(3000, 3000), duel_circles=[(0, 0)])
        self.assertTrue(seated[0]["in_a_duel"])

    def test_a_tower_or_dungeon_entrance_is_its_semicircle(self):
        self.assertTrue(is_dungeon_entrance("Teleport Semi Circle 4 Player Generic"))
        self.assertFalse(is_dungeon_entrance("TeleportVol_Teleport-Foulgaze"))
        self.assertFalse(is_dungeon_entrance("Duel Circle"))

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

    def test_with_a_heading_only_wisps_on_the_way_count(self):
        wisps = [{"id": "behind", "position": (-1500, 0)}, {"id": "ahead", "position": (1500, 300)},
                 {"id": "aside", "position": (0, 1400)}]
        found = safe_wisps(wisps, me=(0, 0), enemies=[], duel_circles=[], heading=(10000, 0))
        self.assertEqual([wisp["id"] for wisp in found], ["ahead"])
        self.assertLessEqual(detour((0, 0), (1500, 300), (10000, 0)), WISP_DETOUR)
        self.assertGreater(detour((0, 0), (-1500, 0), (10000, 0)), WISP_DETOUR)
        anywhere = safe_wisps(wisps, me=(0, 0), enemies=[], duel_circles=[])
        self.assertEqual({wisp["id"] for wisp in anywhere}, {"behind", "ahead", "aside"})

    def test_reach_can_be_widened(self):
        far = [{"id": "far", "position": (WISP_REACH * 3, 0)}]
        self.assertEqual(safe_wisps(far, me=(0, 0), enemies=[], duel_circles=[]), [])
        self.assertEqual(len(safe_wisps(far, me=(0, 0), enemies=[], duel_circles=[], reach=math.inf)), 1)

    def test_a_refill_reaches_any_wisp_only_in_a_zone_without_enemies(self):
        far = [{"id": "far", "position": (WISP_REACH * 3, 0)}]
        self.assertEqual(safe_wisps(far, me=(0, 0), enemies=[], duel_circles=[], reach=refill_reach(False)), [])
        self.assertEqual(len(safe_wisps(far, me=(0, 0), enemies=[], duel_circles=[], reach=refill_reach(True))), 1)

    def test_next_area_to_explore_is_the_nearest_not_yet_explored(self):
        points = [((0, 5000), 0), ((0, 1000), 0), ((0, 3000), 1)]
        self.assertEqual(next_area_to_explore(points, me=(0, 0)), ((0, 1000), 0))
        self.assertEqual(next_area_to_explore(points, me=(0, 0), explored=[(0, 1000)]), ((0, 3000), 1))
        self.assertIsNone(next_area_to_explore(points, me=(0, 0), explored=[(0, 1000), (0, 3000), (0, 5000)]))

    def test_preferred_pieces_are_explored_first(self):
        points = [((0, 5000), 0), ((0, 1000), 0), ((0, 3000), 1)]
        self.assertEqual(next_area_to_explore(points, me=(0, 0), prefer={1}), ((0, 3000), 1))
        self.assertEqual(next_area_to_explore(points, me=(0, 0), explored=[(0, 3000)], prefer={1}), ((0, 1000), 0))

    def test_routes_go_around_enemies_but_not_those_at_either_end(self):
        enemies = [enemy(1, "Ghoul", 3000, 0), enemy(2, "Ghoul", 200, 0), enemy(3, "Ghoul", 6000, 300)]
        around = enemies_to_route_around(enemies, me=(0, 0), destination=(6000, 0))
        self.assertEqual([each["id"] for each in around], [1])
        self.assertGreater(ENEMY_KEEP_OUT, ENEMY_CLEARANCE)

    def test_grace_after_battle(self):
        self.assertFalse(in_grace_after_battle(None, now=100))
        self.assertTrue(in_grace_after_battle(100, now=100 + AFTER_BATTLE_GRACE_SECONDS - 0.1))
        self.assertFalse(in_grace_after_battle(100, now=100 + AFTER_BATTLE_GRACE_SECONDS))

    def test_enemies_keep_blocking_after_three_recent_step_aways(self):
        self.assertFalse(keeps_blocking([10, 20], now=30))
        self.assertTrue(keeps_blocking([10, 20, 25], now=30))
        self.assertFalse(keeps_blocking([10, 20, 25], now=200))

    def test_threat_centre_is_the_average_position(self):
        self.assertEqual(threat_centre([enemy(1, "a", 0, 0), enemy(2, "b", 100, 50)]), (50.0, 25.0))

    def test_back_away_when_the_threat_is_in_front(self):
        self.assertTrue(back_away(1.0, 1.2))
        self.assertTrue(back_away(0.1, 2 * math.pi - 0.1))
        self.assertFalse(back_away(1.0, 1.0 + math.pi))
        self.assertFalse(back_away(0.0, 2.0))


if __name__ == "__main__":
    unittest.main()
