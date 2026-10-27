import math
import struct
import unittest

from wizardtraining.patrols import PatrolMap
from wizardtraining.routes import (COLLISION, DUEL_CIRCLE_NO_GO, GOAL_PIECE_REACH, LEG_ENEMY_CLEARANCE,
                                   MAX_GAP_STEP, NAV, GapStep,
                                   NAV_CELL_REACH,
                                   OBSTACLE_RADIUS, STRAIGHT, Hazards, NavGraph, RoutePlanner, grid_path,
                                   no_more_dangerous, parse_nav_file, string_pull)
from wizardtraining.motion import Track
from wizardtraining.teleports import TeleportVolume

SPACING = 100.0


class SquareWalkGrid:
    """A stand-in for Deimos's walk grid: square cells, walkable unless listed as blocked."""

    spacing = SPACING

    def __init__(self, size: int, blocked=()):
        self.size, self.blocked = size, set(blocked)

    def to_hex(self, x, y):
        return round(x / SPACING), round(y / SPACING)

    def to_world(self, q, r):
        return q * SPACING, r * SPACING

    def neighbours(self, q, r):
        return [(q + 1, r), (q - 1, r), (q, r + 1), (q, r - 1)]

    def walk_z(self, q, r):
        inside = 0 <= q < self.size and 0 <= r < self.size
        return 0.0 if inside and (q, r) not in self.blocked else None

    def _nearest_walk_node(self, q, r):
        return None


def square_nav_graph(size: int) -> NavGraph:
    vertices = [(q * 480.0, r * 480.0) for r in range(size) for q in range(size)]
    edges = []
    for r in range(size):
        for q in range(size):
            here = r * size + q
            if q + 1 < size:
                edges += [(here, here + 1), (here + 1, here)]
            if r + 1 < size:
                edges += [(here, here + size), (here + size, here)]
    return NavGraph.from_edges(vertices, edges)


class HazardsTest(unittest.TestCase):
    def test_steps_cost_more_near_enemies(self):
        hazards = Hazards.of(enemies=[(0, 0)])
        self.assertGreater(hazards.step_cost((100, 0)), hazards.step_cost((800, 0)))
        self.assertEqual(hazards.step_cost((5000, 0)), 1.0)
        self.assertEqual(Hazards().step_cost((0, 0)), 1.0)

    def test_duel_circles_are_no_go(self):
        hazards = Hazards.of(duel_circles=[(0, 0)])
        self.assertTrue(hazards.forbids((DUEL_CIRCLE_NO_GO - 1, 0)))
        self.assertFalse(hazards.forbids((DUEL_CIRCLE_NO_GO + 1, 0)))
        self.assertFalse(hazards.line_is_open((-2000, 0), (2000, 0)))

    def test_a_walk_beginning_near_a_duel_may_only_lead_away(self):
        hazards = Hazards.of(duel_circles=[(0, 0)], start=(800, 0))
        self.assertFalse(hazards.forbids((900, 0)))
        self.assertFalse(hazards.forbids((800, 300)))
        self.assertTrue(hazards.forbids((600, 0)))
        self.assertTrue(Hazards.of(duel_circles=[(0, 0)], start=(5000, 0)).forbids((DUEL_CIRCLE_NO_GO - 1, 0)))

    def test_routes_out_from_beside_a_duel(self):
        grid = SquareWalkGrid(60)
        circle, start, goal = (3000, 3000), (3700, 3000), (5500, 3000)
        cells = grid_path(grid, start, goal, Hazards.of(duel_circles=[circle], start=start))
        self.assertIsNotNone(cells)
        self.assertTrue(all(math.dist(cell, circle) >= 650 for cell in cells))
        self.assertIsNone(grid_path(grid, start, goal, Hazards.of(duel_circles=[circle])))

    def test_obstacles_are_no_go_and_block_lines(self):
        hazards = Hazards.of(obstacles=[(0, 0)])
        self.assertTrue(hazards.forbids((OBSTACLE_RADIUS - 1, 0)))
        self.assertFalse(hazards.forbids((OBSTACLE_RADIUS + 1, 0)))
        self.assertFalse(hazards.line_is_open((-500, 0), (500, 0)))
        self.assertEqual(Hazards().with_obstacles([(1, 2)]).obstacles, ((1, 2),))
        self.assertEqual(Hazards.of(obstacles=[(0, 0), (900, 0)]).clear_around((100, 0), 200).obstacles, ((900, 0),))

    def test_a_safe_line_keeps_clear_of_enemies(self):
        hazards = Hazards.of(enemies=[(0, LEG_ENEMY_CLEARANCE - 10)])
        self.assertFalse(hazards.line_is_safe((-1000, 0), (1000, 0)))
        self.assertTrue(hazards.line_is_safe((-1000, -100), (-900, -100)))


