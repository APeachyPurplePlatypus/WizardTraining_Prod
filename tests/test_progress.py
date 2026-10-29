import unittest

from wizardtraining.progress import (APPROACH_MARGIN, DUEL_BLOCKS_THE_WAY, ENEMY_NEAR_PATH, ENEMY_PATH_CLEARANCE, ENGAGE_HEALTH_FRACTION,
                                     ENGAGE_MANA_FRACTION, MEANINGFUL_TRAVEL_DISTANCE, LimitReached, Limits,
                                     PlannedRoute, RunRecord, StopRun, check_limits, health_for_a_fight, leaves_world,
                                     health_to_travel, mana_for_a_fight, mana_to_travel, still_to_recharge, worth_marking, worth_recalling, parked, nav_did_better, progressed, remember_obstacles,
                                     safe_to_stand, short_for_a_fight, should_drink_potion, stalled, topped_up,
                                     travel_outcome,
                                     ready_to_recall,
                                     wanted_wisp, world_of)


def record(**limits) -> RunRecord:
    return RunRecord(limits=Limits(**limits))


class NavDidBetterTest(unittest.TestCase):
    def test_collision_stuck_then_nav_walked_on(self):
        self.assertTrue(nav_did_better([{"method": "collision", "result": "failed"},
                                        {"method": "nav", "result": "interrupted"}]))
        self.assertFalse(nav_did_better([{"method": "collision", "result": "no route"},
                                         {"method": "nav", "result": "arrived"}]))
        self.assertFalse(nav_did_better([{"method": "collision", "result": "arrived"}]))

    def test_a_turn_that_would_not_settle_says_nothing_about_the_walk_data(self):
        self.assertFalse(nav_did_better([{"method": "collision", "result": "failed",
                                          "reason": "turn failed: facing did not converge"},
                                         {"method": "nav", "result": "arrived"}]))
        self.assertTrue(nav_did_better([{"method": "collision", "result": "failed",
                                         "reason": "stuck: sidesteps did not clear the obstacle"},
                                        {"method": "nav", "result": "arrived"}]))


class WorldTest(unittest.TestCase):
    def test_the_world_is_the_first_part_of_the_zone(self):
        self.assertEqual(world_of("WizardCity/WC_Streets/WC_Triton"), "WizardCity")
        self.assertIsNone(world_of(""))

    def test_a_goal_in_another_world_leaves_it(self):
        self.assertTrue(leaves_world("WizardCity/WC_Hub", "Krokotopia/KT_Hub"))
        self.assertFalse(leaves_world("WizardCity/WC_Hub", "WizardCity/WC_Streets/Interiors/WC_Triton_T1"))
        self.assertFalse(leaves_world("WizardCity/WC_Hub", ""))


class LimitsTest(unittest.TestCase):
    def check(self, run, seconds_left=60, stop_requested=False):
        check_limits(run, seconds_left=seconds_left, stop_requested=stop_requested)

    def test_a_fresh_run_may_continue(self):
        self.check(record())

    def test_each_limit_stops_the_run(self):
        with self.assertRaisesRegex(StopRun, "STOP"):
            self.check(record(), stop_requested=True)
        with self.assertRaisesRegex(StopRun, "time"):
            self.check(record(), seconds_left=0)
        run = record(max_turns=2)
        run.record_turn(progressed("a"))
        run.record_turn(progressed("b"))
        with self.assertRaisesRegex(StopRun, "turn limit"):
            self.check(run)
        run = record(max_battles=1)
        run.battles = 1
        with self.assertRaisesRegex(StopRun, "battle limit"):
            self.check(run)
        run = record(max_step_aways=1)
        run.step_aways.append(["Ghost", 300, False])
        with self.assertRaisesRegex(StopRun, "stepped away"):
            self.check(run)

    def test_planned_limits_may_finish_safely_but_the_stop_file_and_trouble_may_not(self):
        with self.assertRaises(LimitReached):
            self.check(record(), seconds_left=0)
        run = record(max_battles=1)
        run.battles = 1
        with self.assertRaises(LimitReached):
            self.check(run)
        for run, stop_requested in ((record(), True), (record(max_step_aways=0), False)):
            with self.assertRaises(StopRun) as caught:
                self.check(run, stop_requested=stop_requested)
            self.assertNotIsInstance(caught.exception, LimitReached)

    def test_turns_without_progress_stop_the_run_and_progress_resets_the_count(self):
        run = record(max_turns_without_progress=2)
        run.record_turn(stalled("a"))
        run.record_turn(progressed("b"))
        run.record_turn(stalled("c"))
        self.check(run)
        run.record_turn(stalled("d"))
        with self.assertRaisesRegex(StopRun, "without progress"):
            self.check(run)


