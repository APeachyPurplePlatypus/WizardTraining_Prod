"""Route search over a zone's walk data. No game access, so it is tested offline.

Three methods, tried in this order by `movement.travel`:
1. "collision": a hex walk grid over the zone's walkable mesh, built by Deimos from collision.bcd.
2. "nav": the zone's zone.nav waypoint graph.
3. "straight": one straight leg to the destination, only where it keeps clear of enemies and, when walk data
   loaded, crosses no patrol path its ends are not already on.

Grid and graph routes are searched with A*, then merged into as few straight legs as the walk data
allows ("string pulling"). Steps near enemies cost more, so routes keep to the parts of a street that
enemies are not on, and merged legs keep LEG_ENEMY_CLEARANCE from them. Steps near the zone's enemy patrol
paths cost more too (`patrols.PatrolMap`), so routes prefer the sidewalks enemies do not walk, and merging
never makes a leg more dangerous than the steps it replaces. Enemies with a track (`motion.Track`) are no-go
areas ENEMY_KEEP_OUT wide where they will be when the wizard gets there, so a route passes behind an enemy
walking away and keeps clear of where one is heading. Duel circles, other players'
fights in progress, are no-go areas: walking into one joins that fight. So are obstacles: places where the
wizard was blocked although the walk data said the way was clear.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field, replace
from typing import Callable

from .geometry import Point, distance_to_segment, path_beyond, xy
from .motion import WALK_UNITS_PER_SECOND
from .teleports import TeleportVolume, choose_crossing

COLLISION, NAV, STRAIGHT = "collision", "nav", "straight"
ENEMY_AVOID_RADIUS = 900.0
ENEMY_AVOID_WEIGHT = 6.0
LEG_ENEMY_CLEARANCE = 450.0
DUEL_CIRCLE_NO_GO = 900.0
OBSTACLE_RADIUS = 150.0
PATROL_AVOID_RADIUS = 700.0
PATROL_AVOID_WEIGHT = 4.0
MERGE_DANGER_TOLERANCE = 0.25
NAV_GRID_SPACING = 480.0
NAV_CELL_REACH = NAV_GRID_SPACING * math.sqrt(2) / 2
LINE_SAMPLE_SPACING = 60.0
MAX_MERGE_LOOKAHEAD = 40
MAX_GRID_NODES = 60_000
PLANNING_SECONDS = 4.0
REROUTE_DISTANCE = 2500.0
REROUTE_SECONDS = 0.25
GOAL_PIECE_REACH = 600.0
TELEPORT_CLEARANCE = 60.0
ENEMY_KEEP_OUT = 520.0


@dataclass(frozen=True)
class Hazards:
    """Enemies to keep away from, and duel circles and obstacles never to enter, as (x, y) points. `keep_out` are
    other no-go circles as ((x, y), radius): teleport volumes the walk is not going to. `tracks` are enemies
    never to come within ENEMY_KEEP_OUT of, where they will be when the wizard gets there."""
    enemies: tuple[Point, ...] = ()
    duel_circles: tuple[Point, ...] = ()
    obstacles: tuple[Point, ...] = ()
    patrols: object = field(default=None, compare=False)
    keep_out: tuple[tuple[Point, float], ...] = ()
    tracks: tuple = ()

    @classmethod
    def of(cls, enemies=(), duel_circles=(), obstacles=(), patrols=None, keep_out=(), tracks=()) -> "Hazards":
        return cls(tuple(xy(enemy) for enemy in enemies), tuple(xy(circle) for circle in duel_circles),
                   tuple(xy(obstacle) for obstacle in obstacles), patrols,
                   tuple((xy(centre), radius) for centre, radius in keep_out), tuple(tracks))

    def with_obstacles(self, obstacles) -> "Hazards":
        return replace(self, obstacles=self.obstacles + tuple(xy(obstacle) for obstacle in obstacles))

    def step_cost(self, point: Point) -> float:
        """1 away from enemies and patrol paths, rising by up to ENEMY_AVOID_WEIGHT on top of an enemy and by up to
        PATROL_AVOID_WEIGHT on a patrol path."""
        cost = 1.0
        if self.enemies:
            nearest = min(math.dist(point, enemy) for enemy in self.enemies)
            cost += ENEMY_AVOID_WEIGHT * max(0.0, 1.0 - nearest / ENEMY_AVOID_RADIUS)
        if self.patrols:
            cost += PATROL_AVOID_WEIGHT * max(0.0, 1.0 - self.patrols.distance(point, PATROL_AVOID_RADIUS)
                                              / PATROL_AVOID_RADIUS)
        return cost

    def line_cost(self, a: Point, b: Point) -> float:
        """The highest step cost along a straight line, sampled every LINE_SAMPLE_SPACING units."""
        samples = max(1, int(math.dist(a, b) // LINE_SAMPLE_SPACING))
        return max(self.step_cost((a[0] + (b[0] - a[0]) * k / samples, a[1] + (b[1] - a[1]) * k / samples))
                   for k in range(samples + 1))

    def clear_around(self, point, radius: float) -> "Hazards":
        """Without the obstacles within `radius` of `point`: bumping into the NPC a trip is going to must not
        make that NPC unreachable."""
        point = xy(point)
        return replace(self, obstacles=tuple(o for o in self.obstacles if math.dist(o, point) > radius))

    def forbids(self, point: Point, seconds: float = 0.0) -> bool:
        """Whether the wizard may not be at `point`, reached `seconds` from now."""
        return (any(math.dist(point, circle) < DUEL_CIRCLE_NO_GO for circle in self.duel_circles)
                or any(math.dist(point, obstacle) < OBSTACLE_RADIUS for obstacle in self.obstacles)
                or any(math.dist(point, centre) < radius for centre, radius in self.keep_out)
                or self.enemy_will_be_near(point, seconds))

    def enemy_will_be_near(self, point: Point, seconds: float) -> bool:
        return any(math.dist(point, track.at(seconds)) < ENEMY_KEEP_OUT for track in self.tracks)

    def line_is_open(self, a: Point, b: Point, seconds: float = 0.0) -> bool:
        """The line enters no duel circle, obstacle or keep-out circle, and no tracked enemy will be near it as
        the wizard walks it, reaching `a` `seconds` from now."""
        return (all(distance_to_segment(circle, a, b) >= DUEL_CIRCLE_NO_GO for circle in self.duel_circles)
                and all(distance_to_segment(obstacle, a, b) >= OBSTACLE_RADIUS for obstacle in self.obstacles)
                and all(distance_to_segment(centre, a, b) >= radius for centre, radius in self.keep_out)
                and self.line_clear_of_tracks(a, b, seconds))

    def line_clear_of_tracks(self, a: Point, b: Point, seconds: float) -> bool:
        if not self.tracks:
            return True
        length = math.dist(a, b)
        samples = max(1, int(length // LINE_SAMPLE_SPACING))
        for k in range(samples + 1):
            point = (a[0] + (b[0] - a[0]) * k / samples, a[1] + (b[1] - a[1]) * k / samples)
            if self.enemy_will_be_near(point, seconds + length * k / samples / WALK_UNITS_PER_SECOND):
                return False
        return True

    def line_is_safe(self, a: Point, b: Point, seconds: float = 0.0) -> bool:
        return (self.line_is_open(a, b, seconds)
                and all(distance_to_segment(enemy, a, b) >= LEG_ENEMY_CLEARANCE for enemy in self.enemies))


@dataclass
class NavGraph:
    """zone.nav waypoints as (x, y), and for each waypoint index the indices it links to."""
    vertices: list[Point]
    adjacent: dict[int, list[int]] = field(default_factory=dict)

    @classmethod
    def from_edges(cls, vertices, edges) -> "NavGraph":
        adjacent = {index: [] for index in range(len(vertices))}
        for a, b in edges:
            adjacent[a].append(b)
        return cls([xy(vertex) for vertex in vertices], adjacent)

    def nearest(self, point: Point) -> int:
        return min(range(len(self.vertices)), key=lambda index: math.dist(point, self.vertices[index]))

    def covers_line(self, a: Point, b: Point) -> bool:
        """Every sample along the line lies within one nav cell of a waypoint, so it stays on walkable ground."""
        samples = max(1, int(math.dist(a, b) // LINE_SAMPLE_SPACING))
        for k in range(samples + 1):
            point = (a[0] + (b[0] - a[0]) * k / samples, a[1] + (b[1] - a[1]) * k / samples)
            if min(math.dist(point, vertex) for vertex in self.vertices) > NAV_CELL_REACH:
                return False
        return True

    def path(self, start: Point, goal: Point, hazards: Hazards) -> list[int] | None:
        source, target = self.nearest(start), self.nearest(goal)
        frontier, came_from, cost = [(0.0, source)], {source: None}, {source: 0.0}
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == target:
                return walk_back(came_from, current)
            for neighbour in self.adjacent[current]:
                where = self.vertices[neighbour]
                if hazards.forbids(where, seconds_to_reach(start, where)):
                    continue
                total = cost[current] + math.dist(self.vertices[current], where) * hazards.step_cost(where)
                if total < cost.get(neighbour, math.inf):
                    cost[neighbour], came_from[neighbour] = total, current
                    heapq.heappush(frontier, (total + math.dist(where, self.vertices[target]), neighbour))
        return None


def grid_path(grid, start: Point, goal: Point, hazards: Hazards, seconds: float = PLANNING_SECONDS) -> list[Point] | None:
    """A* over the walk grid's cells. Gives up after MAX_GRID_NODES cells or `seconds`, because an unbounded
    search in a large interior stalled a walk for minutes.

    `grid` follows Deimos's walk grid: to_hex, to_world, neighbours, walk_z, _nearest_walk_node, spacing."""
    source, target = walkable_cell_near(grid, start), walkable_cell_near(grid, goal)
    if source is None or target is None:
        return None
    target_xy = grid.to_world(*target)
    frontier, came_from, cost, settled = [(0.0, 0.0, source)], {source: None}, {source: 0.0}, set()
    give_up_at = time.monotonic() + seconds
    while frontier and len(settled) < MAX_GRID_NODES and time.monotonic() < give_up_at:
        _, spent, current = heapq.heappop(frontier)
        if current in settled:
            continue
        settled.add(current)
        if current == target:
            return [grid.to_world(*cell) for cell in walk_back(came_from, current)]
        for neighbour in grid.neighbours(*current):
            if neighbour in settled or grid.walk_z(*neighbour) is None:
                continue
            where = grid.to_world(*neighbour)
            if hazards.forbids(where, seconds_to_reach(start, where)):
                continue
            total = spent + grid.spacing * hazards.step_cost(where)
            if total < cost.get(neighbour, math.inf):
                cost[neighbour], came_from[neighbour] = total, current
                heapq.heappush(frontier, (total + math.dist(where, target_xy), total, neighbour))
    return None