class NavGraphTest(unittest.TestCase):
    def test_a_line_is_covered_only_where_waypoints_are_near(self):
        graph = square_nav_graph(3)
        self.assertTrue(graph.covers_line((0, 0), (960, 0)))
        self.assertTrue(graph.near_a_waypoint((480 + NAV_CELL_REACH - 1, 0)))
        self.assertFalse(graph.near_a_waypoint((-NAV_CELL_REACH - 1, 0)))
        self.assertFalse(graph.covers_line((0, 0), (0, -2000)))

    def test_matches_comparing_with_every_waypoint(self):
        graph = square_nav_graph(4)
        for x in range(-400, 2000, 37):
            for y in range(-400, 2000, 53):
                expected = min(math.dist((x, y), vertex) for vertex in graph.vertices) <= NAV_CELL_REACH
                self.assertEqual(graph.near_a_waypoint((x, y)), expected, (x, y))


class StringPullTest(unittest.TestCase):
    def test_merges_points_a_straight_line_can_join(self):
        points = [(0, 0), (1, 0), (2, 0), (3, 0)]
        self.assertEqual(string_pull(points, lambda i, j: True), [(3, 0)])

    def test_keeps_corners_a_straight_line_cannot_cut(self):
        points = [(0, 0), (1, 0), (1, 1)]
        cuts_corner = lambda i, j: points[i][0] == points[j][0] or points[i][1] == points[j][1]
        self.assertEqual(string_pull(points, cuts_corner), [(1, 0), (1, 1)])

    def test_merging_never_cuts_across_a_patrol(self):
        patrols = PatrolMap()
        patrols.add_segment((500, -300), (500, 300))
        hazards = Hazards.of(patrols=patrols)
        detour = [(0, 0), (0, 1200), (1000, 1200), (1000, 0)]
        legs = string_pull(detour, no_more_dangerous(detour, hazards))
        self.assertEqual(legs, [(0, 1200), (1000, 1200), (1000, 0)])


class GridPathTest(unittest.TestCase):
    def test_finds_a_way_around_blocked_cells(self):
        grid = SquareWalkGrid(5, blocked=[(2, 0), (2, 1), (2, 2), (2, 3)])
        cells = grid_path(grid, (0, 0), (400, 0), Hazards())
        self.assertEqual(cells[0], (0, 0))
        self.assertEqual(cells[-1], (400, 0))
        self.assertIn((200, 400), cells)

    def test_never_enters_a_duel_circle(self):
        grid = SquareWalkGrid(30)
        circle = (1500, 0)
        cells = grid_path(grid, (0, 0), (2900, 0), Hazards.of(duel_circles=[circle]))
        self.assertEqual(cells[-1], (2900, 0))
        self.assertTrue(all(math.dist(cell, circle) >= DUEL_CIRCLE_NO_GO for cell in cells))

    def test_bends_away_from_patrol_paths(self):
        grid = SquareWalkGrid(30)
        patrols = PatrolMap()
        patrols.add_segment((1500, -500), (1500, 500))
        cells = grid_path(grid, (0, 0), (2900, 0), Hazards.of(patrols=patrols))
        self.assertGreater(min(patrols.distance(cell, 3000) for cell in cells), 400)

    def test_bends_away_from_enemies(self):
        grid = SquareWalkGrid(30)
        enemy = (1500, 0)
        cells = grid_path(grid, (0, 0), (2900, 0), Hazards.of(enemies=[enemy]))
        closest = min(math.dist(cell, enemy) for cell in cells)
        self.assertGreater(closest, 400)

    def test_no_route_off_the_grid(self):
        self.assertIsNone(grid_path(SquareWalkGrid(3), (0, 0), (5000, 5000), Hazards()))