class DoorLoopTest(unittest.TestCase):
    def test_zone_changes_count_until_the_quest_goal_changes(self):
        run = record(max_zone_changes_without_quest_change=2)
        for zone in ("Hub", "Shops", "Hub"):
            run.note_place(zone, ("quest", 1))
        check_limits(run, seconds_left=60, stop_requested=False)
        run.note_place("Shops", ("quest", 1))
        with self.assertRaisesRegex(StopRun, "back and forth"):
            check_limits(run, seconds_left=60, stop_requested=False)
        run.note_place("Shops", ("quest", 2))
        self.assertEqual(run.zone_changes_without_quest_change, 0)

    def test_staying_in_one_zone_is_not_a_zone_change(self):
        run = record()
        for _ in range(5):
            run.note_place("Hub", ("quest", 1))
        self.assertEqual(run.zone_changes_without_quest_change, 0)


class MenuLoopTest(unittest.TestCase):
    def test_menu_choices_count_until_the_quest_goal_changes(self):
        run = record(max_menu_choices_without_quest_change=2)
        run.note_menu_choice(("quest", (1,)))
        run.note_menu_choice(("quest", (1,)))
        check_limits(run, seconds_left=60, stop_requested=False)
        run.note_menu_choice(("quest", (1,)))
        with self.assertRaisesRegex(StopRun, "menu kept reopening"):
            check_limits(run, seconds_left=60, stop_requested=False)
        run.note_menu_choice(("quest", (2,)))
        self.assertEqual(run.menu_choices_without_quest_change, 1)


class TravelOutcomeTest(unittest.TestCase):
    def outcome(self, reason, moved, stops_in_a_row=0):
        run = record()
        run.immobile_threat_stops_in_a_row = stops_in_a_row
        return travel_outcome("travel", reason, moved, run)["progress"]

    def test_moving_is_progress(self):
        self.assertTrue(self.outcome("route took too long", MEANINGFUL_TRAVEL_DISTANCE))

    def test_arriving_where_it_already_stood_is_not_progress(self):
        self.assertFalse(self.outcome(None, 0))

    def test_a_state_change_is_progress(self):
        self.assertTrue(self.outcome("battle", 0))

    def test_details_are_kept_in_the_turn(self):
        turn = travel_outcome("travel", "arrived", 0, record(), trip={"moved": 0}, seen=[])
        self.assertEqual(turn["trip"], {"moved": 0})
        self.assertEqual(turn["seen"], [])

    def test_finding_an_obstacle_is_progress(self):
        self.assertTrue(travel_outcome("travel", "every route method failed", 0, record(), new_obstacles=1)["progress"])
        self.assertFalse(travel_outcome("travel", "every route method failed", 0, record())["progress"])

    def test_obstacles_per_zone_are_capped(self):
        run = record(max_obstacles_per_zone=2)
        self.assertEqual(remember_obstacles(run, "zone", [(1.2, 2.7), (3, 4), (5, 6)]), 2)
        self.assertEqual(run.obstacles["zone"], [(1, 3), (3, 4)])
        self.assertEqual(remember_obstacles(run, "zone", [(7, 8)]), 0)

    def test_waiting_for_an_enemy_counts_only_a_few_times(self):
        self.assertTrue(self.outcome(ENEMY_NEAR_PATH, 0, stops_in_a_row=1))
        self.assertFalse(self.outcome(ENEMY_NEAR_PATH, 0, stops_in_a_row=Limits().max_immobile_threat_stops_in_a_row + 1))

    def test_waiting_for_another_players_fight_counts_for_longer_than_waiting_for_an_enemy(self):
        run = record()
        run.duel_waits_in_a_row = Limits().max_duel_waits_in_a_row
        self.assertTrue(travel_outcome("travel", DUEL_BLOCKS_THE_WAY, 0, run)["progress"])
        run.duel_waits_in_a_row += 1
        self.assertFalse(travel_outcome("travel", DUEL_BLOCKS_THE_WAY, 0, run)["progress"])
        self.assertGreater(Limits().max_duel_waits_in_a_row, Limits().max_immobile_threat_stops_in_a_row)


