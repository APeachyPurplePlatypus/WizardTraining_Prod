"""Load a zone's walk data from the installed game files into a `RoutePlanner`.

- zone.nav: read with WizWalker's `pharse_nav_data` (the library's own spelling).
- collision.bcd: Deimos builds a walk grid from it (src/collision.py, ISC; src/collision_math.py,
  GPL-3.0, which also needs numpy and shapely). Deimos is not an installable package, so its checkout
  is named in WIZARDTRAINING_DEIMOS. Without it the "collision" method is skipped and routes use the
  nav graph, then a straight line.
"""

from __future__ import annotations

import sys
from pathlib import Path

from wizwalker import XYZ, Wad
from wizwalker.utils import pharse_nav_data

from .config import DEIMOS_VARIABLE
from .routes import NavGraph, RoutePlanner


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
        collision_world, get_walk_grid, straight_path_walkable = _deimos_collision(deimos_root)
        world = collision_world()
        world.load(await wad.get_file("collision.bcd"))
        grid = get_walk_grid(world, zone)
    except Exception as exc:
        return None, None, f"unavailable: {type(exc).__name__}"
    if not grid.has_mesh:
        return None, None, "no walkable mesh"

    def line_walkable(a, b) -> bool:
        return straight_path_walkable(world, zone, XYZ(a[0], a[1], 0.0), XYZ(b[0], b[1], 0.0))

    return grid, line_walkable, f"{len(world.objects)} objects"


def _deimos_collision(deimos_root: Path):
    if str(deimos_root) not in sys.path:
        sys.path.insert(0, str(deimos_root))
    from src.collision import CollisionWorld
    from src.collision_math import get_walk_grid, straight_path_walkable
    return CollisionWorld, get_walk_grid, straight_path_walkable


async def _nav_graph(wad):
    try:
        vertices, edges = pharse_nav_data(await wad.get_file("zone.nav"))
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"
    return NavGraph.from_edges(vertices, edges), f"{len(vertices)} waypoints"
