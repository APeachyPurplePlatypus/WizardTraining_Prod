import unittest

from wizardtraining.travelplan import (GO_HOME, RECALL, TRAVEL_MANA_RESERVE, WALK, TravelCosts, choose_travel,
                                       link_zones, spare_mana, worth_a_way_back_mark, zone_hops)

HUB, ALTAR = "Krokotopia/KT_Hub", "Krokotopia/KT_Pyramid/KT_AltarOfKings"
CHAMBER, PALACE = "Krokotopia/KT_Pyramid/KT_Chamber", "Krokotopia/KT_Pyramid/KT_PalaceOfFire"


def pyramid():
    links = {}
    for one, other in ((HUB, ALTAR), (ALTAR, CHAMBER), (ALTAR, PALACE)):
        link_zones(links, one, other)
    return links


def choose(here, goal_zone, door_distance, marked_in=None, mana=80, go_home_ready=True, recall_ready=True):
    return choose_travel(here=here, goal_zone=goal_zone, door_distance=door_distance, links=pyramid(), hub=HUB,
                         marked_in=marked_in, mana=mana, costs=TravelCosts(), go_home_ready=go_home_ready,
                         recall_ready=recall_ready)


class TravelPlanTest(unittest.TestCase):
    def test_zones_are_linked_both_ways_and_counted_in_doors(self):
        links = pyramid()
        self.assertEqual(zone_hops(links, CHAMBER, HUB), 2)
        self.assertEqual(zone_hops(links, PALACE, CHAMBER), 2)
        self.assertEqual(zone_hops(links, HUB, HUB), 0)
        self.assertIsNone(zone_hops(links, HUB, "Krokotopia/KT_Unknown"))

    def test_go_home_for_a_goal_in_the_hub_from_deep_in_the_pyramid(self):
        choice = choose(PALACE, HUB, door_distance=20000)
        self.assertEqual(choice.way, GO_HOME)
        self.assertIn("go home ~", choice.describe(PALACE, HUB))

    def test_walk_when_the_door_is_near_and_a_teleport_saves_little(self):
        self.assertEqual(choose(CHAMBER, ALTAR, door_distance=2000).way, WALK)

    def test_recall_back_to_the_mark_in_the_goals_zone(self):
        self.assertEqual(choose(HUB, CHAMBER, door_distance=3000, marked_in=CHAMBER).way, RECALL)

    def test_no_recall_without_mana_to_spare_or_while_cooling_down(self):
        self.assertNotEqual(choose(HUB, CHAMBER, door_distance=3000, marked_in=CHAMBER, mana=TRAVEL_MANA_RESERVE).way,
                            RECALL)
        self.assertNotEqual(choose(HUB, CHAMBER, door_distance=3000, marked_in=CHAMBER, recall_ready=False).way, RECALL)

    def test_an_unknown_way_on_foot_takes_only_a_teleport_into_the_goals_zone(self):
        self.assertEqual(choose("Krokotopia/KT_Unknown", HUB, door_distance=500).way, GO_HOME)
        self.assertEqual(choose("Krokotopia/KT_Unknown", CHAMBER, door_distance=500).way, WALK)

    def test_costs_learn_from_measurements(self):
        costs = TravelCosts(walk_speed=360.0)
        costs.learn("walk_speed", 460.0)
        self.assertAlmostEqual(costs.walk_speed, 390.0)
        self.assertEqual(TravelCosts.from_dict({"walk_speed": 400.0, "unknown": 1}).walk_speed, 400.0)

    def test_the_way_back_is_marked_when_leaving_a_finished_goals_zone_far_from_the_hub(self):
        links = pyramid()
        self.assertTrue(worth_a_way_back_mark(PALACE, PALACE, CHAMBER, HUB, links, None, 80))
        self.assertFalse(worth_a_way_back_mark(PALACE, PALACE, PALACE, HUB, links, None, 80))
        self.assertFalse(worth_a_way_back_mark(ALTAR, ALTAR, CHAMBER, HUB, links, None, 80))
        self.assertFalse(worth_a_way_back_mark(PALACE, PALACE, CHAMBER, HUB, links, PALACE, 80))
        self.assertFalse(worth_a_way_back_mark(PALACE, PALACE, CHAMBER, HUB, links, None, 20))
        self.assertFalse(spare_mana(TRAVEL_MANA_RESERVE))


if __name__ == "__main__":
    unittest.main()