class ReadyToRecallTest(unittest.TestCase):
    def test_recall_waits_for_mana_and_health_to_be_back(self):
        self.assertFalse(ready_to_recall(0.5, 1.0))
        self.assertFalse(ready_to_recall(0.9, 0.5))
        self.assertTrue(ready_to_recall(0.8, 0.9))
        self.assertTrue(ready_to_recall(None, None))


class PlannedRouteTest(unittest.TestCase):
    path = [(0, 0), (1000, 0), (2000, 0)]

    def test_a_route_is_new_until_remembered_and_stays_known_as_legs_are_walked(self):
        route = PlannedRoute()
        self.assertTrue(route.is_new(self.path))
        route.remember_clearances({}, self.path)
        self.assertFalse(route.is_new([(500, 0), (1000, 0), (2000, 0)]))
        self.assertFalse(route.is_new([(1500, 0), (2000, 0)]))
        self.assertTrue(route.is_new([(1500, 0), (3000, 0)]))

    def test_only_new_or_closer_enemies_threaten(self):
        route = PlannedRoute()
        route.remember_clearances({"known": 300.0}, self.path)
        self.assertFalse(route.threatens("known", 300.0))
        self.assertTrue(route.threatens("known", 300.0 - APPROACH_MARGIN - 1))
        self.assertTrue(route.threatens("new", 300.0))
        self.assertFalse(route.threatens("new", ENEMY_PATH_CLEARANCE))


