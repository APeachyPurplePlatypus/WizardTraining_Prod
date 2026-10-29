"""Flat (x, y) geometry. Heights are ignored: routes, distances and threats are judged on the map."""

from __future__ import annotations

import math

Point = tuple[float, float]


def xy(point) -> Point:
    """An (x, y) pair from a WizWalker XYZ or any (x, y, ...) sequence."""
    return (point.x, point.y) if hasattr(point, "x") else (point[0], point[1])


def flat_distance(a, b) -> float:
    return math.dist(xy(a), xy(b))


def angle_between(target: float, current: float) -> float:
    """Signed shortest turn from `current` to `target`, in [-pi, pi)."""
    return (target - current + math.pi) % (2 * math.pi) - math.pi


def bearing(origin, target) -> float:
    """Yaw in [0, 2*pi) from `origin` to `target`, matching WizWalker's `calculate_perfect_yaw` convention
    (0 along -y, pi/2 along -x, pi along +y, 3*pi/2 along +x)."""
    (ox, oy), (tx, ty) = xy(origin), xy(target)
    dx, dy = tx - ox, ty - oy
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return math.atan2(-dx, -dy) % (2 * math.pi)


def project_onto_segment(point, a, b) -> tuple[Point, float, float]:
    """Closest point (`foot`) on segment `a -> b` to `point`, fraction along [0, 1], and flat distance."""
    (px, py), (ax, ay), (bx, by) = xy(point), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    along = 0.0 if length_squared == 0 else ((px - ax) * dx + (py - ay) * dy) / length_squared
    along = max(0.0, min(1.0, along))
    foot = (ax + along * dx, ay + along * dy)
    return foot, along, math.dist((px, py), foot)


def lookahead_point(point, polyline, lookahead: float, line_walkable=None) -> tuple[Point, int]:
    """Pure-Pursuit ('sliding carrot') target along `polyline` (`[leg_start, *remaining_waypoints]`).
    Returns `(carrot, segment_index)` where `segment_index` is the 0-based index of the active segment
    in `polyline` (so `remaining_waypoints[segment_index:]` are the unpassed waypoints).
    If `line_walkable(me, carrot)` is given and refuses a corner-cutting carrot, falls back to the active
    segment's endpoint so the wizard never clips an indoor wall corner."""
    me = xy(point)
    pts = [xy(p) for p in polyline]
    if len(pts) == 1:
        return pts[0], 0
    best_index = 0
    best_foot = pts[0]
    best_dist = math.inf
    for index, (a, b) in enumerate(zip(pts, pts[1:])):
        foot, _, dist = project_onto_segment(me, a, b)
        if dist <= best_dist + 1e-6:
            best_dist = dist
            best_foot = foot
            best_index = index
    tail = [best_foot, *pts[best_index + 1:]]
    carrot = path_beyond(tail, max(0.0, lookahead))[0]
    corner = pts[best_index + 1]
    if line_walkable is not None and carrot != corner and not line_walkable(me, carrot):
        return corner, best_index
    return carrot, best_index


def point_toward(origin, target, distance: float) -> Point:
    """The point `distance` from `origin` in the direction of `target`."""
    (ox, oy), (tx, ty) = xy(origin), xy(target)
    length = math.hypot(tx - ox, ty - oy) or 1.0
    return ox + distance * (tx - ox) / length, oy + distance * (ty - oy) / length


def distance_to_segment(point, a, b) -> float:
    return project_onto_segment(point, a, b)[2]


def distance_to_path(point, path) -> float:
    if len(path) == 1:
        return flat_distance(point, path[0])
    return min(distance_to_segment(point, a, b) for a, b in zip(path, path[1:]))


def path_beyond(path, length: float) -> list[Point]:
    """The rest of a path after its first `length` units, starting at the point that far along; the last point
    alone when the path is shorter."""
    points, remaining = [xy(point) for point in path], length
    for index, (a, b) in enumerate(zip(points, points[1:])):
        step = math.dist(a, b)
        if step > remaining:
            fraction = remaining / step
            return [(a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction), *points[index + 1:]]
        remaining -= step
    return [points[-1]]


def path_within(path, length: float) -> list[Point]:
    """The first `length` units of a path."""
    kept, remaining = [xy(path[0])], length
    for a, b in zip(path, path[1:]):
        a, b = xy(a), xy(b)
        step = math.dist(a, b)
        if step >= remaining:
            fraction = remaining / step if step else 0.0
            kept.append((a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction))
            return kept
        kept.append(b)
        remaining -= step
    return kept
