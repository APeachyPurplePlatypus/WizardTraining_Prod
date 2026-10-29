"""Turning and walking with the keyboard, as a player does, using a 100 Hz closed-loop reflex controller.

Turning uses a closed-loop Proportional-Derivative (PD) controller over live memory yaw and angular velocity:
after an initial calibration tap teaches which way A turns and how fast, turns hold A or D and release on
predicted yaw lead (`motion.pd_steer_command`) without open-loop settle sleeps.

Walking runs a 100 Hz (`TICK_SECONDS = 0.01`) reflex loop with `keys.KeyChord`:
- Pure-Pursuit ('sliding carrot') lookahead (`geometry.lookahead_point`) smoothly curves around waypoints
  holding W + A/D simultaneously instead of stopping at every bend.
- Real-time local vector-field steering (`motion.reactive_bearing`) deflects around moving enemy tracks
  (passing behind their velocity vectors) on every tick while keeping within walkable collision bounds.
- Velocity-predicted braking (`motion.should_release_forward`) releases W just before entering the target
  circle so the wizard coasts cleanly inside without overshooting.
- Heavy perception (`watch(path_ahead)`) runs concurrently in an async task every `WATCH_SECONDS` so UI
  and entity scans never stall the 100 Hz steering loop.

Never written: position, facing or speed. WizWalker's `goto` is not used, because it writes the facing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from dataclasses import dataclass

from wizwalker import XYZ, Keycode
from wizwalker.utils import calculate_perfect_yaw

from .geometry import angle_between, flat_distance, lookahead_point, point_toward, xy
from .keys import HeldKey, KeyChord, tap
from .motion import (PIVOT_IN_PLACE_RADIANS, STOP_LEAD_SECONDS, WALK_UNITS_PER_SECOND, OscillationGuard,
                     lookahead_distance, pd_steer_command, reactive_bearing, settle_radius, should_release_forward,
                     slow_down_distance, smoothed_speed, step_seconds)
from .reports import plain
from .routes import OBSTACLE_RADIUS, Hazards, RoutePlanner

SETTLE_SECONDS = 0.2
MAX_TURN_TAPS = 25
BATTLE = "battle"
LOADING = "loading"
FIRST_TAP_SECONDS = 0.15
TURN_SETTLE_SECONDS = 0.12
YAW_TOLERANCE_RADIANS = math.radians(4.6)
SMALLEST_NOTICEABLE_TURN_RADIANS = 0.01
TURN_TAP = {"undershoot": 0.8, "shortest": 0.02, "longest": 0.5}
STEER_TAP = {"undershoot": 0.7, "shortest": 0.02, "longest": 0.12}
TICK_SECONDS = 0.01
WATCH_SECONDS = 0.05
TURN_TIMEOUT_SECONDS = 3.5
STEER_TOLERANCE_RADIANS = math.radians(8)
STOP_TO_TURN_RADIANS = PIVOT_IN_PLACE_RADIANS
BLOCKED_CHECK_SECONDS = 1.0
BLOCKED_DISTANCE_PER_CHECK = 150.0
MAX_ROUTE_SECONDS = 180.0
WAYPOINT_RADIUS = 120.0
MAX_SIDESTEPS_PER_LEG = 4
SIDESTEP_TURN_RADIANS = math.pi / 3
SIDESTEP_SECONDS = 0.4
TRAIL_SECONDS = 2.0
MAX_TRAIL_POINTS = 90
OBSTACLE_AHEAD_DISTANCE = 200.0
MAX_SETTLE_STEPS = 8


logger = logging.getLogger(__name__)


class KeysIgnored(RuntimeError):
    """An A tap did not change the facing. Outside battles and dialogs, a popup is usually holding the
    keyboard (the Endorse Wizard window did, after a game restart)."""


@dataclass
class TurnCalibration:
    a_key_turn_sign: int | None = None
    radians_per_second: float | None = None

    @property
    def learned(self) -> bool:
        return self.a_key_turn_sign is not None

    def learn(self, pressed_a: bool, seconds: float, turned: float) -> None:
        if self.a_key_turn_sign is None:
            self.a_key_turn_sign = 1 if (turned > 0) == pressed_a else -1
        if seconds > 0:
            self.radians_per_second = abs(turned) / seconds

    def key_for(self, turn: float):
        return Keycode.A if turn * (self.a_key_turn_sign or 1) > 0 else Keycode.D

    def tap_for(self, turn: float, *, undershoot: float, shortest: float, longest: float):
        key = self.key_for(turn)
        seconds = undershoot * abs(turn) / self.radians_per_second
        return key, max(shortest, min(longest, seconds))


def calibration_for(client) -> TurnCalibration:
    if not hasattr(client, "turn_calibration"):
        client.turn_calibration = TurnCalibration()
    return client.turn_calibration


async def in_battle(client) -> bool:
    try:
        return await client.in_battle() is True
    except Exception:
        return False


async def loading(client) -> bool:
    try:
        return await client.is_loading() is True
    except Exception:
        return False


def as_xyz(point) -> XYZ:
    return point if isinstance(point, XYZ) else XYZ(*xy(point), 0.0)


async def bearing_to(client, target) -> float:
    return calculate_perfect_yaw(await client.body.position(), as_xyz(target))


async def turn_toward(client, target_yaw: float) -> dict:
    """Turn until facing is within YAW_TOLERANCE_RADIANS of `target_yaw`.
    Uses a single initial probe tap if `TurnCalibration` has not yet learned which way A turns; thereafter
    uses a 100 Hz closed-loop PD controller (`KeyChord` + `pd_steer_command`) that stops on live yaw + angular
    velocity lead without open-loop settle pauses. Stops immediately if a battle or loading screen begins."""
    calibration = calibration_for(client)
    taps = []
    if await in_battle(client):
        return {"ok": False, "reason": BATTLE, "taps": taps}
    if await loading(client):
        return {"ok": False, "reason": LOADING, "taps": taps}
    yaw = await client.body.yaw()
    remaining = angle_between(target_yaw, yaw)
    if abs(remaining) <= YAW_TOLERANCE_RADIANS:
        return {"ok": True, "taps": taps, "final_error": round(remaining, 3)}

    if not calibration.learned:
        key, seconds = Keycode.A, FIRST_TAP_SECONDS
        await tap(client, key, seconds)
        await asyncio.sleep(TURN_SETTLE_SECONDS)
        new_yaw = await client.body.yaw()
        turned = angle_between(new_yaw, yaw)
        taps.append({"key": key.name, "seconds": round(seconds, 3), "turned": round(turned, 3)})
        if abs(turned) >= SMALLEST_NOTICEABLE_TURN_RADIANS:
            calibration.learn(True, seconds, turned)
        else:
            if await in_battle(client):
                return {"ok": False, "reason": BATTLE, "taps": taps}
            if await loading(client):
                return {"ok": False, "reason": LOADING, "taps": taps}
            raise KeysIgnored("an A tap did not change the facing")
        yaw = new_yaw
        remaining = angle_between(target_yaw, yaw)
        if abs(remaining) <= YAW_TOLERANCE_RADIANS:
            return {"ok": True, "taps": taps, "final_error": round(remaining, 3)}

    started = prev_time = last_state_check = time.monotonic()
    prev_yaw = yaw
    angular_velocity = 0.0
    hold_key = None
    hold_started_at = started
    hold_start_yaw = yaw

    async with KeyChord(client) as chord:
        while time.monotonic() - started <= TURN_TIMEOUT_SECONDS and len(taps) < MAX_TURN_TAPS:
            now = time.monotonic()
            if now - last_state_check >= WATCH_SECONDS:
                last_state_check = now
                if await in_battle(client):
                    chord.release_all()
                    return {"ok": False, "reason": BATTLE, "taps": taps}
                if await loading(client):
                    chord.release_all()
                    return {"ok": False, "reason": LOADING, "taps": taps}
            yaw = await client.body.yaw()
            dt = now - prev_time
            if dt > 0:
                inst_omega = angle_between(yaw, prev_yaw) / dt
                angular_velocity = 0.5 * angular_velocity + 0.5 * inst_omega
                prev_yaw, prev_time = yaw, now
            remaining = angle_between(target_yaw, yaw)
            turn_sign, _ = pd_steer_command(remaining, angular_velocity, deadband=YAW_TOLERANCE_RADIANS)
            if turn_sign == 0:
                chord.release_all()
                if hold_key is not None:
                    held_dt = max(TICK_SECONDS, now - hold_started_at)
                    turned = angle_between(yaw, hold_start_yaw)
                    taps.append({"key": hold_key.name, "seconds": round(held_dt, 3), "turned": round(turned, 3)})
                    if held_dt >= 0.05 and abs(turned) >= SMALLEST_NOTICEABLE_TURN_RADIANS:
                        calibration.learn(hold_key is Keycode.A, held_dt, turned)
                    hold_key = None
                if abs(remaining) <= YAW_TOLERANCE_RADIANS:
                    return {"ok": True, "taps": taps, "final_error": round(remaining, 3)}
                await asyncio.sleep(TICK_SECONDS)
                yaw = await client.body.yaw()
                remaining = angle_between(target_yaw, yaw)
                if abs(remaining) <= YAW_TOLERANCE_RADIANS:
                    return {"ok": True, "taps": taps, "final_error": round(remaining, 3)}
                angular_velocity = 0.0
                continue
            wanted_key = calibration.key_for(turn_sign)
            if wanted_key is not hold_key:
                if hold_key is not None:
                    held_dt = max(TICK_SECONDS, now - hold_started_at)
                    turned = angle_between(yaw, hold_start_yaw)
                    taps.append({"key": hold_key.name, "seconds": round(held_dt, 3), "turned": round(turned, 3)})
                hold_key = wanted_key
                hold_started_at = now
                hold_start_yaw = yaw
            chord.set_keys(wanted_key)
            await asyncio.sleep(TICK_SECONDS)

    return {"ok": False, "reason": "facing did not converge", "taps": taps}


async def face(client, target) -> dict:
    return await turn_toward(client, await bearing_to(client, target))


async def face_and_step(client, target, seconds: float) -> dict:
    """Turn toward `target`, then walk for `seconds` if the turn worked."""
    turn = await face(client, target)
    if turn["ok"] and seconds > 0:
        await tap(client, Keycode.W, seconds)
        await asyncio.sleep(SETTLE_SECONDS)
    return turn


async def steer(client, off_course: float) -> None:
    key, seconds = calibration_for(client).tap_for(off_course, **STEER_TAP)
    await tap(client, key, seconds)


async def sidestep(client, bearing: float, *, to_the_left: bool) -> None:
    offset = SIDESTEP_TURN_RADIANS if to_the_left else -SIDESTEP_TURN_RADIANS
    turn = await turn_toward(client, (bearing + offset) % (2 * math.pi))
    if turn["ok"]:
        await tap(client, Keycode.W, SIDESTEP_SECONDS)
        await asyncio.sleep(SETTLE_SECONDS)


def walk_speed(client) -> float:
    """The walking speed measured on this client (`motion.smoothed_speed`), else WALK_UNITS_PER_SECOND."""
    return getattr(client, "walk_speed", None) or WALK_UNITS_PER_SECOND


def note_walk_speed(client, moved: float, seconds: float) -> None:
    if seconds > 0:
        client.walk_speed = smoothed_speed(getattr(client, "walk_speed", None), moved / seconds)


async def settle_on(client, target, radius: float, log: dict) -> dict:
    """The last stretch to a final target nearer than held W can stop at (`motion.slow_down_distance`): face it and
    step for the time the distance takes at the measured speed (`motion.step_seconds`), until inside `radius`. If
    the target keeps turning up behind (`motion.OscillationGuard`), the wizard is as near as steps get: arrived
    within `motion.settle_radius`, else failed, in seconds rather than the route's minutes."""
    guard = OscillationGuard()
    speed = walk_speed(client)
    for _ in range(MAX_SETTLE_STEPS):
        me = await client.body.position()
        distance = flat_distance(me, target)
        if distance <= radius:
            return arrived(log)
        guard.note(angle_between(calculate_perfect_yaw(me, target), await client.body.yaw()))
        if guard.oscillating:
            log["oscillations"] = log.get("oscillations", 0) + 1
            return (arrived(dict(log, settled=round(distance))) if distance <= settle_radius(radius, speed)
                    else failed(log, "oscillating around the target"))
        turn = await face_and_step(client, target, step_seconds(distance, radius, speed))
        log["settle_steps"] = log.get("settle_steps", 0) + 1
        if not turn["ok"]:
            return (interrupted(log, turn["reason"]) if turn["reason"] in (BATTLE, LOADING)
                    else failed(log, f"turn failed: {turn['reason']}"))
    distance = flat_distance(await client.body.position(), target)
    return (arrived(dict(log, settled=round(distance))) if distance <= settle_radius(radius, speed)
            else failed(log, "could not settle on the target"))


