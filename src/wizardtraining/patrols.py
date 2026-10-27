"""Where a zone's enemies walk, read from its patrol paths, so routes can keep to the parts of a street they
do not use. No game access, so it is tested offline.

A zone's pathNodeData.bin lists path nodes and its pathData.xml names the paths ("Path 01_Eels", "Path 10_Screamer",
"Path Wisps 01", ...). Both are KingsIsle's binary format; the layout here was inferred, not documented:
- a node is a 92-byte record with x, y and z as floats 36, 40 and 44 bytes in and its id as a 32-bit integer
  68 bytes in;
- a path's name is followed by its node ids, 32-bit integers 8 bytes apart, as one increasing run.
On Triton Avenue the nodes lay within a few hundred units of every place enemies were met: 1 unit from the
Rotting Fodder, 72 from the Haunted Minions, 253 and 310 from the Electric Eels.

Paths for wisps, reagents and chests are not enemies and are left out. Paths with only a number are kept,
because they may be.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field

from .geometry import Point, distance_to_segment

NODE_RECORD_BYTES = 92
NODE_X_OFFSET, NODE_ID_OFFSET = 36, 68
PATH_ID_STRIDE = 8
PATH_NAME = re.compile(rb"Path[\x20-\x7e]{1,80}")
NOT_ENEMY_PATHS = ("wisp", "flax", "mistwood", "cattail", "chest", "reagent")
SAMPLE_SPACING = 100.0
BUCKET_SIZE = 1000.0


def parse_nodes(data: bytes) -> dict[int, tuple[float, float, float]]:
    nodes = {}
    for start in range(0, len(data) - NODE_RECORD_BYTES + 1, NODE_RECORD_BYTES):
        x, y, z = struct.unpack_from("<fff", data, start + NODE_X_OFFSET)
        node_id = struct.unpack_from("<I", data, start + NODE_ID_OFFSET)[0]
        if all(math.isfinite(value) for value in (x, y, z)) and max(abs(x), abs(y)) < 200_000 and 0 < node_id < 1_000_000:
            nodes[node_id] = (x, y, z)
    return nodes


def parse_paths(data: bytes) -> dict[str, list[int]]:
    """Each path name and its node ids, in order."""
    names = list(PATH_NAME.finditer(data))
    paths = {}
    for match, following in zip(names, names[1:] + [None]):
        span_end = following.start() if following is not None else len(data)
        paths[match.group().decode("ascii").rstrip("H`\\")] = _increasing_run(data, match.end(), span_end)
    return paths


def _increasing_run(data: bytes, start: int, end: int) -> list[int]:
    """The longest run of integers going up by one, read PATH_ID_STRIDE bytes apart from any starting byte."""
    best = []
    for phase in range(PATH_ID_STRIDE):
        run = []
        for offset in range(start + phase, end - 3, PATH_ID_STRIDE):
            value = struct.unpack_from("<I", data, offset)[0]
            if run and value == run[-1] + 1:
                run.append(value)
            else:
                run = [value] if 0 < value < 1_000_000 else []
            if len(run) > len(best):
                best = list(run)
    return best if len(best) >= 2 else []


def is_enemy_path(name: str) -> bool:
    return not any(word in name.lower() for word in NOT_ENEMY_PATHS)


@dataclass
class PatrolMap:
    """Points every SAMPLE_SPACING units along the enemy patrol paths, bucketed for quick nearest-distance checks."""
    segments: list[tuple[Point, Point]] = field(default_factory=list)
    _buckets: dict[tuple[int, int], list[Point]] = field(default_factory=dict)

    @classmethod
    def from_paths(cls, nodes: dict[int, tuple], paths: dict[str, list[int]]) -> "PatrolMap":
        patrols = cls()
        for name, ids in paths.items():
            if not is_enemy_path(name):
                continue
            points = [(nodes[i][0], nodes[i][1]) for i in ids if i in nodes]
            for a, b in zip(points, points[1:]):
                patrols.add_segment(a, b)
            if len(points) == 1:
                patrols.add_segment(points[0], points[0])
        return patrols

    def add_segment(self, a: Point, b: Point) -> None:
        self.segments.append((a, b))
        steps = max(1, int(math.dist(a, b) // SAMPLE_SPACING))
        for k in range(steps + 1):
            point = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
            self._buckets.setdefault(self._bucket(point), []).append(point)

    @staticmethod
    def _bucket(point: Point) -> tuple[int, int]:
        return int(point[0] // BUCKET_SIZE), int(point[1] // BUCKET_SIZE)

    def distance(self, point: Point, within: float) -> float:
        """Distance from `point` to the nearest patrol path, or `within` when none is closer than that."""
        reach = int(within // BUCKET_SIZE) + 1
        bx, by = self._bucket(point)
        nearest = within
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for sample in self._buckets.get((bx + dx, by + dy), ()):
                    nearest = min(nearest, math.dist(point, sample))
        return nearest

    def segment_distance(self, point: Point) -> float:
        return min((distance_to_segment(point, a, b) for a, b in self.segments), default=math.inf)

    def __bool__(self) -> bool:
        return bool(self.segments)
