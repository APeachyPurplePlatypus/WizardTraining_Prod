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
APPROACH_MEMORY_SECONDS = 6.0


SLOW_DOWN_SECONDS = 0.35
MIN_STEP_SECONDS = 0.05
MAX_STEP_SECONDS = 0.6
SETTLE_SPEED_SECONDS = 0.08
REVERSAL_RADIANS = math.radians(120)
MAX_REVERSALS = 3
SPEED_SMOOTHING = 0.3
SLOWEST_WALK, FASTEST_WALK = 150.0, 2500.0


def slow_down_distance(speed: float) -> float:
    """How near a final target holding W gives way to measured steps (`step_seconds`): SLOW_DOWN_SECONDS of walking.
    Held W is checked every 0.05 s, and at a mount's speed that carries the wizard past a small target circle: with
    the Enchanted Broom on, a wisp walk aiming within 10 went back and forth around the wisp for the route's whole
    180 s (2026-10-28 21:14 to 21:17)."""
    return speed * SLOW_DOWN_SECONDS


def step_seconds(distance: float, radius: float, speed: float) -> float:
    """How long to hold W for a step that ends about halfway into the target circle, within the shortest and
    longest steps."""
    wanted = (distance - radius / 2) / max(speed, SLOWEST_WALK)
    return min(max(wanted, MIN_STEP_SECONDS), MAX_STEP_SECONDS)


def settle_radius(radius: float, speed: float) -> float:
    """How near counts as there once steps start going back and forth: the target circle, or the distance the
    shortest steps can still miss by at this speed, whichever is larger."""
    return max(radius, speed * SETTLE_SPEED_SECONDS)


def smoothed_speed(previous: float | None, measured: float) -> float | None:
    """The walking speed with a new measure folded in (position change per second, W held), kept within
    SLOWEST_WALK and FASTEST_WALK; a measure outside them (a stop, a load) is left out."""
    if not SLOWEST_WALK <= measured <= FASTEST_WALK:
        return previous
    return measured if previous is None else previous + SPEED_SMOOTHING * (measured - previous)


class OscillationGuard:
    """Counts the times the target turns up behind the wizard (off course by REVERSAL_RADIANS or more) on the way
    in, the sign of overshooting it; MAX_REVERSALS of them is oscillating."""

    def __init__(self):
        self.reversals = 0

    def note(self, off_course: float) -> None:
        if abs(off_course) >= REVERSAL_RADIANS:
            self.reversals += 1

    @property
    def oscillating(self) -> bool:
        return self.reversals >= MAX_REVERSALS


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


class ApproachLog:
    """How near each enemy came to the wizard over the last APPROACH_MEMORY_SECONDS. A battle is set off when an
    enemy comes within its reach, and begins seconds later at one of the places battles are held, by which time
    the enemy may be far off and walking away: a Fire Elf stepped away from at 301 units engaged 3 seconds later,
    when the nearest enemy read 954 units away."""

    def __init__(self):
        self._samples: deque = deque()

    def record(self, enemies: list[dict], now: float) -> None:
        for enemy in enemies:
            self._samples.append((now, enemy["id"], enemy["name"], enemy["distance"]))
        while self._samples and now - self._samples[0][0] > APPROACH_MEMORY_SECONDS:
            self._samples.popleft()

    def closest(self, now: float, count: int) -> list[dict]:
        """The `count` enemies that came nearest, each with its nearest distance and how many seconds ago."""
        nearest: dict[object, tuple] = {}
        for when, enemy_id, name, distance in self._samples:
            if now - when <= APPROACH_MEMORY_SECONDS and (enemy_id not in nearest or distance < nearest[enemy_id][2]):
                nearest[enemy_id] = (when, name, distance)
        ranked = sorted(nearest.values(), key=lambda sample: sample[2])[:count]
        return [{"name": name, "distance": round(distance), "seconds_before": round(now - when, 1)}
                for when, name, distance in ranked]

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
