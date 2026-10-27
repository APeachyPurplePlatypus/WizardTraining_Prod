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

from .geometry import Point, distance_to_segment, flat_distance

NODE_RECORD_BYTES = 92
NODE_X_OFFSET, NODE_ID_OFFSET = 36, 68
PATH_ID_STRIDE = 8
PATH_NAME = re.compile(rb"Path[\x20-\x7e]{1,80}")
NOT_ENEMY_PATHS = ("wisp", "flax", "mistwood", "cattail", "chest", "reagent")
NOT_ENEMY_WORDS = {"ore", "wood"}
SIGHTING_RADIUS = 250.0
VIEW_RADIUS = 1200.0
VIEWS_TO_JUDGE = 300
SAMPLE_SPACING = 100.0
BUCKET_SIZE = 250.0
MIN_SHARED_PREFIX = 4
MIN_WORD_LETTERS = 3
SEASONAL_PATHS = ("event",)
WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


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
    """Not a path for wisps, chests or gathering: "Path_Ore_01" in Firecat Alley and "Path_Wood_01" on Unicorn Way
    lead to ore and wood, and counting them as streets left Firecat Alley with almost no sidewalk. The gathering
    names are matched as whole words, so "Path Forest" stays."""
    words = {word.lower() for word in WORD.findall(name)}
    return not any(part in name.lower() for part in NOT_ENEMY_PATHS) and not words & NOT_ENEMY_WORDS


def unwalked_paths(sightings: dict[str, int], views: dict[str, int]) -> set[str]:
    """The patrol paths watched for VIEWS_TO_JUDGE samples (`note_sightings`) on which no enemy was ever seen. A
    zone's path data holds paths no enemy walks: Firecat Alley has 40 that are not wisp, chest or gathering paths,
    many only numbered ("Path 3", "Path 3m"), and by them 80 to 90% of any route there lay within an enemy's reach."""
    return {path for path, viewed in views.items() if viewed >= VIEWS_TO_JUDGE and not sightings.get(path)}


def note_sightings(patrols: "PatrolMap", sightings: dict[str, int], views: dict[str, int], me: Point,
                   enemies: list[Point]) -> None:
    """Count one sample: each path within VIEW_RADIUS of the wizard, `me`, was in view, and each enemy seen counts
    for the path nearest it within SIGHTING_RADIUS."""
    for path in patrols.paths_within(me, VIEW_RADIUS):
        views[path] = views.get(path, 0) + 1
    for enemy in enemies:
        if (path := patrols.nearest_path(enemy, SIGHTING_RADIUS)) is not None:
            sightings[path] = sightings.get(path, 0) + 1


