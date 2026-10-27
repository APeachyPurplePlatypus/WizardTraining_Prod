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


def point_toward(origin, target, distance: float) -> Point:
    """The point `distance` from `origin` in the direction of `target`."""
    (ox, oy), (tx, ty) = xy(origin), xy(target)
    length = math.hypot(tx - ox, ty - oy) or 1.0
    return ox + distance * (tx - ox) / length, oy + distance * (ty - oy) / length


def distance_to_segment(point, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = xy(point), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    along = 0.0 if length_squared == 0 else ((px - ax) * dx + (py - ay) * dy) / length_squared
    along = max(0.0, min(1.0, along))
    return math.dist((px, py), (ax + along * dx, ay + along * dy))


def distance_to_path(point, path) -> float:
    if len(path) == 1:
        return flat_distance(point, path[0])
    return min(distance_to_segment(point, a, b) for a, b in zip(path, path[1:]))


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
