"""Load a zone's walk data from the installed game files into a `RoutePlanner`.

- zone.nav: read by `routes.parse_nav_file`, which keeps the waypoints up to the first whose number is out of place,
  where WizWalker's `pharse_nav_data` gives up on the whole file.
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

from .config import DEIMOS_VARIABLE
from .routes import NavGraph, RoutePlanner, parse_nav_file
from .patrols import PatrolMap, parse_nodes, parse_paths
from .placed import PlacedObject, parse_placed_objects
from .training import DOWN_VOLUMES
from .untracked import WALK_IN_RADIUS, parse_trigger_volumes, walk_in_teleports
from .teleports import TeleportVolume, parse_teleport_volumes

WALL_CLEARANCE = 45.0
BODY_HEIGHT = 135.0
FLOOR_TOLERANCE = 8.0
Z_EMBED_TOL = 75.0
Z_BOX_TOL = 20.0
EXPLORE_SPACING = 2500.0
MAX_CELLS_SEARCHED_FOR_A_FREE_ONE = 2000
PIECE_REACH = 150.0
NO_PATROLS = "no enemy patrols"


async def load_planner(zone: str, deimos_root: Path | None) -> RoutePlanner:
    try:
        wad = Wad.from_game_data(zone.replace("/", "-"))
    except Exception as exc:
        reason = f"no zone file: {type(exc).__name__}"
        return RoutePlanner(zone, status={"collision": reason, "nav": reason})
    walk_grid, free, collision_status = await _collision_grid(wad, zone, deimos_root)
    nav_graph, nav_status = await _nav_graph(wad)
    volumes, teleport_status = await _teleport_volumes(wad)
    placed, zone_data, placed_status = await _placed_objects(wad, zone, deimos_root)
    patrols, patrol_status = await _patrols(wad)
    planner = RoutePlanner(zone, walk_grid=walk_grid, grid_line_walkable=free.contains_line if free else None,
                           nav_graph=nav_graph,
                           status={"collision": collision_status, "nav": nav_status, "teleports": teleport_status,
                                   "placed objects": placed_status, "patrols": patrol_status})
    planner.placed_objects = placed
    planner.trigger_volumes = await _trigger_volumes(wad)
    door_hints = [hint.lower() for (here, _), hint in DOWN_VOLUMES.items() if here == zone]
    doors = [volume for volume in planner.trigger_volumes if not volume.name.startswith("TeleportVol_")
             and any(hint in volume.name.lower() for hint in door_hints)]
    volumes = volumes + [TeleportVolume(volume.name, volume.x, volume.y, volume.z, WALK_IN_RADIUS)
                         for volume in walk_in_teleports(planner.trigger_volumes) + doors]
    planner.zone_data = zone_data
    planner.patrols = patrols
    if free is not None:
        planner.piece_of = free.piece_of
        planner.piece_reaches = free.reaches
        planner.piece_gap = free.gap
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
        walls = await asyncio.to_thread(deimos.walls_at_body_height, world, zone)
        blocked = unary_union([walls, *footprints])
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

    def gap(self, first: int, second: int) -> tuple[tuple[float, float], tuple[float, float], float]:
        """The nearest points of two pieces, on the edge of each, and the distance between them."""
        from shapely.ops import nearest_points
        near_first, near_second = nearest_points(self._pieces[first], self._pieces[second])
        return (near_first.x, near_first.y), (near_second.x, near_second.y), near_first.distance(near_second)

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
        self._heights: dict[tuple[int, int], float | None] = {}

    def to_hex(self, x, y):
        return self._grid.to_hex(x, y)

    def to_world(self, q, r):
        return self._grid.to_world(q, r)

    def neighbours(self, q, r):
        return self._grid.neighbours(q, r)

    def walk_z(self, q, r):
        """The cell's floor height, or None where it cannot be walked. Remembered per cell: the mesh and the free
        area never change within a zone, and these lookups were most of a collision route's planning time."""
        if (q, r) not in self._heights:
            z = self._grid.walk_z(q, r)
            self._heights[(q, r)] = z if z is not None and self._free.contains_point(*self.to_world(q, r)) else None
        return self._heights[(q, r)]

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
        from src.collision_math import _all_collider_solids, _walkable_tris, _walkable_union, get_walk_grid
        self.CollisionWorld, self.get_walk_grid = CollisionWorld, get_walk_grid
        self.walkable_union, self.walkable_tris, self.collider_solids = _walkable_union, _walkable_tris, _all_collider_solids

    def walls_at_body_height(self, world, zone: str):
        """Where the collision file's boxes, cylinders and spheres stand in the wizard's way: each collider's
        footprint, over the walkable floor where either:
        - overhead / floating-base (`bottom > floor_z`): `bottom - floor_z <= BODY_HEIGHT` (135u catches Cyclops
          Lane's tent cylinders at 59u and 109u up while clearing the Commons bridge archways at 160-170u up);
        - embedded (`bottom <= floor_z`): rises at least `Z_BOX_TOL` (20u) for structural boxes or `Z_EMBED_TOL`
          (75u) for cylinders/spheres above the floor, ignoring shallow terrain volumes the navmesh sits inside."""
        from shapely.ops import unary_union
        tree, triangles, heights = self.walkable_tris(world, zone)
        if tree is None:
            return unary_union([])
        blocked = []
        for footprint, bottom, top, is_box in self.collider_solids(world):
            embed_tol = Z_BOX_TOL if is_box else Z_EMBED_TOL
            floor = [triangles[index] for index in tree.query(footprint)
                     if ((bottom > heights[index] and bottom - heights[index] <= BODY_HEIGHT)
                         or (bottom <= heights[index] and top - heights[index] >= embed_tol))
                     and triangles[index].intersects(footprint)]
            if floor:
                region = footprint.intersection(unary_union(floor))
                if not region.is_empty:
                    blocked.append(region)
        return unary_union(blocked)

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

    @staticmethod
    def katsuba_placed_objects(zone: str) -> list[PlacedObject]:
        """Placed objects deserialized directly from `gamedata.bin` via Deimos's `katsuba` + `TemplateManifest.xml`
        resolver, catching templates that do not carry an inline ASCII `<template> instance` string."""
        try:
            from src.entity_collision import _resolver
            if not _resolver._initialize():
                return []
            with _resolver._lock:
                _resolver._load_manifest()
                archive = _resolver._open_wad(zone.replace("/", "-") + ".wad")
                if archive is None or not _resolver._id2name:
                    return []
                zone_data = archive.deserialize("gamedata.bin", _resolver._world_serializer)
                found = []
                for inst in zone_data["m_objectList"]:
                    if inst is None:
                        continue
                    try:
                        tid = inst["m_templateID.m_full"]
                        loc = inst["m_location"]
                        name = _resolver._id2name.get(tid)
                        if name:
                            found.append(PlacedObject(name, float(loc.x), float(loc.y), float(loc.z)))
                    except Exception:
                        continue
                return found
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
    return (patrols, f"{len(patrols.segments)} enemy patrol segments") if patrols else (None, NO_PATROLS)