def arrived(log: dict) -> dict:
    return dict(log, result="arrived")


def interrupted(log: dict, reason: str) -> dict:
    return dict(log, result="interrupted", reason=reason)


def failed(log: dict, reason: str) -> dict:
    return dict(log, result="failed", reason=reason)


@dataclass(frozen=True)
class Reroute:
    """A watcher's answer: walk these legs instead, from where the wizard is, without stopping."""
    legs: list


def must_turn_in_place(off_course: float, turning_learned: bool) -> bool:
    """Stop and turn when the leg bends too sharply to steer into, or, before the first turn has taught how A and
    D turn, when the facing is off at all. A wizard already facing its target walks: a turn of nothing taught
    nothing, and once the loop asked for it again and again while the wizard stood still for a minute."""
    return abs(off_course) > STOP_TO_TURN_RADIANS or (not turning_learned and abs(off_course) > YAW_TOLERANCE_RADIANS)


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def follow_route(client, legs, *, final_radius: float, watch=None,
                       line_walkable=None, live_tracks=None) -> dict:
    """Walk `legs` with a 100 Hz (`TICK_SECONDS`) closed-loop reflex controller (`KeyChord`), Pure-Pursuit
    sliding lookahead (`geometry.lookahead_point`), and real-time local vector-field obstacle deflection
    (`motion.reactive_bearing`). `watch(path_ahead)` runs concurrently every `WATCH_SECONDS` without blocking
    the 100 Hz steering loop."""
    log = {"legs": len(legs), "turns_in_place": 0, "steer_taps": 0, "sidesteps": 0, "reroutes": 0,
           "blocked_at": [], "trail": []}
    if not legs:
        log["seconds"] = 0.0
        return arrived(log)

    started = trail_at = time.monotonic()
    calibration = calibration_for(client)
    remaining = [xy(leg) for leg in legs]
    me = await client.body.position()
    leg_start = xy(me)

    if watch is not None:
        verdict = await watch([xy(me), *remaining])
        if verdict is not None:
            if isinstance(verdict, Reroute):
                remaining = [xy(leg) for leg in verdict.legs]
                log["reroutes"] += 1
            else:
                return interrupted(log, verdict)

    prev_yaw = await client.body.yaw()
    prev_time = time.monotonic()
    angular_velocity = 0.0
    sidesteps = 0
    blocked_check = (prev_time, me)
    pivoting = False
    guard = OscillationGuard()
    watch_task: asyncio.Task | None = None
    next_watch_at = prev_time + WATCH_SECONDS

    try:
        async with KeyChord(client) as chord:
            while remaining:
                now = time.monotonic()
                if now - started > MAX_ROUTE_SECONDS:
                    chord.release_all()
                    return failed(log, "route took too long")

                me = await client.body.position()
                yaw = await client.body.yaw()
                dt = now - prev_time
                if dt > 0:
                    inst_omega = angle_between(yaw, prev_yaw) / dt
                    angular_velocity = 0.5 * angular_velocity + 0.5 * inst_omega
                    prev_yaw, prev_time = yaw, now

                if now >= trail_at and len(log["trail"]) < MAX_TRAIL_POINTS:
                    log["trail"].append((round(me.x), round(me.y)))
                    trail_at = now + TRAIL_SECONDS

                if watch_task is not None and watch_task.done():
                    verdict = await watch_task
                    watch_task = None
                    next_watch_at = now + WATCH_SECONDS
                    if verdict is not None:
                        if isinstance(verdict, Reroute):
                            remaining = [xy(leg) for leg in verdict.legs]
                            leg_start = xy(me)
                            sidesteps = 0
                            blocked_check = (now, me)
                            log["reroutes"] += 1
                            if not remaining:
                                break
                        else:
                            chord.release_all()
                            return interrupted(log, verdict)
                elif watch is not None and watch_task is None and now >= next_watch_at:
                    watch_task = asyncio.create_task(watch([xy(me), *remaining]))

                speed = walk_speed(client)
                lookahead = lookahead_distance(speed)

                while len(remaining) > 1 and flat_distance(me, remaining[0]) <= WAYPOINT_RADIUS:
                    leg_start = remaining.pop(0)
                    sidesteps = 0
                    blocked_check = (now, me)

                carrot, seg_idx = lookahead_point(me, [leg_start, *remaining], lookahead, line_walkable=line_walkable)
                while seg_idx > 0 and len(remaining) > 1:
                    leg_start = remaining.pop(0)
                    seg_idx -= 1
                    sidesteps = 0
                    blocked_check = (now, me)

                target = as_xyz(remaining[0])
                dist_to_target = flat_distance(me, target)

                if len(remaining) == 1:
                    if dist_to_target <= final_radius:
                        chord.release_all()
                        remaining.pop(0)
                        break
                    if should_release_forward(dist_to_target, final_radius, speed):
                        chord.release_all()
                        await asyncio.sleep(STOP_LEAD_SECONDS)
                        me = await client.body.position()
                        if flat_distance(me, target) <= final_radius:
                            remaining.pop(0)
                            break
                    guard.note(angle_between(calculate_perfect_yaw(me, target), yaw))
                    if guard.oscillating or (final_radius < 25.0 and dist_to_target <= slow_down_distance(speed)):
                        chord.release_all()
                        await _cancel_task(watch_task)
                        watch_task = None
                        settled = await settle_on(client, target, final_radius, log)
                        if settled["result"] != "arrived":
                            settled["seconds"] = round(time.monotonic() - started, 1)
                            return settled
                        remaining.pop(0)
                        break

                tracks = live_tracks() if live_tracks is not None else ()
                if len(remaining) == 1 and dist_to_target <= lookahead:
                    desired_yaw = calculate_perfect_yaw(me, target)
                else:
                    desired_yaw = reactive_bearing(me, carrot, tracks, speed=speed, line_walkable=line_walkable)

                off_course = angle_between(desired_yaw, yaw)

                if not calibration.learned and abs(off_course) > YAW_TOLERANCE_RADIANS:
                    chord.release_all()
                    turn = await turn_toward(client, desired_yaw)
                    log["turns_in_place"] += 1
                    if not turn["ok"] and turn["reason"] in (BATTLE, LOADING):
                        return interrupted(log, turn["reason"])
                    if not turn["ok"]:
                        return failed(log, f"turn failed: {turn['reason']}")
                    prev_yaw = await client.body.yaw()
                    prev_time = time.monotonic()
                    angular_velocity = 0.0
                    blocked_check = (prev_time, await client.body.position())
                    continue

                turn_sign, hold_forward = pd_steer_command(off_course, angular_velocity)
                keys = []
                if hold_forward:
                    keys.append(Keycode.W)
                    pivoting = False
                else:
                    if not pivoting:
                        log["turns_in_place"] += 1
                        pivoting = True
                    blocked_check = (now, me)

                if turn_sign != 0 and calibration.learned:
                    keys.append(calibration.key_for(turn_sign))

                pressed = chord.set_keys(*keys)
                if "A" in pressed or "D" in pressed:
                    log["steer_taps"] += 1

                await asyncio.sleep(TICK_SECONDS)

                checked_at, checked_from = blocked_check
                if time.monotonic() - checked_at < BLOCKED_CHECK_SECONDS:
                    continue
                here = await client.body.position()
                moved_since_check = flat_distance(checked_from, here)
                if moved_since_check >= BLOCKED_DISTANCE_PER_CHECK:
                    note_walk_speed(client, moved_since_check, time.monotonic() - checked_at)
                else:
                    chord.release_all()
                    log["blocked_at"].append(point_toward(here, target, OBSTACLE_AHEAD_DISTANCE))
                    if sidesteps >= MAX_SIDESTEPS_PER_LEG:
                        return failed(log, "stuck: sidesteps did not clear the obstacle")
                    sidesteps += 1
                    log["sidesteps"] += 1
                    await sidestep(client, desired_yaw, to_the_left=sidesteps % 2 == 1)
                    prev_yaw = await client.body.yaw()
                    prev_time = time.monotonic()
                    angular_velocity = 0.0
                blocked_check = (time.monotonic(), await client.body.position())
    finally:
        await _cancel_task(watch_task)

    log["seconds"] = round(time.monotonic() - started, 1)
    return arrived(log)