class RoutePlannerTest(unittest.TestCase):
    def test_methods_follow_the_walk_data_that_loaded(self):
        self.assertEqual(RoutePlanner("zone").methods(), [STRAIGHT])
        planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(3), grid_line_walkable=lambda a, b: True,
                               nav_graph=square_nav_graph(2))
        self.assertEqual(planner.methods(), [COLLISION, NAV, STRAIGHT])
        planner.nav_first = True
        self.assertEqual(planner.methods(), [NAV, COLLISION, STRAIGHT])

    def test_nav_route_ends_at_the_goal_and_avoids_a_duel(self):
        planner = RoutePlanner("zone", nav_graph=square_nav_graph(6))
        circle = (1200, 1200)
        legs = planner.route(NAV, (0, 0), (2400, 2400), Hazards.of(duel_circles=[circle]))
        self.assertEqual(legs[-1], (2400, 2400))
        path = [(0, 0), *legs]
        hazards = Hazards.of(duel_circles=[circle])
        self.assertTrue(all(hazards.line_is_open(a, b) for a, b in zip(path, path[1:])))

    def test_collision_route_merges_into_straight_legs(self):
        planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(10), grid_line_walkable=lambda a, b: True)
        self.assertEqual(planner.route(COLLISION, (0, 0), (900, 0)), [(900, 0)])

    def test_straight_route_is_refused_through_a_duel(self):
        planner = RoutePlanner("zone")
        self.assertEqual(planner.route(STRAIGHT, (0, 0), (5000, 0)), [(5000, 0)])
        self.assertIsNone(planner.route(STRAIGHT, (0, 0), (5000, 0), Hazards.of(duel_circles=[(2500, 0)])))

    def test_routes_go_around_a_recorded_obstacle(self):
        walkable = lambda a, b: True
        planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(20), grid_line_walkable=walkable)
        obstacle = (500, 0)
        legs = planner.route(COLLISION, (0, 0), (1000, 0), Hazards.of(obstacles=[obstacle]))
        path = [(0, 0), *legs]
        hazards = Hazards.of(obstacles=[obstacle])
        self.assertEqual(legs[-1], (1000, 0))
        self.assertTrue(all(hazards.line_is_open(a, b) for a, b in zip(path, path[1:])))
        self.assertIsNone(RoutePlanner("zone").route(STRAIGHT, (0, 0), (1000, 0), hazards))

    def test_a_door_in_a_wall_belongs_to_the_piece_beside_it(self):
        lower, upper = (0, 0), (10_000, 0)

        def piece_of(point, reach=150):
            distances = {0: math.dist(point, lower), 1: math.dist(point, upper)}
            nearest = min(distances, key=distances.get)
            return nearest if distances[nearest] - 1000 <= reach else None

        planner = RoutePlanner("zone")
        planner.piece_of = piece_of
        up = TeleportVolume("Tele Up", 500, 0, 0, 100)
        planner.teleports = [(up, 0)]
        door_in_a_wall = (upper[0] + 1000 + GOAL_PIECE_REACH - 100, 0)
        self.assertIsNone(piece_of(door_in_a_wall))
        self.assertEqual(planner.crossing(lower, door_in_a_wall, {}), up)
        self.assertIsNone(planner.crossing(lower, (upper[0] + 1000 + GOAL_PIECE_REACH + 100, 0), {}))

    def test_straight_leg_keeps_clear_of_enemies(self):
        planner = RoutePlanner("zone")
        self.assertIsNone(planner.route(STRAIGHT, (0, 0), (5000, 0), Hazards.of(enemies=[(2500, 200)])))
        self.assertEqual(planner.route(STRAIGHT, (0, 0), (5000, 0), Hazards.of(enemies=[(2500, 2000)])), [(5000, 0)])

    def test_straight_leg_never_cuts_across_a_patrol_when_walk_data_loaded(self):
        patrols = PatrolMap.from_paths({1: (2500, -3000, 0), 2: (2500, 3000, 0)}, {"Path 10_Screamer": [1, 2]})
        hazards = Hazards.of(patrols=patrols)
        with_walk_data = RoutePlanner("zone", walk_grid=SquareWalkGrid(3), grid_line_walkable=lambda a, b: False)
        self.assertIsNone(with_walk_data.route(STRAIGHT, (0, 0), (5000, 0), hazards))
        self.assertEqual(with_walk_data.route(STRAIGHT, (0, 0), (1000, 0), hazards), [(1000, 0)])
        self.assertEqual(RoutePlanner("zone").route(STRAIGHT, (0, 0), (5000, 0), hazards), [(5000, 0)])

    def test_no_crossing_to_a_goal_the_wizards_piece_reaches(self):
        planner = RoutePlanner("zone")
        planner.piece_of = lambda point, reach=150: 1 if point[1] < -2000 else 0
        planner.piece_reaches = lambda piece, point, reach: piece == 0 and point[1] > -2300
        planner.teleports = [(TeleportVolume("to IceSchool", 3605, 3662, 0, 142), 0)]
        self.assertIsNone(planner.crossing((0, 0), (22, -2170), {}))
        self.assertEqual(planner.crossing((0, 0), (22, -4000), {}).name, "to IceSchool")

    def test_no_crossing_where_the_nav_graph_walks(self):
        planner = RoutePlanner("zone", nav_graph=square_nav_graph(3))
        planner.piece_of = lambda point, reach=150: 1 if point[1] > 800 else 0
        planner.teleports = [(TeleportVolume("to IceSchool", 900, 0, 0, 142), 0)]
        self.assertIsNone(planner.crossing((0, 0), (960, 960), {}))
        self.assertEqual(planner.crossing((0, 0), (960, 5000), {}).name, "to IceSchool")

    def test_a_teleporter_known_to_reach_the_goals_piece_beats_a_nav_graph_link(self):
        """Triton Avenue: the nav graph links the lower street to the Haunted Cave's level through the teleporter,
        and walking that link stuck at a wall."""
        planner = RoutePlanner("zone", nav_graph=square_nav_graph(3))
        planner.piece_of = lambda point, reach=150: 1 if point[1] > 800 else 0
        tele_up = TeleportVolume("Tele Up", 900, 0, 0, 177)
        planner.teleports = [(tele_up, 0)]
        self.assertEqual(planner.crossing((0, 0), (960, 960), {"Tele Up": 1}), tele_up)
        self.assertIsNone(planner.crossing((0, 0), (960, 960), {"Tele Up": 0}))
        self.assertIsNone(planner.crossing((0, 0), (960, 960), {"Tele Up": "left the zone"}))

    def test_routes_keep_out_of_teleport_volumes(self):
        planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(20), grid_line_walkable=lambda a, b: True)
        jeweler = TeleportVolume("WC_Shop Jewelry", 1000, 0, 0, 100)
        planner.teleports = [(jeweler, 0)]
        keep_out = planner.teleports_to_keep_out_of((0, 0), (1900, 0), 40)
        self.assertEqual(keep_out, [((1000, 0), 160)])
        legs = planner.route(COLLISION, (0, 0), (1900, 0), Hazards.of(keep_out=keep_out))
        path = [(0, 0), *legs]
        self.assertTrue(all(Hazards.of(keep_out=keep_out).line_is_open(a, b) for a, b in zip(path, path[1:])))

    def test_the_volume_walked_to_or_from_is_not_kept_out(self):
        planner = RoutePlanner("zone")
        door = TeleportVolume("Tower Exit", 1000, 0, 0, 100)
        planner.teleports = [(door, 0)]
        self.assertEqual(planner.teleports_to_keep_out_of((0, 0), (1000, 50), 40), [])
        self.assertEqual(planner.teleports_to_keep_out_of((1050, 0), (5000, 0), 40), [])

    def test_a_door_just_come_through_is_kept_out_without_the_margin(self):
        planner = RoutePlanner("zone")
        planner.teleports = [(TeleportVolume("Myth School Exit", 1000, 0, 0, 100), 0)]
        self.assertEqual(planner.teleports_to_keep_out_of((1130, 0), (5000, 0), 40), [((1000, 0), 129.0)])

    def test_nav_routes_never_start_at_a_forbidden_waypoint(self):
        graph = square_nav_graph(3)
        hazards = Hazards.of(keep_out=[((0, 0), 100)])
        self.assertNotEqual(graph.vertices[graph.path((10, 10), (960, 960), hazards)[0]], (0, 0))
        self.assertIsNone(graph.path((0, 0), (960, 960), Hazards.of(keep_out=[((480, 480), 2000)])))

    def test_volumes_on_another_level_are_not_kept_out(self):
        planner = RoutePlanner("zone")
        planner.piece_of = lambda point, reach=150: 0
        planner.teleports = [(TeleportVolume("Tele Down", 1000, 0, 0, 100), 1)]
        self.assertEqual(planner.teleports_to_keep_out_of((0, 0), (5000, 0), 40), [])

    def test_reroute_plans_the_way_ahead_again_and_keeps_the_rest(self):
        planner = RoutePlanner("zone", walk_grid=SquareWalkGrid(40), grid_line_walkable=lambda a, b: True)
        path_ahead = [(0, 0), (3900, 0), (3900, 3900)]
        legs = planner.reroute(path_ahead, Hazards.of(tracks=[Track((1200, 0))]))
        self.assertEqual(legs[-2:], [(3900, 0), (3900, 3900)])
        walked = [(0, 0), *legs]
        joint = walked.index((2500.0, 0.0))
        self.assertTrue(all(Hazards.of(tracks=[Track((1200, 0))]).line_is_open(a, b)
                            for a, b in zip(walked[:joint], walked[1:joint + 1])))

    def test_no_reroute_without_walk_data(self):
        self.assertIsNone(RoutePlanner("zone").reroute([(0, 0), (3000, 0)], Hazards()))

    def test_unknown_method_is_an_error(self):
        with self.assertRaises(ValueError):
            RoutePlanner("zone").route("teleport", (0, 0), (1, 1))



