import math
import unittest

from wizardtraining.patrols import PatrolMap
from wizardtraining.routes import (COLLISION, DUEL_CIRCLE_NO_GO, LEG_ENEMY_CLEARANCE, NAV, OBSTACLE_RADIUS, STRAIGHT,
                                   Hazards, NavGraph, RoutePlanner, grid_path, no_more_dangerous, string_pull)

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

    def test_unknown_method_is_an_error(self):
        with self.assertRaises(ValueError):
            RoutePlanner("zone").route("teleport", (0, 0), (1, 1))


if __name__ == "__main__":
    unittest.main()
