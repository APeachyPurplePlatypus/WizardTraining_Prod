"""Where enemies are heading, from how they moved in the last moments, and real-time closed-loop steering math.
No game access, so it is tested offline.

Enemies walk their patrol paths at a steady pace, so recent positions give an instantaneous velocity,
and a straight-line guess holds for a few seconds. Routes use it to pass where an enemy will not be when the
wizard gets there, rather than where it stands now. The walking reflex loop uses it on every tick to steer
around moving enemies in real time (passing behind their velocity vector) and to damp turn rate with a
closed-loop PD controller.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .geometry import Point, angle_between, bearing, xy

WALK_UNITS_PER_SECOND = 600.0
MOTION_WINDOW_SECONDS = 1.5
MIN_MOTION_SPAN_SECONDS = 0.3
INSTANT_STEP_MIN_SECONDS = 0.02
INSTANT_REVERSAL_COSINE = 0.5
PREDICTION_HORIZON_SECONDS = 4.0
MAX_ENEMY_SPEED = 1000.0
MIN_MOVING_ENEMY_SPEED = 30.0
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

STEER_DEADBAND_RADIANS = math.radians(1.8)
TURN_LEAD_SECONDS = 0.035
PIVOT_IN_PLACE_RADIANS = math.radians(85)
STOP_LEAD_SECONDS = 0.035
PURE_PURSUIT_LOOKAHEAD_SECONDS = 0.45
MIN_LOOKAHEAD_DISTANCE = 180.0
MAX_LOOKAHEAD_DISTANCE = 480.0
REACTIVE_AVOID_RADIUS = 950.0
REACTIVE_REPULSION_WEIGHT = 2.4
REACTIVE_TANGENT_WEIGHT = 1.8
REACTIVE_WALL_PROBE_DISTANCE = 200.0


def lookahead_distance(speed: float) -> float:
    """Pure-Pursuit lookahead distance scaled to the wizard's current walking/mount speed."""
    return min(MAX_LOOKAHEAD_DISTANCE, max(MIN_LOOKAHEAD_DISTANCE, speed * PURE_PURSUIT_LOOKAHEAD_SECONDS))


def should_release_forward(distance: float, radius: float, speed: float,
                           stop_lead_seconds: float = STOP_LEAD_SECONDS) -> bool:
    """Whether the wizard is close enough to `radius` that releasing W now will coast into the target circle."""
    return distance <= radius + max(0.0, speed) * stop_lead_seconds


def pd_steer_command(off_course: float, angular_velocity: float = 0.0, *,
                     deadband: float = STEER_DEADBAND_RADIANS,
                     lead_seconds: float = TURN_LEAD_SECONDS,
                     pivot_radians: float = PIVOT_IN_PLACE_RADIANS) -> tuple[int, bool]:
    """Closed-loop Proportional-Derivative (PD) steering controller.
    Given `off_course` (signed angle in [-pi, pi) from current yaw to target yaw) and `angular_velocity`
    (d(yaw)/dt in rad/s), predicts the remaining error after `lead_seconds` of key-up latency.
    Returns `(turn_sign, hold_forward)` where:
    - `turn_sign` is `1` (turn in +yaw direction), `-1` (turn in -yaw direction), or `0` (coast/straight).
    - `hold_forward` is `True` when `abs(off_course) <= pivot_radians`, allowing simultaneous W + A/D curving."""
    hold_forward = abs(off_course) <= pivot_radians
    predicted = off_course - angular_velocity * lead_seconds
    if abs(off_course) <= deadband or abs(predicted) <= deadband:
        return 0, hold_forward
    if off_course * predicted < 0 and abs(off_course) < pivot_radians:
        return 0, hold_forward
    return (1 if predicted > 0 else -1), hold_forward