class GapStepTest(unittest.TestCase):
    """Sapphyra's Tower's courtyard is a walkable piece of its own, 175 units from Olde Town's street."""

    def planner(self, gap):
        planner = RoutePlanner("WizardCity/WC_Streets/WC_OldeTown")
        planner.piece_of = lambda point, reach=150.0: 1 if point[0] < -10000 else 4
        planner.piece_gap = lambda first, second: ((-10568.0, -4613.0), (-10658.0, -4763.0), gap)
        return planner

    def test_steps_across_a_short_gap_to_the_goals_piece(self):
        step = self.planner(175.0).gap_step((2467, 201), (-11333, -6232))
        self.assertEqual(step, GapStep((-10568.0, -4613.0), (-10658.0, -4763.0), (4, 1)))

    def test_no_step_within_one_piece_over_a_wide_gap_or_after_one_failed(self):
        self.assertIsNone(self.planner(175.0).gap_step((2467, 201), (-6107, -3249)))
        self.assertIsNone(self.planner(MAX_GAP_STEP + 1).gap_step((2467, 201), (-11333, -6232)))
        self.assertIsNone(self.planner(175.0).gap_step((2467, 201), (-11333, -6232), failed=[(4, 1)]))
        self.assertIsNone(RoutePlanner("zone").gap_step((0, 0), (1, 1)))