async def travel(client, planner: RoutePlanner, destination, *, arrive_radius: float,
                 watch=None, hazards: Hazards = Hazards(), live_tracks=None, max_methods: int | None = None) -> dict:
    """Try each route method in turn, planning again from wherever the wizard is after a failure and around
    any obstacle found so far, or only the first `max_methods` of them. The result's "blocked_at" lists the obstacles
    found on this trip."""
    attempts, blocked_at = [], []
    tracks_fn = live_tracks or (lambda: hazards.tracks)
    for method in planner.methods()[:max_methods]:
        start = await client.body.position()
        around = hazards.with_obstacles(blocked_at).clear_around(destination, arrive_radius + OBSTACLE_RADIUS)
        legs = planner.route(method, start, destination, around)
        attempt = {"method": method, "from": plain(start), "to": plain(as_xyz(destination)),
                   "avoiding": len(hazards.enemies), "duel_circles": len(hazards.duel_circles),
                   "obstacles": len(hazards.obstacles) + len(blocked_at),
                   "legs": None if legs is None else [(round(x), round(y)) for x, y in legs]}
        attempts.append(attempt)
        if legs is None:
            attempt["result"] = "no route"
            continue
        logger.info("route by %s: %d legs to (%d, %d)", method, len(legs), *map(round, xy(destination)))
        attempt.update(await follow_route(client, legs, final_radius=arrive_radius, watch=watch,
                                          line_walkable=planner.walls_allow, live_tracks=tracks_fn))
        blocked_at += attempt["blocked_at"]
        if attempt["result"] != "failed":
            break
    else:
        return {"result": "failed", "reason": "every route method failed", "attempts": attempts,
                "blocked_at": blocked_at}
    return {"result": attempt["result"], "reason": attempt.get("reason"), "attempts": attempts,
            "blocked_at": blocked_at}
