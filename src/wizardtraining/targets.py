"""Which enemies matter, worked out from tracker readings. No game access, so it is tested offline.

Each enemy is a dict with "id", "name" and "position", plus "distance" from the wizard and "in_a_duel"
once `measured`. For a bounty goal the quest arrow points at the target enemies, so enemies near the
arrow are the quest's targets and the rest are bystanders to keep away from. An enemy standing in a
duel circle is in someone else's fight and is never a target.
"""

from __future__ import annotations

import math

from .geometry import Point, flat_distance, xy

DUEL_CIRCLE_RADIUS = 500.0
QUEST_TARGET_ARROW_RADIUS = 700.0
ENEMY_CLEARANCE = 450.0
STEP_AWAY_DISTANCE = 400.0
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


def next_area_to_explore(points: list, *, me, explored=()) -> tuple | None:
    """The nearest exploration point not explored yet, as ((x, y), piece), or None when all are done."""
    left = [point for point in points if (round(point[0][0]), round(point[0][1])) not in explored]
    return min(left, key=lambda point: flat_distance(me, point[0]), default=None)


def escape_point(me, close: list[dict], distance: float = STEP_AWAY_DISTANCE) -> Point:
    """The point `distance` from `me`, directly away from the close enemies taken together."""
    mx, my = xy(me)
    away_x = sum(mx - xy(enemy["position"])[0] for enemy in close)
    away_y = sum(my - xy(enemy["position"])[1] for enemy in close)
    length = math.hypot(away_x, away_y) or 1.0
    return mx + distance * away_x / length, my + distance * away_y / length
