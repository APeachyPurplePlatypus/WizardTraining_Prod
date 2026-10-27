"""Enemies, friendly NPCs and duel circles among the loaded entities.

The enemy test is Deimos's (src/sprinty_client.py, GPL-3.0): an entity's NPCBehavior holds a flag at
offset 288 that is true for enemies and false for friendly NPCs. Distant entities load as "StandIn"
placeholders without NPC data, so enemies are recognisable only nearby.

Each entity is classified once and remembered by address and name. The game reuses addresses, notably
after a zone change, which also clears what is remembered. Later checks re-read only names and
positions. A duel circle (CombatSigil_Object) is someone's fight in progress; walking into one joins it.
"""

from __future__ import annotations

import time

from wizwalker.constants import Primitive

from .geometry import flat_distance
from .movement import face_and_step
from .targets import escape_point, measured

DUEL_CIRCLE_NAME = "CombatSigil_Object"
NPC_BEHAVIOR_ENEMY_FLAG_OFFSET = 288
ENTITY_LIST_REFRESH_SECONDS = 0.5
STEP_AWAY_SECONDS = 0.6
ENEMY, NPC, DUEL_CIRCLE, OTHER = "enemy", "npc", "duel circle", "other"


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
    if name == DUEL_CIRCLE_NAME:
        return DUEL_CIRCLE
    flag = await npc_enemy_flag(entity)
    return OTHER if flag is None else (ENEMY if flag else NPC)


class EntityTracker:
    """Remembers what each loaded entity is, and re-reads only the positions of the ones that matter."""

    def __init__(self, client):
        self._client = client
        self._kinds: dict[tuple[int, str], str] = {}
        self._zone = None
        self._tracked = []
        self._refreshed_at = 0.0

    async def _refresh(self) -> None:
        if time.monotonic() - self._refreshed_at < ENTITY_LIST_REFRESH_SECONDS:
            return
        self._refreshed_at = time.monotonic()
        zone = await self._client.zone_name()
        if zone != self._zone:
            self._zone, self._kinds = zone, {}
        tracked = []
        for entity in await self._client.get_base_entity_list():
            try:
                name = await entity.object_name() or ""
            except Exception:
                continue
            key = (entity.base_address, name)
            if key not in self._kinds:
                self._kinds[key] = await classify(entity, name)
            if self._kinds[key] != OTHER:
                tracked.append((entity, self._kinds[key], name))
        self._tracked = tracked

    async def _located(self, kinds: set[str]) -> list[tuple[object, str, str, object]]:
        await self._refresh()
        located = []
        for entity, kind, name in self._tracked:
            if kind in kinds:
                try:
                    located.append((entity, kind, name, await entity.location()))
                except Exception:
                    continue
        return located

    async def enemies_and_duel_circles(self) -> tuple[list[dict], list]:
        enemies, circles = [], []
        for entity, kind, name, where in await self._located({ENEMY, DUEL_CIRCLE}):
            if kind == DUEL_CIRCLE:
                circles.append(where)
            else:
                enemies.append({"id": entity.base_address, "entity": entity, "name": name, "position": where})
        return enemies, circles

    async def npc_positions(self) -> list:
        return [where for _, _, _, where in await self._located({NPC})]


def tracker_for(client) -> EntityTracker:
    if not hasattr(client, "entity_tracker"):
        client.entity_tracker = EntityTracker(client)
    return client.entity_tracker


async def surroundings(client) -> tuple[list[dict], list]:
    """Enemies sorted by distance and marked if they stand in a duel circle, and the circles themselves."""
    me = await client.body.position()
    enemies, circles = await tracker_for(client).enemies_and_duel_circles()
    return measured(enemies, me, circles), circles


async def nearby_enemies(client) -> list[dict]:
    enemies, _ = await surroundings(client)
    return enemies


async def nearest_npc(client):
    """Position of the friendly NPC closest to the wizard, or None."""
    me = await client.body.position()
    npcs = await tracker_for(client).npc_positions()
    return min(npcs, key=lambda where: flat_distance(me, where), default=None)


async def step_away(client, close: list[dict]) -> None:
    await face_and_step(client, escape_point(await client.body.position(), close), STEP_AWAY_SECONDS)