class WispTest(unittest.TestCase):
    def test_very_low_health_then_low_mana_then_middling_health(self):
        self.assertEqual(wanted_wisp(0.3, 0.1), "health")
        self.assertEqual(wanted_wisp(0.5, 0.1), "mana")
        self.assertEqual(wanted_wisp(0.9, 0.1), "mana")
        self.assertEqual(wanted_wisp(0.5, 0.9), "health")
        self.assertIsNone(wanted_wisp(0.9, 0.3))
        self.assertIsNone(wanted_wisp(0.9, 0.9))
        self.assertIsNone(wanted_wisp(None, None))

    def test_a_fight_needs_mana(self):
        self.assertFalse(mana_for_a_fight(1 / 30))
        self.assertFalse(mana_for_a_fight(ENGAGE_MANA_FRACTION - 0.01))
        self.assertTrue(mana_for_a_fight(ENGAGE_MANA_FRACTION))
        self.assertTrue(mana_for_a_fight(None))

    def test_a_fight_needs_health(self):
        self.assertFalse(health_for_a_fight(1 / 801))
        self.assertFalse(health_for_a_fight(ENGAGE_HEALTH_FRACTION - 0.01))
        self.assertTrue(health_for_a_fight(ENGAGE_HEALTH_FRACTION))
        self.assertTrue(health_for_a_fight(None))

    def test_too_little_mana_to_travel_among_enemies(self):
        self.assertFalse(mana_to_travel(3 / 32))
        self.assertTrue(mana_to_travel(7 / 32))
        self.assertTrue(mana_to_travel(None))

    def test_too_little_health_to_travel_after_a_defeat(self):
        self.assertFalse(health_to_travel(55 / 1102))
        self.assertTrue(health_to_travel(630 / 1102))
        self.assertTrue(health_to_travel(None))

    def test_after_a_defeat_health_then_mana_are_recharged_nearly_full(self):
        self.assertEqual(still_to_recharge(109 / 1102, 31 / 60), "health")
        self.assertEqual(still_to_recharge(1000 / 1102, 31 / 60), "mana")
        self.assertIsNone(still_to_recharge(1000 / 1102, 50 / 60))
        self.assertIsNone(still_to_recharge(None, None))

    def test_the_goals_zone_is_marked_once_where_enemies_were_met(self):
        chamber = "Krokotopia/KT_Pyramid/KT_Chamber"
        self.assertTrue(worth_marking(chamber, chamber, None, 80, enemies_here=True, refused=False))
        self.assertFalse(worth_marking(chamber, chamber, chamber, 80, enemies_here=True, refused=False))
        self.assertFalse(worth_marking(chamber, "Krokotopia/KT_Pyramid/KT_AltarOfKings", None, 80, enemies_here=True,
                                       refused=False))
        self.assertFalse(worth_marking("Krokotopia/KT_Hub", "Krokotopia/KT_Hub", None, 80, enemies_here=False,
                                       refused=False))
        self.assertFalse(worth_marking(chamber, chamber, None, 4, enemies_here=True, refused=False))
        self.assertFalse(worth_marking(chamber, chamber, None, 80, enemies_here=True, refused=True))

    def test_recall_to_the_door_of_the_dungeon_the_goal_is_in(self):
        lane, dungeon, hub = "WizardCity/WC_Streets/WC_Cyclops", "WizardCity/WC_Streets/Interiors/WC_Cyclops_T1", "WizardCity/WC_Hub"
        self.assertTrue(worth_recalling(hub, dungeon, lane, 80, door_for=dungeon))
        self.assertFalse(worth_recalling(hub, dungeon, lane, 80))
        self.assertFalse(worth_recalling(lane, dungeon, lane, 80, door_for=dungeon))
        self.assertTrue(worth_recalling(hub, dungeon, lane, 80, door_for=dungeon, came_from="WizardCity/WC_Streets/WC_Cyclops_Cave"))

    def test_only_the_map_makes_a_trap_kept_across_runs(self):
        from wizardtraining.progress import ENEMIES_IN_THE_WAY, trapped_by
        self.assertEqual(trapped_by("every route method failed"), "the map")
        self.assertEqual(trapped_by(ENEMIES_IN_THE_WAY), "enemies")
        self.assertIsNone(trapped_by("battle"))
        self.assertIsNone(trapped_by(None))

    def test_no_recall_when_the_goals_zone_is_next_door(self):
        triton, underwater = "WizardCity/WC_Streets/WC_Triton", "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater"
        house = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_H1"
        self.assertFalse(worth_recalling(house, underwater, underwater, 93, next_door=True))
        self.assertTrue(worth_recalling(house, underwater, underwater, 93))

    def test_no_recall_back_to_the_door_just_walked_through(self):
        triton, underwater = "WizardCity/WC_Streets/WC_Triton", "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater"
        instance = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_T1"
        self.assertFalse(worth_recalling(underwater, instance, triton, 88, door_for=instance, came_from=triton))
        self.assertTrue(worth_recalling("WizardCity/WC_Hub", instance, triton, 88, door_for=instance, came_from=underwater))

    def test_a_parked_quest_waits_for_the_next_level(self):
        self.assertTrue(parked({"Mad Maximus": 13}, "Mad Maximus", 13))
        self.assertFalse(parked({"Mad Maximus": 13}, "Mad Maximus", 14))
        self.assertFalse(parked({"Mad Maximus": 13}, "Bear Market", 13))
        self.assertFalse(parked({}, None, 13))

    def test_recall_into_the_goals_zone_from_elsewhere(self):
        chamber, hub = "Krokotopia/KT_Pyramid/KT_Chamber", "Krokotopia/KT_Hub"
        self.assertTrue(worth_recalling(hub, chamber, chamber, 80))
        self.assertFalse(worth_recalling(chamber, chamber, chamber, 80))
        self.assertFalse(worth_recalling(hub, "Krokotopia/KT_Pyramid/KT_PalaceOfFire", chamber, 80))
        self.assertFalse(worth_recalling(hub, chamber, None, 80))
        self.assertFalse(worth_recalling(hub, chamber, chamber, 5))

    def test_waiting_for_mana_goes_on_until_nearly_full(self):
        self.assertFalse(topped_up(12 / 30))
        self.assertFalse(topped_up(26 / 30))
        self.assertTrue(topped_up(27 / 30))
        self.assertTrue(topped_up(None))

    def test_health_comes_before_mana_for_a_fight(self):
        self.assertEqual(short_for_a_fight(1 / 801, 22 / 30), "health")
        self.assertEqual(short_for_a_fight(1 / 801, 0.0), "health")
        self.assertEqual(short_for_a_fight(1.0, 1 / 30), "mana")
        self.assertIsNone(short_for_a_fight(ENGAGE_HEALTH_FRACTION, ENGAGE_MANA_FRACTION))
        self.assertIsNone(short_for_a_fight(None, None))


