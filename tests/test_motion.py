import unittest

from wizardtraining.motion import (MAX_ENEMY_SPEED, MOTION_WINDOW_SECONDS, PREDICTION_HORIZON_SECONDS, MotionTracker,
                                   ApproachLog, Track, closest_approach, closing_speed)
from wizardtraining.routes import COLLISION, ENEMY_KEEP_OUT, Hazards, RoutePlanner

from test_routes import SquareWalkGrid


def ghoul(x, y):
    return {"id": 7, "position": (x, y)}


class MotionTrackerTest(unittest.TestCase):
    def test_velocity_from_recent_positions(self):
        tracker = MotionTracker()
        tracker.observe([ghoul(0, 0)], 10.0)
        tracker.observe([ghoul(100, 0)], 10.5)
        tracker.observe([ghoul(200, 0)], 11.0)
        self.assertEqual(tracker.track(ghoul(200, 0), 11.0), Track((200, 0), (200.0, 0.0)))

    def test_standing_still_without_enough_recent_movement(self):
        tracker = MotionTracker()
        self.assertEqual(tracker.track(ghoul(0, 0), 1.0), Track((0, 0)))
        tracker.observe([ghoul(0, 0)], 10.0)
        tracker.observe([ghoul(10, 0)], 10.1)
        self.assertEqual(tracker.track(ghoul(10, 0), 10.1).velocity, (0.0, 0.0))
        tracker.observe([ghoul(100, 0)], 10.5)
        self.assertEqual(tracker.track(ghoul(100, 0), 10.5 + MOTION_WINDOW_SECONDS + 1).velocity, (0.0, 0.0))

    def test_a_jump_is_not_a_velocity(self):
        tracker = MotionTracker()
        tracker.observe([ghoul(0, 0)], 10.0)
        tracker.observe([ghoul(MAX_ENEMY_SPEED * 2, 0)], 11.0)
        self.assertEqual(tracker.track(ghoul(MAX_ENEMY_SPEED * 2, 0), 11.0).velocity, (0.0, 0.0))

    def test_predictions_stop_at_the_horizon(self):
        track = Track((0, 0), (100, 0))
        self.assertEqual(track.at(2), (200, 0))
        self.assertEqual(track.at(PREDICTION_HORIZON_SECONDS + 10), (100 * PREDICTION_HORIZON_SECONDS, 0))


class ApproachLogTest(unittest.TestCase):
    def test_reports_each_enemys_nearest_reading_in_the_last_seconds(self):
        log = ApproachLog()
        log.record([{"id": 1, "name": "FireElf-Red-L02", "distance": 301.0}], now=10.0)
        log.record([{"id": 1, "name": "FireElf-Red-L02", "distance": 954.0},
                    {"id": 2, "name": "Snowman-Fire-L12", "distance": 700.0}], now=13.0)
        self.assertEqual(log.closest(13.2, 2), [{"name": "FireElf-Red-L02", "distance": 301, "seconds_before": 3.2},
                                                {"name": "Snowman-Fire-L12", "distance": 700, "seconds_before": 0.2}])

    def test_forgets_readings_older_than_its_memory(self):
        log = ApproachLog()
        log.record([{"id": 1, "name": "Troll", "distance": 200.0}], now=0.0)
        log.record([{"id": 1, "name": "Troll", "distance": 800.0}], now=7.0)
        self.assertEqual(log.closest(7.0, 3), [{"name": "Troll", "distance": 800, "seconds_before": 0.0}])
        log.forget()
        self.assertEqual(log.closest(7.0, 3), [])


class ClosingSpeedTest(unittest.TestCase):
    def test_how_fast_an_enemy_comes_toward_a_point(self):
        self.assertAlmostEqual(closing_speed(Track((0.0, 0.0), (300.0, 0.0)), (500.0, 0.0)), 300.0)
        self.assertAlmostEqual(closing_speed(Track((0.0, 0.0), (-300.0, 0.0)), (500.0, 0.0)), -300.0)
        self.assertAlmostEqual(closing_speed(Track((0.0, 0.0), (0.0, 300.0)), (500.0, 0.0)), 0.0)
        self.assertEqual(closing_speed(Track((5.0, 5.0)), (5.0, 5.0)), 0.0)