def seconds_to_reach(start: Point, point: Point) -> float:
    """When the wizard reaches `point`, at the soonest: the straight-line distance at walking speed. Searches use
    it to ask where enemies will be by then."""
    return math.dist(start, point) / WALK_UNITS_PER_SECOND


def arrival_times(points: list[Point]) -> list[float]:
    """Seconds until the wizard reaches each point, walking them in order from the first."""
    times, walked = [0.0], 0.0
    for a, b in zip(points, points[1:]):
        walked += math.dist(a, b)
        times.append(walked / WALK_UNITS_PER_SECOND)
    return times


def walkable_cell_near(grid, point: Point):
    cell = grid.to_hex(*point)
    return cell if grid.walk_z(*cell) is not None else grid._nearest_walk_node(*cell)


def walk_back(came_from: dict, last) -> list:
    path = []
    while last is not None:
        path.append(last)
        last = came_from[last]
    return path[::-1]


def string_pull(points: list[Point], straight_line_ok: Callable[[int, int], bool]) -> list[Point]:
    """From each point, jump to the farthest later point a straight line can reach; `straight_line_ok` gets the
    two points' indices. Neighbouring points are always joined, so every point is reachable. The start is not
    repeated in the result."""
    legs, i = [], 0
    while i < len(points) - 1:
        j = min(len(points) - 1, i + MAX_MERGE_LOOKAHEAD)
        while j > i + 1 and not straight_line_ok(i, j):
            j -= 1
        legs.append(points[j])
        i = j
    return legs


