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

import sys
from collections import deque
from pathlib import Path

from wizwalker import Wad
from wizwalker.utils import pharse_nav_data

from .config import DEIMOS_VARIABLE
from .routes import NavGraph, RoutePlanner

WALL_CLEARANCE = 30.0
MAX_CELLS_SEARCHED_FOR_A_FREE_ONE = 2000


async def load_planner(zone: str, deimos_root: Path | None) -> RoutePlanner:
    try:
        wad = Wad.from_game_data(zone.replace("/", "-"))
    except Exception as exc:
        reason = f"no zone file: {type(exc).__name__}"
        return RoutePlanner(zone, status={"collision": reason, "nav": reason})
    walk_grid, line_walkable, collision_status = await _collision_grid(wad, zone, deimos_root)
    nav_graph, nav_status = await _nav_graph(wad)
    return RoutePlanner(zone, walk_grid=walk_grid, grid_line_walkable=line_walkable, nav_graph=nav_graph,
                        status={"collision": collision_status, "nav": nav_status})


async def _collision_grid(wad, zone: str, deimos_root: Path | None):
    if deimos_root is None:
        return None, None, f"skipped: {DEIMOS_VARIABLE} is not set"
    try:
        deimos = _deimos_collision(deimos_root)
        world = deimos.CollisionWorld()
        world.load(await wad.get_file("collision.bcd"))
        grid = deimos.get_walk_grid(world, zone)
        if not grid.has_mesh:
            return None, None, "no walkable mesh"
        free_area = deimos.walkable_union(world, zone).difference(deimos.zone_bcd_walls(world, zone).buffer(WALL_CLEARANCE))
    except Exception as exc:
        return None, None, f"unavailable: {type(exc).__name__}"
    free = FreeArea(free_area)
    return WallAwareGrid(grid, free), free.contains_line, f"{len(world.objects)} objects, walls avoided"


class FreeArea:
    """Where the wizard's body fits: the navmesh minus the padded collision walls."""

    def __init__(self, area):
        from shapely.geometry import LineString, Point
        from shapely.prepared import prep
        self._area, self._line, self._point = prep(area), LineString, Point

    def contains_point(self, x: float, y: float) -> bool:
        return self._area.contains(self._point(x, y))

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


def _deimos_collision(deimos_root: Path) -> _DeimosCollision:
    if str(deimos_root) not in sys.path:
        sys.path.insert(0, str(deimos_root))
    return _DeimosCollision()


async def _nav_graph(wad):
    try:
        vertices, edges = pharse_nav_data(await wad.get_file("zone.nav"))
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"
    return NavGraph.from_edges(vertices, edges), f"{len(vertices)} waypoints"