class WayAcrossTest(unittest.TestCase):
    """Triton Avenue: the Haunted Cave's door is on the upper level, 198 units across a gap from the street, and
    "Tele Up" lands there."""

    def planner(self, tele_up_standing_in=18):
        planner = RoutePlanner("WizardCity/WC_Streets/WC_Triton")
        planner.piece_of = lambda point, reach=150.0: 0 if point[1] > 5000 else 18
        planner.piece_gap = lambda first, second: ((-16100.0, 140.0), (-16300.0, 140.0), 198.0)
        planner.teleports = [(TeleportVolume("Tele Up", -16336.0, 1176.0, 0.0, 300.0), tele_up_standing_in)]
        return planner

    cave_door = (-37005.0, 6000.0)
    street = (-15000.0, 0.0)

    def test_a_teleporter_seen_to_land_in_the_goals_piece_comes_before_a_gap_step(self):
        way = self.planner().way_across(self.street, self.cave_door, {"Tele Up": 0})
        self.assertEqual(way.name, "Tele Up")

    def test_a_short_gap_is_stepped_across_when_no_teleporter_is_known_to_lead_there(self):
        way = self.planner().way_across(self.street, self.cave_door, {})
        self.assertEqual(way, GapStep((-16100.0, 140.0), (-16300.0, 140.0), (18, 0)))

    def test_after_a_failed_step_an_untried_teleporter_is_chosen(self):
        way = self.planner().way_across(self.street, self.cave_door, {}, failed_gaps=[(18, 0)])
        self.assertEqual(way.name, "Tele Up")

    def test_nothing_to_cross_within_one_piece(self):
        self.assertIsNone(self.planner().way_across(self.street, (-15000.0, 100.0), {"Tele Up": 0}))