def reactive_bearing(me, carrot, tracks=(), *, speed: float = WALK_UNITS_PER_SECOND,
                     avoid_radius: float = REACTIVE_AVOID_RADIUS,
                     line_walkable=None) -> float:
    """Real-time local potential-field + velocity-obstacle steering bearing toward `carrot` while deflecting
    around nearby enemy `tracks` (biasing behind moving enemies' velocity vectors).
    Falls back to the direct carrot bearing if a deflected probe step would cross an unwalkable wall."""
    mx, my = xy(me)
    cx, cy = xy(carrot)
    gx, gy = cx - mx, cy - my
    goal_dist = math.hypot(gx, gy)
    if goal_dist < 1e-3:
        return bearing((mx, my), (cx, cy))
    ux, uy = gx / goal_dist, gy / goal_dist
    fx, fy = ux, uy
    deflected = False
    for track in tracks:
        px, py = track.position
        dist_now = math.hypot(mx - px, my - py)
        if dist_now > avoid_radius * 1.25:
            continue
        look_t = min(1.0, dist_now / max(speed, SLOWEST_WALK))
        pred_x, pred_y = track.at(look_t)
        dist_pred = math.hypot(mx - pred_x, my - pred_y)
        if dist_pred < dist_now:
            tx, ty, eff_dist = pred_x, pred_y, dist_pred
        else:
            tx, ty, eff_dist = px, py, dist_now
        if eff_dist >= avoid_radius or eff_dist < 1e-3:
            continue
        deflected = True
        rx, ry = (mx - tx) / eff_dist, (my - ty) / eff_dist
        closeness = max(0.0, 1.0 - eff_dist / avoid_radius)
        repulse = REACTIVE_REPULSION_WEIGHT * (closeness * closeness)
        fx += rx * repulse
        fy += ry * repulse
        vx, vy = track.velocity
        v_speed = math.hypot(vx, vy)
        # Two unit tangents perpendicular to the radial vector:
        t1x, t1y = -ry, rx
        t2x, t2y = ry, -rx
        if v_speed >= MIN_MOVING_ENEMY_SPEED:
            # Prefer the tangent that points behind the enemy's velocity vector (-vx, -vy)
            behind_x, behind_y = -vx / v_speed, -vy / v_speed
            dot1 = t1x * behind_x + t1y * behind_y
            dot2 = t2x * behind_x + t2y * behind_y
            tan_x, tan_y = (t1x, t1y) if dot1 >= dot2 else (t2x, t2y)
        else:
            # Stationary enemy: prefer the tangent aligned with our goal direction
            dot1 = t1x * ux + t1y * uy
            dot2 = t2x * ux + t2y * uy
            tan_x, tan_y = (t1x, t1y) if dot1 >= dot2 else (t2x, t2y)
        tangent_scale = REACTIVE_TANGENT_WEIGHT * closeness
        fx += tan_x * tangent_scale
        fy += tan_y * tangent_scale

    if not deflected or math.hypot(fx, fy) < 1e-3:
        return bearing((mx, my), (cx, cy))
    f_len = math.hypot(fx, fy)
    fx, fy = fx / f_len, fy / f_len
    if line_walkable is not None:
        probe_dist = min(goal_dist, REACTIVE_WALL_PROBE_DISTANCE)
        probe = (mx + fx * probe_dist, my + fy * probe_dist)
        if not line_walkable((mx, my), probe):
            return bearing((mx, my), (cx, cy))
    return bearing((0.0, 0.0), (fx, fy))


def slow_down_distance(speed: float) -> float:
    """How near a final target holding W gives way to measured steps (`step_seconds`): SLOW_DOWN_SECONDS of walking.
    Held W is checked every tick, and at a mount's speed that carries the wizard past a small target circle: with
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
    """Recent positions of each enemy, by its id, and the velocities they give.
    Uses the shortest recent window spanning at least MIN_MOTION_SPAN_SECONDS (instead of the oldest sample
    in MOTION_WINDOW_SECONDS) and detects instantaneous step reversals so patrol turns are seen immediately."""

    def __init__(self):
        self._samples: dict[object, deque] = {}

    def observe(self, enemies: list[dict], now: float) -> None:
        for enemy in enemies:
            samples = self._samples.setdefault(enemy["id"], deque())
            if samples and now <= samples[-1][0]:
                continue
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
        last_time, last_x, last_y = samples[-1]
        if last_time - samples[0][0] < MIN_MOTION_SPAN_SECONDS:
            return Track(position)
        # Pick the newest sample that spans at least MIN_MOTION_SPAN_SECONDS so turns aren't smeared over 1.5s
        anchor_time, anchor_x, anchor_y = samples[0]
        for sample_time, sx, sy in reversed(samples):
            if last_time - sample_time >= MIN_MOTION_SPAN_SECONDS:
                anchor_time, anchor_x, anchor_y = sample_time, sx, sy
                break
        span = last_time - anchor_time
        velocity = ((last_x - anchor_x) / span, (last_y - anchor_y) / span)
        # If the very last step reversed or turned sharply, use the instantaneous step velocity immediately
        if len(samples) >= 3:
            prev_time, prev_x, prev_y = samples[-2]
            dt = last_time - prev_time
            if dt >= INSTANT_STEP_MIN_SECONDS:
                inst_vx, inst_vy = (last_x - prev_x) / dt, (last_y - prev_y) / dt
                inst_speed = math.hypot(inst_vx, inst_vy)
                chord_speed = math.hypot(*velocity)
                if MIN_MOVING_ENEMY_SPEED <= inst_speed <= MAX_ENEMY_SPEED and chord_speed > 0:
                    cosine = (inst_vx * velocity[0] + inst_vy * velocity[1]) / (inst_speed * chord_speed)
                    if cosine < INSTANT_REVERSAL_COSINE:
                        velocity = (inst_vx, inst_vy)
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
