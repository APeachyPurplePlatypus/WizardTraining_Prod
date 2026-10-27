import math
import unittest

from wizardtraining.patrols import PatrolMap
from wizardtraining.routes import (COLLISION, DUEL_CIRCLE_NO_GO, GOAL_PIECE_REACH, LEG_ENEMY_CLEARANCE, NAV,
                                   OBSTACLE_RADIUS, STRAIGHT, Hazards, NavGraph, RoutePlanner, grid_path,
                                   no_more_dangerous, string_pull)
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


if __name__ == "__main__":
    unittest.main()
