"""Load a zone's walk data from the installed game files into a `RoutePlanner`.

- zone.nav: read with WizWalker's `pharse_nav_data` (the library's own spelling).
- collision.bcd: Deimos builds a walk grid from it (src/collision.py, ISC; src/collision_math.py,
  GPL-3.0, which also needs numpy and shapely). Deimos is not an installable package, so its checkout
  is named in WIZARDTRAINING_DEIMOS. Without it the "collision" method is skipped and routes use the
  nav graph, then a straight line.

Deimos's walk grid and `straight_path_walkable` check only the walkable navmesh, not the collision walls
in collision.bcd: Deimos walks through some volumes that only block teleports. In the Commons, trees,
fences and buildings are such walls, and walking into them stalled every route. So the wizard's free
area is the navmesh minus Deimos's height-aware walls (`zone_bcd_walls`) padded by WALL_CLEARANCE, and
grid cells and straight legs must stay inside it.
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path

from wizwalker import Wad
from wizwalker.utils import pharse_nav_data

from .config import DEIMOS_VARIABLE
from .routes import NavGraph, RoutePlanner
from .patrols import PatrolMap, parse_nodes, parse_paths
from .placed import parse_placed_objects
from .teleports import parse_teleport_volumes

WALL_CLEARANCE = 30.0
EXPLORE_SPACING = 2500.0
MAX_CELLS_SEARCHED_FOR_A_FREE_ONE = 2000
PIECE_REACH = 150.0


async def load_planner(zone: str, deimos_root: Path | None) -> RoutePlanner:
    try:
        wad = Wad.from_game_data(zone.replace("/", "-"))
    except Exception as exc:
        reason = f"no zone file: {type(exc).__name__}"
        return RoutePlanner(zone, status={"collision": reason, "nav": reason})
    walk_grid, free, collision_status = await _collision_grid(wad, zone, deimos_root)
    nav_graph, nav_status = await _nav_graph(wad)
    volumes, teleport_status = await _teleport_volumes(wad)
    placed, placed_status = await _placed_objects(wad)
    patrols, patrol_status = await _patrols(wad)
    planner = RoutePlanner(zone, walk_grid=walk_grid, grid_line_walkable=free.contains_line if free else None,
                           nav_graph=nav_graph,
                           status={"collision": collision_status, "nav": nav_status, "teleports": teleport_status,
                                   "placed objects": placed_status, "patrols": patrol_status})
    planner.placed_objects = placed
    planner.patrols = patrols
    if free is not None:
        planner.piece_of = free.piece_of
        planner.piece_reaches = free.reaches
        planner.teleports = [(volume, free.piece_of(volume.point, volume.radius + PIECE_REACH)) for volume in volumes]
        planner.exploration_points = free.exploration_points(EXPLORE_SPACING)
    return planner


async def _collision_grid(wad, zone: str, deimos_root: Path | None):
    if deimos_root is None:
        return None, None, f"skipped: {DEIMOS_VARIABLE} is not set"
    try:
        from shapely.ops import unary_union
        deimos = _deimos_collision(deimos_root)
        world = deimos.CollisionWorld()
        world.load(await wad.get_file("collision.bcd"))
        grid = deimos.get_walk_grid(world, zone)
        if not grid.has_mesh:
            return None, None, "no walkable mesh"
        footprints = await asyncio.to_thread(deimos.placed_object_footprints, zone)
        blocked = unary_union([deimos.zone_bcd_walls(world, zone), *footprints])
        free_area = deimos.walkable_union(world, zone).difference(blocked.buffer(WALL_CLEARANCE))
    except Exception as exc:
        return None, None, f"unavailable: {type(exc).__name__}"
    free = FreeArea(free_area)
    return WallAwareGrid(grid, free), free, (f"{len(world.objects)} objects, {len(footprints)} placed-object footprints, "
                                             f"walls avoided, {free.piece_count} pieces")


class FreeArea:
    """Where the wizard's body fits: the navmesh minus the padded collision walls. It can come in separate
    pieces with no walkable path between them, such as the two levels of Triton Avenue."""

    def __init__(self, area):
        import shapely
        from shapely.geometry import LineString, Point
        shapely.prepare(area)
        self._area, self._line, self._point, self._contains_xy = area, LineString, Point, shapely.contains_xy
        self._pieces = list(getattr(area, "geoms", [area]))

    @property
    def piece_count(self) -> int:
        return len(self._pieces)

    def exploration_points(self, spacing: float) -> list[tuple[tuple[float, float], int]]:
        """One walkable point per `spacing`-sized square of each piece, with the piece's index: places to go
        and look when a goal's targets are not in sight."""
        from shapely.geometry import box
        points = []
        for index, piece in enumerate(self._pieces):
            min_x, min_y, max_x, max_y = piece.bounds
            x = min_x
            while x < max_x:
                y = min_y
                while y < max_y:
                    part = piece.intersection(box(x, y, x + spacing, y + spacing))
                    if not part.is_empty and part.area > spacing * spacing * 0.05:
                        where = part.representative_point()
                        points.append(((where.x, where.y), index))
                    y += spacing
                x += spacing
        return points

    def piece_of(self, point, reach: float = PIECE_REACH) -> int | None:
        """The index of the piece within `reach` of `point`, the nearest one if several, or None."""
        where = self._point(*point)
        distances = [piece.distance(where) for piece in self._pieces]
        nearest = min(range(len(distances)), key=distances.__getitem__, default=None)
        return nearest if nearest is not None and distances[nearest] <= reach else None

    def reaches(self, index: int, point, reach: float) -> bool:
        """Whether piece `index` comes within `reach` of `point`."""
        return self._pieces[index].distance(self._point(*point)) <= reach

    def contains_point(self, x: float, y: float) -> bool:
        return bool(self._contains_xy(self._area, x, y))

    def contains_line(self, a, b) -> bool:
        if a[0] == b[0] and a[1] == b[1]:
            return self.contains_point(*a)
        return self._area.contains(self._line([a, b]))