def no_more_dangerous(points: list[Point], hazards: "Hazards") -> Callable[[int, int], bool]:
    """A check for string pulling: the straight line from point i to point j is no more dangerous than the most
    dangerous of the points it replaces, so merging never cuts back across a patrol path."""
    costs = [hazards.step_cost(point) for point in points]

    def ok(i: int, j: int) -> bool:
        return hazards.line_cost(points[i], points[j]) <= max(costs[i:j + 1]) + MERGE_DANGER_TOLERANCE
    return ok


class RoutePlanner:
    """Plans routes in one zone from whichever walk data loaded. `status` says what loaded, or why not."""

    def __init__(self, zone: str, *, walk_grid=None, grid_line_walkable: Callable[[Point, Point], bool] | None = None,
                 nav_graph: NavGraph | None = None, status: dict | None = None):
        self.zone = zone
        self.walk_grid = walk_grid
        self.grid_line_walkable = grid_line_walkable
        self.nav_graph = nav_graph
        self.status = status or {}
        self.piece_of: Callable[..., int | None] | None = None
        self.piece_reaches: Callable[[int, Point, float], bool] | None = None
        self.teleports: list[tuple[TeleportVolume, int | None]] = []
        self.placed_objects: list = []
        self.exploration_points: list[tuple[Point, int]] = []
        self.patrols = None

    def crossing(self, start, goal, outcomes: dict[str, object]) -> TeleportVolume | None:
        """A teleport volume to walk into when `goal` lies in another walkable piece than `start`, or None
        when they are in the same piece, the pieces are unknown, or no volume is left to try.

        Doors stand in walls, and NPCs and quest objects often behind counters, outside the walkable area: a
        goal belongs to the nearest piece within GOAL_PIECE_REACH. But when the wizard's own piece also comes
        within GOAL_PIECE_REACH of the goal, or the zone's nav graph links the two, it walks there. Ravenwood's
        walkway to the Commons is missing from its collision mesh, so its gate lay in a sliver of walkable
        ground of its own, and a crossing toward that sliver walked into the school doors instead."""
        if self.piece_of is None:
            return None
        start_piece, goal_piece = self.piece_of(xy(start)), self.piece_of(xy(goal), GOAL_PIECE_REACH)
        if start_piece is None or goal_piece is None or start_piece == goal_piece:
            return None
        if self.piece_reaches is not None and self.piece_reaches(start_piece, xy(goal), GOAL_PIECE_REACH):
            return None
        if self.nav_links(start, goal):
            return None
        return choose_crossing(self.teleports, start_piece=start_piece, goal_piece=goal_piece, outcomes=outcomes,
                               goal=goal)

    def nav_links(self, start, goal) -> bool:
        """Whether the nav graph has a path from a waypoint within GOAL_PIECE_REACH of `start` to one within it of
        `goal`."""
        if self.nav_graph is None or not self.nav_graph.vertices:
            return False
        start, goal = xy(start), xy(goal)
        waypoints = self.nav_graph.path(start, goal, Hazards())
        if not waypoints:
            return False
        first, last = self.nav_graph.vertices[waypoints[0]], self.nav_graph.vertices[waypoints[-1]]
        return math.dist(first, start) <= GOAL_PIECE_REACH and math.dist(last, goal) <= GOAL_PIECE_REACH

    def teleports_to_keep_out_of(self, start, destination, arrive_radius: float) -> list[tuple[Point, float]]:
        """The teleport volumes a walk from `start` to `destination` must not cross, as circles TELEPORT_CLEARANCE
        wider than the volume: walking through one changes the zone. Left out: a volume at the destination,
        which may be the door the walk is for; one the wizard stands at, as it does after coming through it;
        and volumes on another walkable piece, such as another level, which the walk cannot reach."""
        here, goal = xy(start), xy(destination)
        start_piece = self.piece_of(here) if self.piece_of is not None else None
        circles = []
        for volume, piece in self.teleports:
            centre, keep_out = (volume.x, volume.y), volume.radius + TELEPORT_CLEARANCE
            if math.dist(centre, goal) <= keep_out + arrive_radius or math.dist(centre, here) <= keep_out:
                continue
            if start_piece is not None and piece is not None and piece != start_piece:
                continue
            circles.append((centre, keep_out))
        return circles

    def methods(self) -> list[str]:
        usable = []
        if self.walk_grid is not None and self.grid_line_walkable is not None:
            usable.append(COLLISION)
        if self.nav_graph is not None and self.nav_graph.vertices:
            usable.append(NAV)
        return usable + [STRAIGHT]

    def straight_line_ok(self, a: Point, b: Point, hazards: Hazards) -> bool:
        """A straight leg has nothing keeping it on the sidewalks, so it must stay clear of enemies, and when walk
        data loaded it may be no more dangerous than its ends: a straight line to a door once cut across a
        street of patrolling Scarlet Screamers after the walk-data route was blocked."""
        if not hazards.line_is_safe(a, b):
            return False
        if self.methods() == [STRAIGHT]:
            return True
        ends = max(hazards.step_cost(a), hazards.step_cost(b))
        return hazards.line_cost(a, b) <= ends + MERGE_DANGER_TOLERANCE

    def walls_allow(self, a: Point, b: Point) -> bool:
        return self.grid_line_walkable is None or self.grid_line_walkable(a, b)

    def reroute(self, path_ahead, hazards: Hazards) -> list[Point] | None:
        """A new way from the wizard, the first point of `path_ahead`: the next REROUTE_DISTANCE planned again
        around `hazards`, within REROUTE_SECONDS, then the rest of the old route. It runs while the wizard
        keeps walking, so it uses the walk data only, never a straight line. None when no way is found."""
        joint, *rest = path_beyond(path_ahead, REROUTE_DISTANCE)
        for method in self.methods():
            if method == STRAIGHT:
                continue
            legs = self.route(method, path_ahead[0], joint, hazards, seconds=REROUTE_SECONDS)
            if legs:
                return [*legs, *rest]
        return None

    def route(self, method: str, start, goal, hazards: Hazards = Hazards(),
              seconds: float = PLANNING_SECONDS) -> list[Point] | None:
        """Waypoints after the start, the goal last, or None when this method finds no route."""
        start, goal = xy(start), xy(goal)
        if method == COLLISION:
            cells = grid_path(self.walk_grid, start, goal, hazards, seconds)
            if cells is None:
                return None
            points = [start, *cells, goal]
            danger_ok, times = no_more_dangerous(points, hazards), arrival_times(points)
            return string_pull(points, lambda i, j: self.grid_line_walkable(points[i], points[j])
                               and hazards.line_is_safe(points[i], points[j], times[i]) and danger_ok(i, j))
        if method == NAV:
            waypoints = self.nav_graph.path(start, goal, hazards)
            if waypoints is None:
                return None
            points = [start, *(self.nav_graph.vertices[index] for index in waypoints), goal]
            danger_ok, times = no_more_dangerous(points, hazards), arrival_times(points)
            return string_pull(points, lambda i, j: self.nav_graph.covers_line(points[i], points[j])
                               and self.walls_allow(points[i], points[j])
                               and hazards.line_is_safe(points[i], points[j], times[i]) and danger_ok(i, j))
        if method == STRAIGHT:
            return [goal] if self.straight_line_ok(start, goal, hazards) else None
        raise ValueError(f"unknown route method {method!r}")
