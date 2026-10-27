"""Turning and walking with the keyboard, as a player does.

Turning taps A or D and reads the facing after each tap. The first taps learn which way A turns and how
fast; later turns and steering reuse that. Walking holds W while a watcher runs every WATCH_SECONDS:
it steers with short A/D taps, turns in place at sharp corners, and releases W the moment the watcher
reports a reason to stop. No progress while W is held means blocked: the point just ahead is recorded as
an obstacle, and the wizard sidesteps by turning off the bearing. Zone walk data can call a way clear that
is not (it happened in the Commons), so later routes plan around recorded obstacles.

Never written: position, facing or speed. WizWalker's `goto` is not used, because it writes the facing.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

from wizwalker import XYZ, Keycode
from wizwalker.utils import calculate_perfect_yaw

from .geometry import angle_between, flat_distance, point_toward, xy
from .keys import HeldKey, tap
from .reports import plain
from .routes import OBSTACLE_RADIUS, Hazards, RoutePlanner

SETTLE_SECONDS = 0.2
MAX_TURN_TAPS = 25
FIRST_TAP_SECONDS = 0.15
TURN_SETTLE_SECONDS = 0.12
YAW_TOLERANCE_RADIANS = math.radians(4.6)
SMALLEST_NOTICEABLE_TURN_RADIANS = 0.01
TURN_TAP = {"undershoot": 0.8, "shortest": 0.02, "longest": 0.5}
STEER_TAP = {"undershoot": 0.7, "shortest": 0.02, "longest": 0.12}
WATCH_SECONDS = 0.05
STEER_TOLERANCE_RADIANS = math.radians(8)
STOP_TO_TURN_RADIANS = math.radians(50)
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
        self.radians_per_second = abs(turned) / seconds

    def tap_for(self, turn: float, *, undershoot: float, shortest: float, longest: float):
        key = Keycode.A if turn * self.a_key_turn_sign > 0 else Keycode.D
        seconds = undershoot * abs(turn) / self.radians_per_second
        return key, max(shortest, min(longest, seconds))


def calibration_for(client) -> TurnCalibration:
    if not hasattr(client, "turn_calibration"):
        client.turn_calibration = TurnCalibration()
    return client.turn_calibration


def as_xyz(point) -> XYZ:
    return point if isinstance(point, XYZ) else XYZ(*xy(point), 0.0)


async def bearing_to(client, target) -> float:
    return calculate_perfect_yaw(await client.body.position(), as_xyz(target))


async def turn_toward(client, target_yaw: float) -> dict:
    """Tap A or D until the facing is within YAW_TOLERANCE_RADIANS of `target_yaw`."""
    calibration = calibration_for(client)
    taps = []
    for _ in range(MAX_TURN_TAPS):
        yaw = await client.body.yaw()
        remaining = angle_between(target_yaw, yaw)
        if abs(remaining) <= YAW_TOLERANCE_RADIANS:
            return {"ok": True, "taps": taps, "final_error": round(remaining, 3)}
        if calibration.learned:
            key, seconds = calibration.tap_for(remaining, **TURN_TAP)
        else:
            key, seconds = Keycode.A, FIRST_TAP_SECONDS
        await tap(client, key, seconds)
        await asyncio.sleep(TURN_SETTLE_SECONDS)
        turned = angle_between(await client.body.yaw(), yaw)
        taps.append({"key": key.name, "seconds": round(seconds, 3), "turned": round(turned, 3)})
        if abs(turned) >= SMALLEST_NOTICEABLE_TURN_RADIANS:
            calibration.learn(key is Keycode.A, seconds, turned)
        elif not calibration.learned:
            raise KeysIgnored("an A tap did not change the facing")
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


def arrived(log: dict) -> dict:
    return dict(log, result="arrived")


def interrupted(log: dict, reason: str) -> dict:
    return dict(log, result="interrupted", reason=reason)


def failed(log: dict, reason: str) -> dict:
    return dict(log, result="failed", reason=reason)


async def follow_route(client, legs, *, final_radius: float, watch=None) -> dict:
    """Walk the legs holding W, steering on the move. `watch(path_ahead)` runs every WATCH_SECONDS with the
    wizard's position followed by the remaining legs, and may return a reason to stop."""
    log = {"legs": len(legs), "turns_in_place": 0, "steer_taps": 0, "sidesteps": 0, "blocked_at": [], "trail": []}
    started = trail_at = time.monotonic()
    calibration = calibration_for(client)
    async with HeldKey(client, Keycode.W) as forward:
        for index, leg in enumerate(legs):
            radius = final_radius if index == len(legs) - 1 else WAYPOINT_RADIUS
            target = as_xyz(leg)
            sidesteps = 0
            blocked_check = (time.monotonic(), await client.body.position())
            while True:
                if time.monotonic() - started > MAX_ROUTE_SECONDS:
                    return failed(log, "route took too long")
                me = await client.body.position()
                if time.monotonic() >= trail_at and len(log["trail"]) < MAX_TRAIL_POINTS:
                    log["trail"].append((round(me.x), round(me.y)))
                    trail_at = time.monotonic() + TRAIL_SECONDS
                path_ahead = [xy(me), *(xy(remaining) for remaining in legs[index:])]
                if watch is not None and (reason := await watch(path_ahead)):
                    await forward.release()
                    return interrupted(log, reason)
                if flat_distance(me, target) <= radius:
                    break
                bearing = calculate_perfect_yaw(me, target)
                off_course = angle_between(bearing, await client.body.yaw())
                if abs(off_course) > STOP_TO_TURN_RADIANS or not calibration.learned:
                    await forward.release()
                    turn = await turn_toward(client, bearing)
                    log["turns_in_place"] += 1
                    if not turn["ok"]:
                        return failed(log, f"turn failed: {turn['reason']}")
                    blocked_check = (time.monotonic(), await client.body.position())
                    continue
                forward.press()
                if abs(off_course) > STEER_TOLERANCE_RADIANS:
                    await steer(client, off_course)
                    log["steer_taps"] += 1
                await asyncio.sleep(WATCH_SECONDS)
                checked_at, checked_from = blocked_check
                if time.monotonic() - checked_at < BLOCKED_CHECK_SECONDS:
                    continue
                here = await client.body.position()
                if flat_distance(checked_from, here) < BLOCKED_DISTANCE_PER_CHECK:
                    await forward.release()
                    log["blocked_at"].append(point_toward(here, target, OBSTACLE_AHEAD_DISTANCE))
                    if sidesteps >= MAX_SIDESTEPS_PER_LEG:
                        return failed(log, "stuck: sidesteps did not clear the obstacle")
                    sidesteps += 1
                    log["sidesteps"] += 1
                    await sidestep(client, bearing, to_the_left=sidesteps % 2 == 1)
                blocked_check = (time.monotonic(), await client.body.position())
    log["seconds"] = round(time.monotonic() - started, 1)
    return arrived(log)


async def travel(client, planner: RoutePlanner, destination, *, arrive_radius: float,
                 watch=None, hazards: Hazards = Hazards()) -> dict:
    """Try each route method in turn, planning again from wherever the wizard is after a failure and around
    any obstacle found so far. The result's "blocked_at" lists the obstacles found on this trip."""
    attempts, blocked_at = [], []
    for method in planner.methods():
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
        attempt.update(await follow_route(client, legs, final_radius=arrive_radius, watch=watch))
        blocked_at += attempt["blocked_at"]
        if attempt["result"] != "failed":
            break
    else:
        return {"result": "failed", "reason": "every route method failed", "attempts": attempts,
                "blocked_at": blocked_at}
    return {"result": attempt["result"], "reason": attempt.get("reason"), "attempts": attempts,
            "blocked_at": blocked_at}