class BlockedOnlyByDuelsTest(unittest.TestCase):
    """The Haunted Cave street: one way on, passing 887 units from another player's fight, with 900 kept clear."""

    def corridor_planner(self):
        vertices = [(480.0 * step, 0.0) for step in range(10)]
        edges = [(a, a + 1) for a in range(9)] + [(a + 1, a) for a in range(9)]
        return RoutePlanner("WizardCity/WC_Streets/WC_HauntedCave", nav_graph=NavGraph.from_edges(vertices, edges))

    start, goal = (0.0, 0.0), (4320.0, 0.0)

    def test_a_circle_beside_the_only_way_is_all_that_blocks_it(self):
        planner = self.corridor_planner()
        near = Hazards.of(duel_circles=[(2000.0, 887.0)])
        self.assertTrue(planner.blocked_only_by_duels(self.start, self.goal, near))
        self.assertTrue(planner.has_mapped_route(self.start, self.goal, Hazards.of(duel_circles=[(2000.0, 2000.0)])))

    def test_a_circle_far_from_the_way_blocks_nothing(self):
        planner = self.corridor_planner()
        far = Hazards.of(duel_circles=[(2000.0, 3000.0)])
        self.assertFalse(planner.blocked_only_by_duels(self.start, self.goal, far))
        self.assertFalse(planner.blocked_only_by_duels(self.start, self.goal, Hazards()))

    def test_a_goal_no_route_reaches_even_without_the_circles_is_not_blamed_on_them(self):
        cut_in_two = NavGraph.from_edges([(0.0, 0.0), (480.0, 0.0), (4000.0, 0.0), (4480.0, 0.0)],
                                         [(0, 1), (1, 0), (2, 3), (3, 2)])
        planner = RoutePlanner("zone", nav_graph=cut_in_two)
        hazards = Hazards.of(duel_circles=[(240.0, 800.0)])
        self.assertFalse(planner.blocked_only_by_duels((0.0, 0.0), (4480.0, 0.0), hazards))


class AfterAFailedStepTest(unittest.TestCase):
    """Coming out of the Haunted Cave gate puts the wizard on Triton Avenue's upper level (piece 0); the Headmistress's
    house is on the lower street (piece 18), 198 units across a ledge the wizard cannot cross."""

    def planner(self):
        planner = RoutePlanner("WizardCity/WC_Streets/WC_Triton")
        planner.piece_of = lambda point, reach=150.0: 0 if point[0] < -16200 else 18
        planner.piece_reaches = lambda piece, point, reach: piece == 0
        planner.piece_gap = lambda first, second: ((-16273.0, 110.0), (-16077.0, 140.0), 198.0)
        planner.teleports = [(TeleportVolume("Tele Up", -16336.0, 1176.0, 0.0, 177.0), 18),
                             (TeleportVolume("Tele Down", -17514.0, 1145.0, 0.0, 188.0), 0),
                             (TeleportVolume("To TempestNexus", -17564.0, -4043.0, 0.0, 185.0), 0)]
        return planner

    start, goal = (-17120.0, 880.0), (-16100.0, 140.0)

    def test_the_wizards_piece_reaching_the_goal_means_walk_there_until_a_step_failed(self):
        planner = self.planner()
        self.assertIsNone(planner.crossing(self.start, self.goal, {}))
        self.assertEqual(planner.crossing(self.start, self.goal, {}, failed_gaps=[(0, 18)]).name, "Tele Down")

    def test_after_the_step_failed_the_untried_volume_nearest_the_goal_is_walked_into(self):
        way = self.planner().way_across(self.start, self.goal, {}, failed_gaps=[(0, 18)])
        self.assertEqual(way.name, "Tele Down")

    def test_a_failed_step_for_other_pieces_changes_nothing(self):
        self.assertIsNone(self.planner().crossing(self.start, self.goal, {}, failed_gaps=[(18, 0)]))