class ClosestApproachTest(unittest.TestCase):
    path = [(0, 0), (3000, 0)]

    def test_an_enemy_walking_away_never_comes_close(self):
        self.assertGreater(closest_approach(Track((1500, 300), (0, 400)), self.path, speed=600), 700)

    def test_an_enemy_heading_into_the_path_does(self):
        self.assertLess(closest_approach(Track((1500, 1000), (0, -400)), self.path, speed=600), 100)


class PredictiveRouteTest(unittest.TestCase):
    planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(30), grid_line_walkable=lambda a, b: True)

    def widest_detour(self, track):
        legs = self.planner.route(COLLISION, (0, 0), (2900, 0), Hazards.of(tracks=[track]))
        path = [(0, 0), *legs]
        return max(abs(y) for _, y in path), legs[-1]

    def test_a_standing_enemy_is_walked_around(self):
        detour, end = self.widest_detour(Track((1500, 0)))
        self.assertGreaterEqual(detour, ENEMY_KEEP_OUT - 100)
        self.assertEqual(end, (2900, 0))

    def test_an_enemy_walking_off_the_path_is_passed_behind(self):
        detour, end = self.widest_detour(Track((1500, 0), (0, 800)))
        self.assertLess(detour, ENEMY_KEEP_OUT / 2)
        self.assertEqual(end, (2900, 0))

    def test_where_an_enemy_will_be_is_forbidden(self):
        hazards = Hazards.of(tracks=[Track((0, 0), (300, 0))])
        self.assertFalse(hazards.forbids((900, 0), seconds=0))
        self.assertTrue(hazards.forbids((900, 0), seconds=3))


class SettleTest(unittest.TestCase):
    def test_held_walk_gives_way_to_steps_sooner_the_faster_the_wizard(self):
        from wizardtraining.motion import slow_down_distance
        self.assertLess(slow_down_distance(400.0), slow_down_distance(800.0))

    def test_a_step_ends_inside_the_target_circle_within_the_shortest_and_longest_steps(self):
        from wizardtraining.motion import MAX_STEP_SECONDS, MIN_STEP_SECONDS, step_seconds
        self.assertAlmostEqual(step_seconds(215.0, 30.0, 800.0), 0.25)
        self.assertEqual(step_seconds(31.0, 30.0, 800.0), MIN_STEP_SECONDS)
        self.assertEqual(step_seconds(5000.0, 30.0, 800.0), MAX_STEP_SECONDS)

    def test_settling_counts_what_the_shortest_steps_can_miss_by(self):
        from wizardtraining.motion import settle_radius
        self.assertEqual(settle_radius(30.0, 300.0), 30.0)
        self.assertEqual(settle_radius(10.0, 800.0), 64.0)

    def test_three_reversals_are_oscillating(self):
        import math
        from wizardtraining.motion import OscillationGuard
        guard = OscillationGuard()
        for off_course in (0.1, math.pi, -0.2, -math.pi * 0.9, math.pi * 0.8):
            guard.note(off_course)
        self.assertTrue(guard.oscillating)
        calm = OscillationGuard()
        for off_course in (0.1, 0.3, -0.2, 0.5):
            calm.note(off_course)
        self.assertFalse(calm.oscillating)

    def test_the_measured_speed_is_smoothed_and_stops_and_loads_are_left_out(self):
        from wizardtraining.motion import smoothed_speed
        self.assertEqual(smoothed_speed(None, 600.0), 600.0)
        self.assertAlmostEqual(smoothed_speed(600.0, 900.0), 690.0)
        self.assertEqual(smoothed_speed(600.0, 20.0), 600.0)
        self.assertEqual(smoothed_speed(600.0, 9000.0), 600.0)


if __name__ == "__main__":
    unittest.main()
