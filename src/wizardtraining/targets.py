"""Which enemies matter, worked out from tracker readings. No game access, so it is tested offline.

Each enemy is a dict with "id", "name" and "position", plus "distance" from the wizard and "in_a_duel"
once `measured`. For a bounty goal the quest arrow points at the target enemies, so enemies near the
arrow are the quest's targets and the rest are bystanders to keep away from. An enemy standing in a
duel circle is in someone else's fight and is never a target.
"""

from __future__ import annotations

import re

import math

from .geometry import Point, angle_between, flat_distance, xy
from .routes import ENEMY_KEEP_OUT

DUEL_CIRCLE_NAMES = frozenset({"Duel Circle", "CombatSigil_Object"})
DUEL_CIRCLE_RADIUS = 700.0
QUEST_TARGET_ARROW_RADIUS = 700.0
ENEMY_CLEARANCE = 450.0
WISP_REACH = 2500.0
WISP_ENEMY_CLEARANCE = 600.0
WISP_DETOUR = 1200.0
AFTER_BATTLE_GRACE_SECONDS = 6.0
DODGES_BEFORE_WAITING = 3
DODGE_MEMORY_SECONDS = 60.0


DUNGEON_ENTRANCE_NAME = "Teleport Semi Circle"


def is_dungeon_entrance(name: str) -> bool:
    """The semicircle in front of a tower or dungeon where its interact prompt shows and X enters, such as
    "Teleport Semi Circle 4 Player Generic" outside Sapphyra's Tower in Olde Town, whose quest arrow points at a
    door volume inside a fenced courtyard."""
    return DUNGEON_ENTRANCE_NAME in name


def leads_to_another_zone(goal: dict, zone: str) -> bool:
    """The goal names a zone other than `zone`, so its waypoint is a door. An "Explore" goal names none: "Take a Walk
    on the Nightside" asked the wizard to walk to a spot in the Nightside, 1,500 units from where it stood, while
    a dungeon entrance stood 1,770 units from that spot; the wizard walked to the entrance again and again."""
    return goal.get("destination_zone") not in ("", None, zone)


def is_duel_circle(name: str) -> bool:
    """A fight in progress shows as a "Duel Circle" entity at its centre, the name Deimos looks for
    (`nearest_duel_circle_distance_and_xyz` in Deimos.py), with its fighters seated about 600 units round it:
    590 to 610 in Deimos, and 599 in the client's log when the wizard joined one. Looking only for
    `CombatSigil_Object`, seen once 3,500 units off in Unicorn Way, found no duel in 35 runs, and the wizard
    walked straight into another player's fight in Firecat Alley. An enemy within DUEL_CIRCLE_RADIUS of one
    is seated in it."""
    return name in DUEL_CIRCLE_NAMES


def measured(enemies: list[dict], me, duel_circles) -> list[dict]:
    """The enemies sorted by distance from `me`, each marked with its distance and whether it is in a duel."""
    for enemy in enemies:
        enemy["distance"] = flat_distance(me, enemy["position"])
        enemy["in_a_duel"] = any(flat_distance(enemy["position"], circle) < DUEL_CIRCLE_RADIUS
                                 for circle in duel_circles)
    return sorted(enemies, key=lambda enemy: enemy["distance"])


def quest_targets(enemies: list[dict], arrow, code: str | None = None) -> list[dict]:
    """The enemies a bounty is after: those near its arrow, and any whose display code is the goal's own `code`,
    wherever they stand, leaving out those in another player's duel. Triton Avenue's Kraken stood 912 from its
    bounty's arrow, so it counted as a bystander to keep away from, and no route to it was left (17:55)."""
    return [enemy for enemy in enemies
            if not enemy["in_a_duel"] and (flat_distance(enemy["position"], arrow) <= QUEST_TARGET_ARROW_RADIUS
                                           or (code and enemy.get("display_code") == code))]


def named_enemies_not_in_a_duel(enemies: list[dict], code: str | None) -> list[dict]:
    """The enemies whose display code is `code`, leaving out those seated in another player's duel: walking to one
    ends at the circle, which routes keep 900 units away from, and a walk near a duel always ends. In Cyclops Lane
    the four Cyclops Legionnaires in sight were all in one, and the run stopped for turns without progress."""
    return [enemy for enemy in enemies if code and enemy.get("display_code") == code and not enemy["in_a_duel"]]


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


def detour(me, via, heading) -> float:
    """How much farther the walk to `heading` gets by passing through `via`."""
    return flat_distance(me, via) + flat_distance(via, heading) - flat_distance(me, heading)