class PotionTest(unittest.TestCase):
    def test_drinks_only_when_low_with_a_full_charge(self):
        self.assertTrue(should_drink_potion(99 / 624, 1.0))
        self.assertFalse(should_drink_potion(0.5, 1.0))
        self.assertFalse(should_drink_potion(0.1, 0.6))
        self.assertFalse(should_drink_potion(0.1, "<unavailable: ReadingError>"))
        self.assertFalse(should_drink_potion(None, 1.0))


class ReportTest(unittest.TestCase):
    def test_report_is_labelled_as_real_game_data(self):
        report = record(target_level=7).as_report()
        self.assertIs(report["simulated"], False)
        self.assertEqual(report["limits"]["target_level"], 7)



class SafeToStandTest(unittest.TestCase):
    def test_a_zone_where_enemies_were_met_is_never_safe_to_stand_in(self):
        firecat = "WizardCity/WC_Streets/WC_Firecat"
        self.assertFalse(safe_to_stand(firecat, [firecat], enemies_in_sight=0))
        self.assertTrue(safe_to_stand("WizardCity/WC_Streets/WC_OldeTown", [firecat], enemies_in_sight=0))
        self.assertFalse(safe_to_stand("WizardCity/WC_Streets/WC_OldeTown", [firecat], enemies_in_sight=1))



class RecallInTheGoalZoneTest(unittest.TestCase):
    def test_no_recall_while_in_the_goals_zone(self):
        from wizardtraining.progress import worth_recalling
        cyclops, cave = "WizardCity/WC_Streets/WC_Cyclops", "WizardCity/WC_Streets/WC_DarkCave"
        self.assertFalse(worth_recalling(cyclops, cyclops, cave, 80, door_for=cyclops))
        self.assertTrue(worth_recalling("WizardCity/WC_Hub", cyclops, cave, 80, door_for=cyclops))


class HeavyFightTest(unittest.TestCase):
    def test_a_fight_costing_a_third_of_the_health_is_heavy(self):
        from wizardtraining.progress import heavy_fight
        self.assertTrue(heavy_fight(1047, 540, 1133))
        self.assertFalse(heavy_fight(929, 543, 1133))
        self.assertFalse(heavy_fight(1133, 1033, 1133))
        self.assertFalse(heavy_fight(None, 543, 1133))

    def test_a_door_known_to_open_on_an_instance_waits_for_a_full_refill(self):
        from wizardtraining.progress import short_before_entering
        tower = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_T1"
        self.assertEqual(short_before_entering("Enter", 525 / 1164, 68 / 96, tower), "health")
        self.assertEqual(short_before_entering("Enter", 1100 / 1164, 60 / 96, tower), "mana")
        self.assertIsNone(short_before_entering("Enter", 1100 / 1164, 90 / 96, tower))
        self.assertIsNone(short_before_entering("Jump", 525 / 1164, 68 / 96, tower))

    def test_a_shop_door_asks_for_nothing_and_an_unknown_door_only_that_the_wizard_not_be_low(self):
        from wizardtraining.progress import short_before_entering
        self.assertIsNone(short_before_entering("Enter", 525 / 1164, 30 / 96, "WizardCity/Interiors/WC_Shop_Robes"))
        self.assertIsNone(short_before_entering("Enter", 525 / 1164, 68 / 96))
        self.assertEqual(short_before_entering("Enter", 400 / 1164, 68 / 96), "health")

    def test_obstacles_learned_near_a_spot_are_forgotten(self):
        from wizardtraining.progress import forget_obstacles_near
        shop = record()
        shop.obstacles["WizardCity/WC_Shop_Area"] = [(-1500, -2300), (-1600, -2400), (2000, 0)]
        self.assertEqual(forget_obstacles_near(shop, "WizardCity/WC_Shop_Area", (-1540, -2358)), 2)
        self.assertEqual(shop.obstacles["WizardCity/WC_Shop_Area"], [(2000, 0)])

    def test_a_held_quest_stays_parked_whatever_the_level(self):
        from wizardtraining.progress import parked
        held = {"Strange Brew": "waiting for wizard404 API"}
        self.assertTrue(parked({"Strange Brew": 14}, "Strange Brew", 20, held))
        self.assertFalse(parked({"Strange Brew": 14}, "Strange Brew", 15))
        self.assertTrue(parked({}, "Strange  Brew", 15, held))

    def test_after_a_heavy_fight_a_near_goal_comes_before_the_refill_at_half_health_or_more(self):
        from wizardtraining.progress import worth_pushing_on
        self.assertTrue(worth_pushing_on(629 / 1164, 3018))
        self.assertFalse(worth_pushing_on(500 / 1164, 3018))
        self.assertFalse(worth_pushing_on(900 / 1164, 6600))
        self.assertFalse(worth_pushing_on(None, 3018))
        self.assertTrue(worth_pushing_on(677 / 1164, 6800, stalled=True))
        self.assertFalse(worth_pushing_on(500 / 1164, 6800, stalled=True))

    def test_headway_is_a_thousand_nearer_the_goal_than_at_the_last_refill_trip(self):
        from wizardtraining.progress import made_headway
        self.assertFalse(made_headway(6800, 6850))
        self.assertTrue(made_headway(5650, 6800))
        self.assertTrue(made_headway(6800, None))
        self.assertTrue(made_headway(None, 6800))


