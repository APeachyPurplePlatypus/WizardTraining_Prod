"""One reading of the wizard's state, and the checks the loop makes on it.

Every read goes through `attempt`, so a failed read shows up as "<unavailable: ...>" instead of ending
the run. The checks treat anything but an explicit reading as unknown: only an explicit "not in battle,
not loading, no dialog" counts as free to move.
"""

from __future__ import annotations

from .reports import plain

BATTLE_PHASES = {"starting", "pre_planning", "planning", "pre_execution", "execution", "resolution", "victory"}


async def attempt(coro):
    try:
        return plain(await coro)
    except Exception as exc:
        return f"<unavailable: {type(exc).__name__}>"


async def snapshot(client) -> dict:
    return {
        "zone": await attempt(client.zone_name()),
        "level": await attempt(client.stats.reference_level()),
        "health": await attempt(client.stats.current_hitpoints()),
        "max_health": await attempt(client.stats.max_hitpoints()),
        "mana": await attempt(client.stats.current_mana()),
        "position": await attempt(client.body.position()),
        "yaw": await attempt(client.body.yaw()),
        "in_battle": await attempt(client.in_battle()),
        "duel_phase": await attempt(client.duel.duel_phase()),
        "loading": await attempt(client.is_loading()),
        "in_dialog": await attempt(client.is_in_dialog()),
    }


def battle_showing(state: dict) -> bool:
    return state["in_battle"] is True or state["duel_phase"] in BATTLE_PHASES


def free_to_move(state: dict) -> bool:
    return state["in_battle"] is False and state["loading"] is False and state["in_dialog"] is False


def health_fraction(state: dict) -> float | None:
    health, max_health = state["health"], state["max_health"]
    if isinstance(health, int) and isinstance(max_health, int) and max_health > 0:
        return health / max_health
    return None