def safe_wisps(wisps: list[dict], *, me, enemies: list[dict], duel_circles, tried=(), heading=None,
               reach: float = WISP_REACH) -> list[dict]:
    """Wisps within `reach`, nearest first, leaving out ones already tried, ones with an enemy within
    WISP_ENEMY_CLEARANCE, and ones inside someone else's duel circle. With a `heading` (where the quest goes
    next), only wisps on the way, at most WISP_DETOUR out of it: turning back for any wisp in reach walked the
    wizard back and forth along Cyclops Lane, into fights with enemies the quest did not ask for."""
    def safe(wisp):
        return (wisp["id"] not in tried and str(wisp["id"]) not in tried
                and flat_distance(me, wisp["position"]) <= reach
                and (heading is None or detour(me, wisp["position"], heading) <= WISP_DETOUR)
                and all(flat_distance(enemy["position"], wisp["position"]) >= WISP_ENEMY_CLEARANCE for enemy in enemies)
                and all(flat_distance(circle, wisp["position"]) >= DUEL_CIRCLE_RADIUS for circle in duel_circles))
    return sorted((wisp for wisp in wisps if safe(wisp)), key=lambda wisp: flat_distance(me, wisp["position"]))


def refill_reach(safe_zone: bool) -> float:
    """How far a refill goes for a wisp, both to fetch one and to end a search on seeing one: any distance in a zone
    without enemies, WISP_REACH among them. A search that ended on any wisp loaded, while the fetch took only those
    within WISP_REACH, stopped every walk in Firecat Alley before it began, until the run stopped."""
    return math.inf if safe_zone else WISP_REACH


def next_area_to_explore(points: list, *, me, explored=(), prefer=()) -> tuple | None:
    """The nearest exploration point not explored yet, as ((x, y), piece), or None when all are done. Points
    in the `prefer` pieces come first: a quest's targets tend to be near each other, so the pieces holding
    its other goals' objects are the likeliest places for the enemies it asks for."""
    left = [point for point in points if (round(point[0][0]), round(point[0][1])) not in explored]
    preferred = [point for point in left if point[1] in set(prefer)]
    return min(preferred or left, key=lambda point: flat_distance(me, point[0]), default=None)


def letters_and_digits(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalnum())


def is_reagent(entity_name: str, reagent: str) -> bool:
    """A loaded entity is the reagent a scavenge goal asks for: its object name ends in the reagent's name without
    spaces, then a number, after any prefix. In the Commons a Frosted Flax showed as "FrostedFlax_01"; a "Mist Wood"
    may show as "MistWood_..." or with a zone's prefix. A name that goes on past the reagent's ("MistWoodBarrel_01")
    is another object."""
    key, name = letters_and_digits(reagent), letters_and_digits(entity_name)
    stem = name.rstrip("0123456789")
    return bool(key) and stem != name and stem.endswith(key)


REAGENT_NAME = re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z]+)+_\d+$")


def looks_like_a_reagent(entity_name: str) -> bool:
    """An entity named as reagents are: words run together, then a number ("FrostedFlax_01", whose prompt reads "to
    Collect"); not the zone-prefixed names of NPCs and props ("WC-ST01-NPC01", "WC_WispHealth")."""
    return REAGENT_NAME.match(entity_name) is not None


ESSENCE_WORD = "essence"


def is_essence(item: str) -> bool:
    """A scavenge item collected by casting an Extract spell on an enemy in battle, not found on the ground: "Know
    Thine Enemy" asked for "Lost Soul Essence" and taught Extract Undead, whose effect is collect_essence."""
    return item.split()[-1].lower() == ESSENCE_WORD if item.split() else False


def essence_enemy(item: str) -> str:
    """The enemy an essence is taken from: "Lost Soul Essence" from a Lost Soul."""
    words = item.split()
    return " ".join(words[:-1]) if is_essence(item) else item


def fought_in(enemy_zones: dict[str, list[str]], names, zone: str) -> None:
    """Note that each enemy named was fought in `zone`."""
    for name in names:
        if name and zone not in enemy_zones.setdefault(name, []):
            enemy_zones[name].append(zone)


REAGENT_DETOUR = 3000.0
REAGENT_SAFE_CLEARANCE = 800.0


def worth_a_detour(reagent_distance: float, enemy_distances: list[float]) -> bool:
    """A wanted reagent in sight while doing something else is worth the walk when it is within REAGENT_DETOUR and no
    enemy stands within REAGENT_SAFE_CLEARANCE of it."""
    return reagent_distance <= REAGENT_DETOUR and all(distance > REAGENT_SAFE_CLEARANCE for distance in enemy_distances)