@dataclass
class PatrolMap:
    """Points every SAMPLE_SPACING units along the enemy patrol paths, bucketed for quick nearest-distance checks,
    and the same points with their path's name, for telling which path an enemy is on."""
    segments: list[tuple[Point, Point]] = field(default_factory=list)
    paths: dict[str, list[Point]] = field(default_factory=dict)
    _buckets: dict[tuple[int, int], list[Point]] = field(default_factory=dict)
    _named: dict[tuple[int, int], list[tuple[float, float, str]]] = field(default_factory=dict)
    _around: dict[tuple, list[Point]] = field(default_factory=dict)
    _distances: dict[tuple, float] = field(default_factory=dict)

    @classmethod
    def from_paths(cls, nodes: dict[int, tuple], paths: dict[str, list[int]]) -> "PatrolMap":
        return cls.of({name: [(nodes[i][0], nodes[i][1]) for i in ids if i in nodes]
                       for name, ids in paths.items() if is_enemy_path(name)})

    @classmethod
    def of(cls, paths: dict[str, list[Point]]) -> "PatrolMap":
        patrols = cls()
        for name, points in paths.items():
            if points:
                patrols.paths[name] = points
            for a, b in zip(points, points[1:]):
                patrols.add_segment(a, b, name)
            if len(points) == 1:
                patrols.add_segment(points[0], points[0], name)
        return patrols

    def without(self, names: set[str]) -> "PatrolMap":
        return PatrolMap.of({name: points for name, points in self.paths.items() if name not in names})

    def add_segment(self, a: Point, b: Point, name: str | None = None) -> None:
        self.segments.append((a, b))
        self._around.clear()
        self._distances.clear()
        steps = max(1, int(math.dist(a, b) // SAMPLE_SPACING))
        for k in range(steps + 1):
            point = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
            self._buckets.setdefault(self._bucket(point), []).append(point)
            if name is not None:
                self._named.setdefault(self._bucket(point), []).append((point[0], point[1], name))

    def nearest_path(self, point: Point, within: float) -> str | None:
        """The name of the path nearest `point`, if one comes within `within`."""
        best, nearest = None, within * within
        for x, y, name in self._named_around(point, within):
            squared = (x - point[0]) ** 2 + (y - point[1]) ** 2
            if squared < nearest:
                best, nearest = name, squared
        return best

    def paths_within(self, point: Point, within: float) -> set[str]:
        limit = within * within
        return {name for x, y, name in self._named_around(point, within)
                if (x - point[0]) ** 2 + (y - point[1]) ** 2 < limit}

    def _named_around(self, point: Point, within: float) -> list[tuple[float, float, str]]:
        bx, by = self._bucket(point)
        reach = int(within // BUCKET_SIZE) + 1
        return [sample for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)
                for sample in self._named.get((bx + dx, by + dy), ())]

    @staticmethod
    def _bucket(point: Point) -> tuple[int, int]:
        return int(point[0] // BUCKET_SIZE), int(point[1] // BUCKET_SIZE)

    def distance(self, point: Point, within: float) -> float:
        """Distance from `point` to the nearest patrol path, or `within` when none is closer than that. Route
        searches ask this for every cell they visit, tens of thousands of times, so it compares squared distances
        over the samples of the surrounding buckets, gathered once per bucket, and remembers each answer: the
        cells and waypoints asked about are the same from one route to the next."""
        key = (point[0], point[1], within)
        if key not in self._distances:
            x, y = point
            limit = nearest = within * within
            for sample_x, sample_y in self._samples_around(self._bucket(point), int(within // BUCKET_SIZE) + 1):
                squared = (sample_x - x) ** 2 + (sample_y - y) ** 2
                if squared < nearest:
                    nearest = squared
            self._distances[key] = math.sqrt(nearest) if nearest < limit else within
        return self._distances[key]

    def _samples_around(self, bucket: tuple[int, int], reach: int) -> list[Point]:
        key = (bucket, reach)
        if key not in self._around:
            bx, by = bucket
            self._around[key] = [sample for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)
                                 for sample in self._buckets.get((bx + dx, by + dy), ())]
        return self._around[key]

    def segment_distance(self, point: Point) -> float:
        return min((distance_to_segment(point, a, b) for a, b in self.segments), default=math.inf)

    def paths_named_like(self, *names: str) -> list[str]:
        """Enemy paths whose name shares a word with any of `names`: a goal's enemy ("Scarlet Screamer") or tags
        ("Ddl_WC_TA_ScarletScreamer") against path names ("Path 10_Screamer")."""
        wanted = [word for name in names for word in name_words(name)]
        return [path for path in self.paths if not is_seasonal(path)
                and any(similar(word, other) for word in wanted for other in name_words(path))]

    def nearest_point_on(self, path_names: list[str], me) -> Point | None:
        points = [point for name in path_names for point in self.paths.get(name, ())]
        return min(points, key=lambda point: flat_distance(me, point), default=None)

    def __bool__(self) -> bool:
        return bool(self.segments)


def name_words(name: str) -> set[str]:
    """Words of at least MIN_WORD_LETTERS letters, split at separators and capitals."""
    return {word.lower() for word in WORD.findall(name)
            if len(word) >= MIN_WORD_LETTERS and not word.isdigit() and word.lower() not in IGNORED_WORDS}


def similar(a: str, b: str) -> bool:
    """Two words that start alike: "rotting" and "rotter" share four letters, "eel" and "eels" all three of the
    shorter one's, so a path can be matched to an enemy's name."""
    letters = min(MIN_SHARED_PREFIX, len(a), len(b))
    return a[:letters] == b[:letters]


def is_seasonal(path_name: str) -> bool:
    """Paths of seasonal events ("Path RedPageEvent - Spellwrit Screamer"), whose enemies are there only while the
    event runs. They are still avoided, but never chosen as the place to find a goal's enemies."""
    return any(word in path_name.lower() for word in SEASONAL_PATHS)


IGNORED_WORDS = {"path", "monster", "spawn", "point", "the", "and"}