class HeavyZoneTest(unittest.TestCase):
    def test_a_zone_with_heavy_fights_wants_the_recharge_before_walking_on(self):
        from wizardtraining.progress import short_for_a_heavy_zone
        self.assertTrue(short_for_a_heavy_zone(708 / 1195, 3))
        self.assertFalse(short_for_a_heavy_zone(1100 / 1195, 3))
        self.assertFalse(short_for_a_heavy_zone(708 / 1195, 1))
        self.assertFalse(short_for_a_heavy_zone(None, 3))


class MarkAtTheDoorTest(unittest.TestCase):
    def test_walk_to_a_near_door_to_mark_it_when_no_enemy_is_on_the_way(self):
        from wizardtraining.progress import walk_to_mark_at_the_door
        here, door = (0, 0), (1000, 0)
        self.assertTrue(walk_to_mark_at_the_door(here, door, [(500, 900), (-800, 0)]))
        self.assertFalse(walk_to_mark_at_the_door(here, door, [(500, 200)]))
        self.assertFalse(walk_to_mark_at_the_door(here, (100, 0), []))
        self.assertFalse(walk_to_mark_at_the_door(here, (3000, 0), []))


class GoInFirstTest(unittest.TestCase):
    house = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_H1"

    def test_a_house_whose_door_is_close_is_gone_into_before_refilling(self):
        from wizardtraining.progress import worth_going_in_first
        self.assertTrue(worth_going_in_first(830 / 1195, 900, self.house))
        self.assertFalse(worth_going_in_first(500 / 1195, 900, self.house))
        self.assertFalse(worth_going_in_first(830 / 1195, 3000, self.house))
        self.assertFalse(worth_going_in_first(830 / 1195, None, self.house))

    def test_not_for_an_instance_a_dungeon_or_a_street(self):
        from wizardtraining.progress import worth_going_in_first
        instance = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_T1"
        self.assertFalse(worth_going_in_first(0.9, 500, instance))
        self.assertFalse(worth_going_in_first(0.9, 500, self.house, [self.house]))
        self.assertFalse(worth_going_in_first(0.9, 500, "WizardCity/WC_Streets/WC_Triton"))


class AfterBattleTest(unittest.TestCase):
    def test_a_move_ends_the_timeline_and_bookkeeping_does_not(self):
        from wizardtraining.progress import acted_after_battle
        for did in ("went to the Commons for a refill", "travel to waypoint", "walk to a health wisp",
                    "recalled toward the goal", "entered with X at the interact prompt"):
            self.assertTrue(acted_after_battle(did), did)
        for did in ("battle", "settled after arriving", "dialog", "deck edit stopped", None):
            self.assertFalse(acted_after_battle(did), did)


class InstanceGoalManaTest(unittest.TestCase):
    def test_mana_is_topped_up_before_setting_off_for_an_instance_goal(self):
        from wizardtraining.progress import short_for_an_instance_goal
        instance = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_T1"
        self.assertTrue(short_for_an_instance_goal(instance, 47 / 98))
        self.assertFalse(short_for_an_instance_goal(instance, 90 / 98))
        self.assertFalse(short_for_an_instance_goal("WizardCity/WC_Streets/WC_Triton", 47 / 98))
        sunken = "WizardCity/WC_Streets/WC_Sunken_City"
        self.assertTrue(short_for_an_instance_goal(sunken, 0.5, [sunken]))


