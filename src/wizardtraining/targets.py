"""Which enemies matter, worked out from tracker readings. No game access, so it is tested offline.

Each enemy is a dict with "id", "name" and "position", plus "distance" from the wizard and "in_a_duel"
once `measured`. For a bounty goal the quest arrow points at the target enemies, so enemies near the
arrow are the quest's targets and the rest are bystanders to keep away from. An enemy standing in a
duel circle is in someone else's fight and is never a target.
"""

from __future__ import annotations

import math

from .geometry import Point, angle_between, flat_distance, xy

DUEL_CIRCLE_RADIUS = 500.0
QUEST_TARGET_ARROW_RADIUS = 700.0
ENEMY_CLEARANCE = 450.0
WISP_REACH = 4000.0
WISP_ENEMY_CLEARANCE = 600.0


def measured(enemies: list[dict], me, duel_circles) -> list[dict]:
    """The enemies sorted by distance from `me`, each marked with its distance and whether it is in a duel."""
    for enemy in enemies:
        enemy["distance"] = flat_distance(me, enemy["position"])
        enemy["in_a_duel"] = any(flat_distance(enemy["position"], circle) < DUEL_CIRCLE_RADIUS
                                 for circle in duel_circles)
    return sorted(enemies, key=lambda enemy: enemy["distance"])


def quest_targets(enemies: list[dict], arrow) -> list[dict]:
    return [enemy for enemy in enemies
            if not enemy["in_a_duel"] and flat_distance(enemy["position"], arrow) <= QUEST_TARGET_ARROW_RADIUS]


def bystanders(enemies: list[dict], targets: list[dict]) -> list[dict]:
    target_ids = {target["id"] for target in targets}
    return [enemy for enemy in enemies if enemy["id"] not in target_ids]


def others(enemies: list[dict], ignore=()) -> list[dict]:
    """The enemies not named among `ignore`. Targets are ignored by name, since a group shares one."""
    ignored_names = {enemy["name"] for enemy in ignore}
    return [enemy for enemy in enemies if enemy["name"] not in ignored_names]


def too_close(enemies: list[dict]) -> list[dict]:
    return [enemy for enemy in enemies if enemy["distance"] < ENEMY_CLEARANCE]


def summary(enemies: list[dict], limit: int = 6) -> list:
    return [(enemy["name"], round(enemy["distance"]), enemy["in_a_duel"]) for enemy in enemies[:limit]]


def safe_wisps(wisps: list[dict], *, me, enemies: list[dict], duel_circles, tried=()) -> list[dict]:
    """Wisps within WISP_REACH, nearest first, leaving out ones already tried, ones with an enemy within
    WISP_ENEMY_CLEARANCE, and ones inside someone else's duel circle."""
    def safe(wisp):
        return (wisp["id"] not in tried
                and flat_distance(me, wisp["position"]) <= WISP_REACH
                and all(flat_distance(enemy["position"], wisp["position"]) >= WISP_ENEMY_CLEARANCE for enemy in enemies)
                and all(flat_distance(circle, wisp["position"]) >= DUEL_CIRCLE_RADIUS for circle in duel_circles))
    return sorted((wisp for wisp in wisps if safe(wisp)), key=lambda wisp: flat_distance(me, wisp["position"]))


def next_area_to_explore(points: list, *, me, explored=(), prefer=()) -> tuple | None:
    """The nearest exploration point not explored yet, as ((x, y), piece), or None when all are done. Points
    in the `prefer` pieces come first: a quest's targets tend to be near each other, so the pieces holding
    its other goals' objects are the likeliest places for the enemies it asks for."""
    left = [point for point in points if (round(point[0][0]), round(point[0][1])) not in explored]
    preferred = [point for point in left if point[1] in set(prefer)]
    return min(preferred or left, key=lambda point: flat_distance(me, point[0]), default=None)


def threat_centre(close: list[dict]) -> Point:
    """The average position of the close enemies: the point to move away from."""
    points = [xy(enemy["position"]) for enemy in close]
    return sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)


def back_away(bearing_to_threat: float, facing: float) -> bool:
    """True when the threat is within 90 degrees of where the wizard faces, so walking backward (S) moves
    away from it; False when it is behind, so walking forward (W) does. Neither needs a turn."""
    return abs(angle_between(bearing_to_threat, facing)) < math.pi / 2