def zones_to_search_for(reagent_zones: dict[str, list[str]], reagent: str, candidates: list[tuple[int, str]]) -> list[str]:
    """The zones to look in next for a reagent: those it is known or said to grow in first, in that order, then the
    others nearest first (`candidates` as (doors away, zone))."""
    known = reagent_zones.get(reagent, [])
    doors_away = {zone: doors for doors, zone in candidates}
    return sorted(doors_away, key=lambda zone: (zone not in known,
                                                known.index(zone) if zone in known else doors_away[zone]))


def found_in(reagent_zones: dict[str, list[str]], reagent: str, zone: str) -> bool:
    """Put `zone` first among the zones `reagent` grows in; True when that changed the list."""
    known = reagent_zones.setdefault(reagent, [])
    if known[:1] == [zone]:
        return False
    if zone in known:
        known.remove(zone)
    known.insert(0, zone)
    return True


BLOCKED_TALK_DISTANCE = 260.0
STALLED_NUDGE_DISTANCE = 5.0


def close_enough(nudges: list[dict]) -> bool:
    """The prompt is for this one; or the wizard is within `within` with a prompt showing; or it can get no closer
    (the last two nudges within STALLED_NUDGE_DISTANCE of each other) and a prompt shows within
    BLOCKED_TALK_DISTANCE. A Cyclops Lane quest NPC stands 164 units up, with no walkable ground there: every
    nudge stopped 102 units away, with the prompt showing, and the run stopped for turns without progress. In the
    Wizard City Library the quest NPC stands behind a desk: every nudge stopped 205 units away, with the prompt
    showing and that NPC the nearest, and the wizard tried 15 times "to get close enough" (2026-10-28, 00:24)."""
    if not nudges:
        return False
    last = nudges[-1]
    if last["prompt_for_this_one"] or (last["distance"] <= last["within"] and last["in_range"] is True):
        return True
    return (len(nudges) >= 2 and abs(nudges[-2]["distance"] - last["distance"]) <= STALLED_NUDGE_DISTANCE
            and last["distance"] <= BLOCKED_TALK_DISTANCE and last["in_range"] is True)


def area_in_zone(points: list, *, me, explored: list, leaves_the_zone) -> tuple | None:
    """The nearest exploration point not explored yet that is not reached only through a door out of the zone
    (`leaves_the_zone`, given the point); the points that are, are added to `explored`. Woken in the Krokotopia hub
    with 19 health, the search for health wisps walked into the hub's World Spiral entrance and left the hub."""
    while (area := next_area_to_explore(points, me=me, explored=explored)) is not None:
        if not leaves_the_zone(area[0]):
            return area
        explored.append((round(area[0][0]), round(area[0][1])))
    return None


def keeps_blocking(dodge_times: list[float], *, now: float) -> bool:
    """True once the wizard has stepped away DODGES_BEFORE_WAITING times in DODGE_MEMORY_SECONDS: enemies patrol
    the way ahead, and walking on as soon as they are out of reach only leads back into them."""
    return sum(1 for moment in dodge_times if now - moment <= DODGE_MEMORY_SECONDS) >= DODGES_BEFORE_WAITING


def enemies_to_route_around(enemies: list[dict], *, me, destination) -> list[dict]:
    """The enemies routes keep ENEMY_KEEP_OUT from. That is wider than ENEMY_CLEARANCE, at which the wizard steps
    away, so a route never leads into a step-away. Left out: enemies already that close to the wizard, or no
    route could leave them (stepping away handles those), and enemies that close to the destination, or an NPC
    standing near an enemy could never be reached."""
    return [enemy for enemy in enemies if flat_distance(me, enemy["position"]) > ENEMY_KEEP_OUT
            and flat_distance(destination, enemy["position"]) > ENEMY_KEEP_OUT]


def in_grace_after_battle(battle_ended_at: float | None, *, now: float) -> bool:
    """Right after a battle the game does not pull the wizard into another for about ten seconds. The first
    AFTER_BATTLE_GRACE_SECONDS of that are used to walk past enemies without avoiding them; the margin keeps
    the wizard from being next to an enemy when the protection ends."""
    return battle_ended_at is not None and now - battle_ended_at < AFTER_BATTLE_GRACE_SECONDS


def threat_centre(close: list[dict]) -> Point:
    """The average position of the close enemies: the point to move away from."""
    points = [xy(enemy["position"]) for enemy in close]
    return sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)


def back_away(bearing_to_threat: float, facing: float) -> bool:
    """True when the threat is within 90 degrees of where the wizard faces, so walking backward (S) moves
    away from it; False when it is behind, so walking forward (W) does. Neither needs a turn."""
    return abs(angle_between(bearing_to_threat, facing)) < math.pi / 2
