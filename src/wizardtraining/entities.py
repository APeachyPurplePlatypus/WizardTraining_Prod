"""Enemies, friendly NPCs and duel circles among the loaded entities.

The enemy test is Deimos's (src/sprinty_client.py, GPL-3.0): an entity's NPCBehavior holds a flag at
offset 288 that is true for enemies and false for friendly NPCs. Distant entities load as "StandIn"
placeholders without NPC data, so enemies are recognisable only nearby.

Each entity is classified once and remembered by address and name. The game reuses addresses, notably
after a zone change, which also clears what is remembered. Later checks re-read only names and
positions. A duel circle (`targets.is_duel_circle`) is someone's fight in progress; walking into one joins it.
"""

from __future__ import annotations

import time

from wizwalker import Keycode
from wizwalker.constants import Primitive

from .geometry import flat_distance
from .keys import tap
from .movement import bearing_to
from .targets import back_away, is_duel_circle, is_dungeon_entrance, measured, threat_centre

NPC_BEHAVIOR_ENEMY_FLAG_OFFSET = 288
ENTITY_LIST_REFRESH_SECONDS = 0.5
STEP_AWAY_SECONDS = 0.8
ENEMY, NPC, DUEL_CIRCLE, OTHER = "enemy", "npc", "duel circle", "other"
DUNGEON_ENTRANCE = "dungeon entrance"
HEALTH_WISP, MANA_WISP = "health wisp", "mana wisp"
WISP_NAME_PARTS = {"wisphealth": HEALTH_WISP, "wispmana": MANA_WISP}


async def npc_enemy_flag(entity) -> bool | None:
    """True for an enemy, False for a friendly NPC, None for anything without an NPCBehavior."""
    try:
        for behavior in await entity.inactive_behaviors():
            if await behavior.read_type_name() == "NPCBehavior":
                return bool(await behavior.read_value_from_offset(NPC_BEHAVIOR_ENEMY_FLAG_OFFSET, Primitive.bool))
    except Exception:
        return None
    return None


async def classify(entity, name: str) -> str:
    if is_duel_circle(name):
        return DUEL_CIRCLE
    if is_dungeon_entrance(name):
        return DUNGEON_ENTRANCE
    for part, kind in WISP_NAME_PARTS.items():
        if part in name.lower():
            return kind
    flag = await npc_enemy_flag(entity)
    return OTHER if flag is None else (ENEMY if flag else NPC)


async def display_code(entity) -> str | None:
    """The language code of an entity's display name, such as "WizardMobs_00000331" (Scarlet Screamer).
    Quest goals name their enemies with the same codes."""
    try:
        template = await entity.object_template()
        return (await template.display_name() or None) if template is not None else None
    except Exception:
        return None


class EntityTracker:
    """Remembers what each loaded entity is, and re-reads only the positions of the ones that matter."""

    def __init__(self, client):
        self._client = client
        self._kinds: dict[tuple[int, str], str] = {}
        self._display_codes: dict[tuple[int, str], str | None] = {}
        self._zone = None
        self._tracked = []
        self._refreshed_at = 0.0

    async def _refresh(self) -> None:
        if time.monotonic() - self._refreshed_at < ENTITY_LIST_REFRESH_SECONDS:
            return
        self._refreshed_at = time.monotonic()
        zone = await self._client.zone_name()
        if zone != self._zone:
            self._zone, self._kinds, self._display_codes = zone, {}, {}
        tracked = []
        for entity in await self._client.get_base_entity_list():
            try:
                name = await entity.object_name() or ""
            except Exception:
                continue
            key = (entity.base_address, name)
            if key not in self._kinds:
                self._kinds[key] = await classify(entity, name)
                if self._kinds[key] == ENEMY:
                    self._display_codes[key] = await display_code(entity)
            if self._kinds[key] != OTHER:
                tracked.append((entity, self._kinds[key], name))
        self._tracked = tracked

    async def _located(self, kinds: set[str], *, refresh: bool = True) -> list[tuple[object, str, str, object]]:
        if refresh:
            await self._refresh()
        located = []
        for entity, kind, name in self._tracked:
            if kind in kinds:
                try:
                    located.append((entity, kind, name, await entity.location()))
                except Exception:
                    continue
        return located

    async def enemies_and_duel_circles(self, *, refresh: bool = True) -> tuple[list[dict], list]:
        enemies, circles = [], []
        for entity, kind, name, where in await self._located({ENEMY, DUEL_CIRCLE}, refresh=refresh):
            if kind == DUEL_CIRCLE:
                circles.append(where)
            else:
                enemies.append({"id": entity.base_address, "entity": entity, "name": name, "position": where,
                                "display_code": self._display_codes.get((entity.base_address, name))})
        return enemies, circles

    async def dungeon_entrances(self) -> list:
        return [where for _, _, _, where in await self._located({DUNGEON_ENTRANCE})]

    async def npc_positions(self) -> list:
        return [where for _, _, _, where in await self._located({NPC})]

    async def wisps(self, kind: str) -> list[dict]:
        """Health or mana wisps currently loaded: red ones restore health, blue ones mana, when touched."""
        return [{"id": entity.base_address, "name": name, "position": where}
                for entity, _, name, where in await self._located({kind})]


def tracker_for(client) -> EntityTracker:
    if not hasattr(client, "entity_tracker"):
        client.entity_tracker = EntityTracker(client)
    return client.entity_tracker


async def surroundings(client, *, refresh: bool = True) -> tuple[list[dict], list]:
    """Enemies sorted by distance and marked if they stand in a duel circle, and the circles themselves."""
    me = await client.body.position()
    enemies, circles = await tracker_for(client).enemies_and_duel_circles(refresh=refresh)
    return measured(enemies, me, circles), circles


async def nearby_enemies(client) -> list[dict]:
    enemies, _ = await surroundings(client)
    return enemies


async def wisps(client, kind: str) -> list[dict]:
    return await tracker_for(client).wisps(kind)


async def objects_named(client, matches) -> list[dict]:
    """Loaded entities whose object name `matches` accepts, with their id, name and position: reagents, which the
    tracker does not keep."""
    found = []
    for entity in await client.get_base_entity_list():
        try:
            name = await entity.object_name() or ""
            if matches(name):
                found.append({"id": entity.base_address, "name": name, "position": await entity.location()})
        except Exception:
            continue
    return found


async def dungeon_entrance_near(client, point, reach: float):
    """The loaded tower or dungeon entrance nearest `point` within `reach` of it, or None."""
    entrances = [where for where in await tracker_for(client).dungeon_entrances()
                 if flat_distance(where, point) <= reach]
    return min(entrances, key=lambda where: flat_distance(where, point), default=None)


async def nearest_npc(client):
    """Position of the friendly NPC closest to the wizard, or None."""
    me = await client.body.position()
    npcs = await tracker_for(client).npc_positions()
    return min(npcs, key=lambda where: flat_distance(me, where), default=None)


async def step_away(client, close: list[dict]) -> str:
    """Move away from close enemies without turning first: backward with S if they are in front, forward with
    W if they are behind. A 180-degree turn with A and D takes almost 2 s, long enough for a chasing enemy to
    catch the wizard, while S moves as fast as W. Returns the key used."""
    facing = await client.body.yaw()
    key = Keycode.S if back_away(await bearing_to(client, threat_centre(close)), facing) else Keycode.W
    await tap(client, key, STEP_AWAY_SECONDS)
    return key.name