class HeavyZoneOnTheWayTest(unittest.TestCase):
    def test_the_zone_outside_an_instance_goal_counts(self):
        from wizardtraining.progress import heavy_zone_on_the_way
        underwater = "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater"
        instance = "WizardCity/WC_Streets/WC_Triton_Underwater/Interiors/WC_Triton_Underwater_T1"
        heavy, enemies = {underwater: 8, instance: 1}, [underwater, instance]
        self.assertEqual(heavy_zone_on_the_way("WizardCity/WC_Hub", [instance, underwater, None], heavy, enemies),
                         underwater)
        self.assertIsNone(heavy_zone_on_the_way("WizardCity/WC_Hub", [instance, None, None], heavy, enemies))
        self.assertIsNone(heavy_zone_on_the_way(underwater, [underwater], heavy, enemies))


class OnARefillTripTest(unittest.TestCase):
    def test_a_trip_is_over_once_the_wizard_is_in_a_dungeon_or_among_enemies(self):
        from wizardtraining.progress import on_a_refill_trip
        underwater = "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater"
        self.assertTrue(on_a_refill_trip("WizardCity/WC_Hub", underwater, dungeon_here=False, enemies_here=False))
        self.assertFalse(on_a_refill_trip("Interiors/WC_Triton_Underwater_T1", underwater, dungeon_here=True,
                                          enemies_here=False))
        self.assertFalse(on_a_refill_trip("WizardCity/WC_Streets/WC_Triton", underwater, dungeon_here=False,
                                          enemies_here=True))
        self.assertFalse(on_a_refill_trip(underwater, underwater, dungeon_here=False, enemies_here=True))
        self.assertFalse(on_a_refill_trip("WizardCity/WC_Hub", None, dungeon_here=False, enemies_here=False))


class RefillTripsAreNoDoorLoopTest(unittest.TestCase):
    def test_a_travel_button_starts_the_count_of_zone_changes_again(self):
        run = RunRecord(limits=Limits(max_zone_changes_without_quest_change=2))
        for zone in ("Hub", "Shops", "Olde Town"):
            run.note_place(zone, ("Curfew!", 1))
        self.assertEqual(run.zone_changes_without_quest_change, 2)
        run.last_place = None
        run.note_place("Triton", ("Curfew!", 1))
        self.assertEqual(run.zone_changes_without_quest_change, 0)


class TripOutOfADungeonTest(unittest.TestCase):
    sunken = "WizardCity/WC_Streets/WC_Sunken_City"

    def test_the_way_back_in_is_within_the_margin_of_the_dungeon_timer(self):
        from wizardtraining.progress import RESUME_TRIP_SECONDS, resume_in_time
        self.assertTrue(resume_in_time(1000.0, 1000.0 + 300))
        self.assertTrue(resume_in_time(1000.0, 1000.0 + RESUME_TRIP_SECONDS))
        self.assertFalse(resume_in_time(1000.0, 1000.0 + RESUME_TRIP_SECONDS + 1))
        self.assertFalse(resume_in_time(None, 1000.0))
        self.assertFalse(resume_in_time(2000.0, 1000.0))

    def test_a_dungeon_held_when_the_wizard_is_back_in_it_and_its_enemies_stayed_down(self):
        from wizardtraining.progress import dungeon_held
        left = {"zone": self.sunken, "enemies": 2}
        self.assertTrue(dungeon_held(left, self.sunken, 2))
        self.assertTrue(dungeon_held(left, self.sunken, 3))
        self.assertFalse(dungeon_held(left, self.sunken, 6))
        self.assertFalse(dungeon_held(left, "WizardCity/WC_Hub", 0))
        self.assertTrue(dungeon_held({"zone": self.sunken, "enemies": None}, self.sunken, 6))

    def test_a_door_to_a_dungeon_behind_an_entry_box_waits_for_the_full_refill(self):
        from wizardtraining.progress import short_before_entering
        self.assertEqual(short_before_entering("Enter", 0.7, 0.9, self.sunken, [self.sunken]), "health")
        self.assertEqual(short_before_entering("Enter", 0.95, 0.7, self.sunken, [self.sunken]), "mana")
        self.assertIsNone(short_before_entering("Enter", 0.7, 0.9, self.sunken))


if __name__ == "__main__":
    unittest.main()