async def _placed_objects(wad, zone: str | None = None, deimos_root: Path | None = None):
    try:
        data = await wad.get_file("gamedata.bin")
        placed = parse_placed_objects(data)
    except Exception as exc:
        return [], None, f"unavailable: {type(exc).__name__}"
    if zone and deimos_root is not None:
        try:
            deimos = _deimos_collision(deimos_root)
            extra = await asyncio.to_thread(deimos.katsuba_placed_objects, zone)
            seen = {(obj.template, round(obj.x / 5), round(obj.y / 5)) for obj in placed}
            for obj in extra:
                key = (obj.template, round(obj.x / 5), round(obj.y / 5))
                if key not in seen:
                    seen.add(key)
                    placed.append(obj)
        except Exception:
            pass
    return placed, data, f"{len(placed)} placed objects"


async def _teleport_volumes(wad):
    try:
        volumes = parse_teleport_volumes(await wad.get_file("volumes.xml"))
    except Exception as exc:
        return [], f"unavailable: {type(exc).__name__}"
    return volumes, f"{len(volumes)} teleport volumes"


async def _trigger_volumes(wad):
    try:
        return parse_trigger_volumes(await wad.get_file("volumes.xml"))
    except Exception:
        return []


async def _nav_graph(wad):
    try:
        vertices, edges = parse_nav_file(await wad.get_file("zone.nav"))
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"
    return NavGraph.from_edges(vertices, edges), f"{len(vertices)} waypoints"
