"""Where enemies are heading, from how they moved in the last moments. No game access, so it is tested offline.

Enemies walk their patrol paths at a steady pace, so the positions of the last second or so give a velocity,
and a straight-line guess holds for a few seconds. Routes use it to pass where an enemy will not be when the
wizard gets there, rather than where it stands now. The walking watcher uses it to stop only for an enemy
whose course will bring it close to the path ahead, and to see one coming before it is close.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .geometry import Point, xy

WALK_UNITS_PER_SECOND = 600.0
MOTION_WINDOW_SECONDS = 1.5
MIN_MOTION_SPAN_SECONDS = 0.3
PREDICTION_HORIZON_SECONDS = 4.0
MAX_ENEMY_SPEED = 1000.0
APPROACH_SAMPLE_SPACING = 60.0


@dataclass(frozen=True)
class Track:
    """An enemy's position now and its velocity in units per second."""
    position: Point
    velocity: Point = (0.0, 0.0)

    def at(self, seconds: float) -> Point:
        """Where the enemy will be after `seconds`. Beyond PREDICTION_HORIZON_SECONDS it is assumed to stay at
        its position then: patrols turn, and a longer straight-line guess would only mislead."""
        t = min(max(seconds, 0.0), PREDICTION_HORIZON_SECONDS)
        return self.position[0] + self.velocity[0] * t, self.position[1] + self.velocity[1] * t


class MotionTracker:
    """Recent positions of each enemy, by its id, and the velocities they give."""

    def __init__(self):
        self._samples: dict[object, deque] = {}

    def observe(self, enemies: list[dict], now: float) -> None:
        for enemy in enemies:
            samples = self._samples.setdefault(enemy["id"], deque())
            samples.append((now, *xy(enemy["position"])))
            while now - samples[0][0] > MOTION_WINDOW_SECONDS:
                samples.popleft()

    def track(self, enemy: dict, now: float) -> Track:
        """The enemy's track. It counts as standing still without recent samples spanning at least
        MIN_MOTION_SPAN_SECONDS, or when it seems to move faster than MAX_ENEMY_SPEED (a reused id)."""
        position = xy(enemy["position"])
        samples = self._samples.get(enemy["id"])
        if not samples or now - samples[-1][0] > MOTION_WINDOW_SECONDS:
            return Track(position)
        (first_time, first_x, first_y), (last_time, last_x, last_y) = samples[0], samples[-1]
        span = last_time - first_time
        if span < MIN_MOTION_SPAN_SECONDS:
            return Track(position)
        velocity = ((last_x - first_x) / span, (last_y - first_y) / span)
        if math.hypot(*velocity) > MAX_ENEMY_SPEED:
            return Track(position)
        return Track(position, velocity)

    def forget(self) -> None:
        self._samples.clear()


def closing_speed(track: Track, point) -> float:
    """How fast the enemy is coming toward `point`, in units per second; negative when it is moving away."""
    dx, dy = point[0] - track.position[0], point[1] - track.position[1]
    distance = math.hypot(dx, dy)
    if distance == 0:
        return 0.0
    return (track.velocity[0] * dx + track.velocity[1] * dy) / distance


def closest_approach(track: Track, path: list, speed: float = WALK_UNITS_PER_SECOND) -> float:
    """How close the enemy will come to the wizard as it walks `path` from its first point, starting now."""
    points = [xy(point) for point in path]
    if len(points) == 1:
        return math.dist(points[0], track.position)
    nearest, walked = math.inf, 0.0
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        steps = max(1, int(length // APPROACH_SAMPLE_SPACING))
        for k in range(steps + 1):
            along = length * k / steps
            point = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
            nearest = min(nearest, math.dist(point, track.at((walked + along) / speed)))
        walked += length
    return nearest