class NearbyLandingTest(unittest.TestCase):
    """Triton Avenue: "Tele Down" is known to land in piece 20, 195 units from the lower street's piece 18, where
    the east gate is; a house door and the cave's gate on the upper level (piece 0) are untried."""

    def planner(self):
        planner = RoutePlanner("WizardCity/WC_Streets/WC_Triton")
        planner.piece_of = lambda point, reach=150.0: 0 if point[0] < -17000 else 18 if point[0] > -1000 else 20
        planner.piece_reaches = lambda piece, point, reach: False
        gaps = {(0, 18): 198.0, (20, 18): 195.0, (0, 20): 10465.0}
        planner.piece_gap = lambda first, second: ((0.0, 0.0), (1.0, 1.0), gaps.get((first, second),
                                                                                 gaps.get((second, first), 99999.0)))
        planner.teleports = [(TeleportVolume("Tele Down", -17514.0, 1145.0, 0.0, 188.0), 0),
                             (TeleportVolume("ThiefHouse", -23913.0, -6182.0, 0.0, 100.0), 0),
                             (TeleportVolume("Cavern", -37005.0, 3289.0, 0.0, 400.0), 0)]
        return planner

    start, gate = (-17120.0, 880.0), (6.0, 2477.0)
    seen = {"Tele Down": 20}

    def test_a_volume_seen_to_land_a_short_step_from_the_goal_comes_before_untried_ones(self):
        way = self.planner().way_across(self.start, self.gate, self.seen, failed_gaps=[(0, 18)])
        self.assertEqual(way.name, "Tele Down")

    def test_from_there_the_short_step_is_taken(self):
        landing = (-16500.0, 500.0)
        way = self.planner().way_across(landing, self.gate, self.seen, failed_gaps=[(0, 18)])
        self.assertIsInstance(way, GapStep)
        self.assertEqual(way.pieces, (20, 18))

    def test_a_landing_whose_step_already_failed_is_not_used(self):
        way = self.planner().way_across(self.start, self.gate, self.seen, failed_gaps=[(0, 18), (20, 18)])
        self.assertNotEqual(way.name, "Tele Down")

    def test_without_a_known_landing_an_untried_volume_is_chosen(self):
        way = self.planner().way_across(self.start, self.gate, {}, failed_gaps=[(0, 18)])
        self.assertEqual(way.name, "Tele Down")


def nav_file(waypoints, links) -> bytes:
    data = bytearray(b"\x00\x00") + struct.pack("<i", len(waypoints))
    for (x, y, z), number in waypoints:
        data += struct.pack("<fffh", x, y, z, number)
    data += struct.pack("<i", len(links))
    for a, b in links:
        data += struct.pack("<hh", a, b)
    return bytes(data)


class NavFileTest(unittest.TestCase):
    def test_reads_waypoints_and_links(self):
        data = nav_file([((0, 0, 0), 0), ((480, 0, 0), 1), ((480, 480, 0), 2)], [(0, 1), (1, 0), (1, 2), (2, 1)])
        waypoints, links = parse_nav_file(data)
        self.assertEqual(waypoints, [(0.0, 0.0, 0.0), (480.0, 0.0, 0.0), (480.0, 480.0, 0.0)])
        self.assertEqual(links, [(0, 1), (1, 0), (1, 2), (2, 1)])

    def test_keeps_the_waypoints_before_a_number_out_of_place(self):
        """Olde Town's file numbers its 352nd waypoint 350 again."""
        data = nav_file([((0, 0, 0), 0), ((480, 0, 0), 1), ((960, 0, 0), 1), ((7000, 0, 0), 2)],
                        [(0, 1), (1, 0), (1, 2), (2, 3)])
        waypoints, links = parse_nav_file(data)
        self.assertEqual(len(waypoints), 2)
        self.assertEqual(links, [(0, 1), (1, 0)])

if __name__ == "__main__":
    unittest.main()