class WallAwareGrid:
    """Deimos's walk grid, with every cell outside the free area treated as unwalkable."""

    def __init__(self, grid, free: FreeArea):
        self._grid, self._free = grid, free
        self.spacing = grid.spacing

    def to_hex(self, x, y):
        return self._grid.to_hex(x, y)

    def to_world(self, q, r):
        return self._grid.to_world(q, r)

    def neighbours(self, q, r):
        return self._grid.neighbours(q, r)

    def walk_z(self, q, r):
        z = self._grid.walk_z(q, r)
        return z if z is not None and self._free.contains_point(*self.to_world(q, r)) else None

    def _nearest_walk_node(self, q, r):
        """The closest free cell, searching outward through neighbouring cells."""
        seen, queue = {(q, r)}, deque([(q, r)])
        while queue and len(seen) < MAX_CELLS_SEARCHED_FOR_A_FREE_ONE:
            cell = queue.popleft()
            if self.walk_z(*cell) is not None:
                return cell
            for neighbour in self.neighbours(*cell):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return None


class _DeimosCollision:
    def __init__(self):
        from src.collision import CollisionWorld
        from src.collision_math import _walkable_union, get_walk_grid, zone_bcd_walls
        self.CollisionWorld, self.get_walk_grid = CollisionWorld, get_walk_grid
        self.walkable_union, self.zone_bcd_walls = _walkable_union, zone_bcd_walls

    @staticmethod
    def placed_object_footprints(zone: str) -> list:
        """The footprints of the zone's placed objects (tents, trees, crates), from Deimos's model reader, or
        none when its optional packages (katsuba 0.4, kinif, wiztype) are missing. collision.bcd leaves these
        out: Cyclops Lane's fairground tents were walked into on every collision route."""
        try:
            from src.entity_collision import build_zone_static_shapes
            return build_zone_static_shapes(zone, None)
        except Exception:
            return []


def _deimos_collision(deimos_root: Path) -> _DeimosCollision:
    if str(deimos_root) not in sys.path:
        sys.path.insert(0, str(deimos_root))
    return _DeimosCollision()


async def _patrols(wad):
    try:
        patrols = PatrolMap.from_paths(parse_nodes(await wad.get_file("pathNodeData.bin")),
                                       parse_paths(await wad.get_file("pathData.xml")))
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"
    return (patrols, f"{len(patrols.segments)} enemy patrol segments") if patrols else (None, "no enemy patrols")


async def _placed_objects(wad):
    try:
        placed = parse_placed_objects(await wad.get_file("gamedata.bin"))
    except Exception as exc:
        return [], f"unavailable: {type(exc).__name__}"
    return placed, f"{len(placed)} placed objects"


async def _teleport_volumes(wad):
    try:
        volumes = parse_teleport_volumes(await wad.get_file("volumes.xml"))
    except Exception as exc:
        return [], f"unavailable: {type(exc).__name__}"
    return volumes, f"{len(volumes)} teleport volumes"


async def _nav_graph(wad):
    try:
        vertices, edges = pharse_nav_data(await wad.get_file("zone.nav"))
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"
    return NavGraph.from_edges(vertices, edges), f"{len(vertices)} waypoints"
