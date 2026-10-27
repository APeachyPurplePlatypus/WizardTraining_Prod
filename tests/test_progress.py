import unittest

from wizardtraining.progress import (APPROACH_MARGIN, ENEMY_NEAR_PATH, ENEMY_PATH_CLEARANCE, MEANINGFUL_TRAVEL_DISTANCE,
                                     Limits, PlannedRoute, RunRecord, StopRun, check_limits, needs_rest, progressed,
                                     remember_obstacles, stalled, travel_outcome)


def record(**limits) -> RunRecord:
    return RunRecord(limits=Limits(**limits))


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


class RestTest(unittest.TestCase):
    def test_rests_below_the_threshold_only(self):
        self.assertTrue(needs_rest(0.5))
        self.assertFalse(needs_rest(0.9))
        self.assertFalse(needs_rest(None))


class ReportTest(unittest.TestCase):
    def test_report_is_labelled_as_real_game_data(self):
        report = record(target_level=7).as_report()
        self.assertIs(report["simulated"], False)
        self.assertEqual(report["limits"]["target_level"], 7)


if __name__ == "__main__":
    unittest.main()
