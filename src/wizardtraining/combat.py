"""Battles: walk into an enemy, then play each planning phase with a `CombatPolicy`.

Cards are described by the game's own spell type ("Damage", "Steal", "AOE", "Heal"), as Deimos reads
them. Clicks go through the mouseless cursor (see `ui`), switched on only for the battle.

Battle readings can be wrong: a failed duel lookup reads as "ended", so the end of a battle is read
twice, BATTLE_END_CONFIRM_SECONDS apart. Anything unexpected stops the battle code and leaves the
battle to the operator rather than guessing.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

from wizwalker.combat import CombatHandler
from wizwalker.memory import DuelPhase

from .geometry import flat_distance
from .movement import KeysIgnored, face_and_step
from .policy import Card, Cast, CombatPolicy, Combatant, RoundView, problem_with
from .reports import plain
from .state import attempt
from .ui import enable_clicks

APPROACH_STEP_SECONDS = 0.4
MAX_APPROACH_STEPS = 15
MAX_ROUNDS = 12
PHASE_TIMEOUT_SECONDS = 90.0
BATTLE_TIMEOUT_SECONDS = 600.0
PHASE_POLL_SECONDS = 0.5
CARDS_DRAW_SECONDS = 0.5
PAUSE_BETWEEN_CAST_CLICKS_SECONDS = 0.5
BATTLE_END_CONFIRM_SECONDS = 1.0
DUEL_CIRCLE_EXIT_SECONDS = 2.0


async def approach(client, enemy: dict) -> dict:
    """Walk toward the enemy in short steps until a battle starts or the steps run out."""
    steps = []
    for _ in range(MAX_APPROACH_STEPS):
        if await client.in_battle():
            return {"ok": True, "steps": steps}
        try:
            target = await enemy["entity"].location()
        except Exception:
            return {"ok": False, "reason": "enemy no longer readable", "steps": steps}
        distance = flat_distance(await client.body.position(), target)
        try:
            turn = await face_and_step(client, target, APPROACH_STEP_SECONDS)
        except KeysIgnored:
            if await client.in_battle():
                return {"ok": True, "steps": steps, "note": "battle started during the approach"}
            raise
        if not turn["ok"]:
            if await client.in_battle():
                return {"ok": True, "steps": steps, "note": "battle started during the approach"}
            return {"ok": False, "reason": f"turn failed: {turn['reason']}", "steps": steps}
        steps.append({"distance_before": round(distance, 1), "turn_taps": len(turn["taps"])})
    if await client.in_battle():
        return {"ok": True, "steps": steps}
    return {"ok": False, "reason": "no battle after the maximum approach steps", "steps": steps}


async def duel_phase(client):
    try:
        return await client.duel.duel_phase()
    except Exception:
        return None


async def wait_for_phase(client, wanted: set, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        phase = await duel_phase(client)
        if phase in wanted:
            return phase
        await asyncio.sleep(PHASE_POLL_SECONDS)
    return None


async def battle_over(client) -> bool:
    if await duel_phase(client) is not DuelPhase.ended:
        return False
    await asyncio.sleep(BATTLE_END_CONFIRM_SECONDS)
    return await duel_phase(client) is DuelPhase.ended


async def wait_for_next_round(client, combat, round_number, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await duel_phase(client) in (DuelPhase.ended, None):
            return "ended"
        try:
            if await combat.round_number() != round_number:
                return "next round"
        except Exception:
            pass
        await asyncio.sleep(PHASE_POLL_SECONDS)
    return "timeout"


async def number(coro) -> int | None:
    value = await attempt(coro)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


async def read_round(combat):
    """The round as a policy sees it, plus the game objects needed to act on its choice."""
    me = await combat.get_client_member()
    enemies = [member for member in await combat.get_all_monster_members() if not await member.is_dead()]
    cards = await combat.get_cards()
    view = RoundView(
        round_number=await number(combat.round_number()),
        health=await number(me.health()),
        max_health=await number(me.max_health()),
        pips=await number(me.normal_pips()),
        power_pips=await number(me.power_pips()),
        cards=tuple([Card(name=await attempt(card.name()), spell_type=await attempt(card.type_name()),
                          castable=await attempt(card.is_castable()) is True) for card in cards]),
        enemies=tuple([Combatant(name=await attempt(enemy.name()), health=await number(enemy.health()))
                       for enemy in enemies]),
    )
    return view, me, cards, enemies


async def play_round(combat, policy: CombatPolicy) -> dict:
    view, me, cards, enemies = await read_round(combat)
    entry = {"round": view.round_number, "view": asdict(view)}
    choice = policy.choose(view)
    problem = None if choice is None else problem_with(choice, view)
    if choice is None or problem:
        await combat.pass_button()
        entry["action"] = "pass" if problem is None else f"pass: {problem}"
        return entry
    await cards[choice.card].cast(cast_target(choice, me, enemies), sleep_time=PAUSE_BETWEEN_CAST_CLICKS_SECONDS)
    entry["action"] = f"cast {view.cards[choice.card].name} on {choice.target}"
    return entry


def cast_target(choice: Cast, me, enemies: list):
    if choice.target == "self":
        return me
    if choice.target == "enemy":
        return enemies[choice.enemy]
    return None


async def fight(client, policy: CombatPolicy, on_round=None) -> dict:
    """Play the current battle to its end, or stop and leave it to the operator. `on_round(entry)` is called
    after each round the wizard plays, with what it saw and did."""
    result = {"rounds": []}
    combat = CombatHandler(client)
    started = time.monotonic()
    await enable_clicks(client)
    async with client.mouse_handler:
        while len(result["rounds"]) < MAX_ROUNDS:
            if time.monotonic() - started > BATTLE_TIMEOUT_SECONDS:
                result["stopped"] = "battle time limit reached; left for the operator"
                break
            phase = await wait_for_phase(client, {DuelPhase.planning, DuelPhase.ended}, PHASE_TIMEOUT_SECONDS)
            if phase is None:
                result["stopped"] = "no planning phase within the timeout; left for the operator"
                break
            if phase is DuelPhase.ended:
                if await battle_over(client):
                    break
                continue
            await asyncio.sleep(CARDS_DRAW_SECONDS)
            try:
                entry = await play_round(combat, policy)
            except Exception as exc:
                result["stopped"] = f"round failed: {type(exc).__name__}; left for the operator"
                break
            result["rounds"].append(entry)
            if on_round is not None:
                on_round(entry)
            entry["then"] = await wait_for_next_round(client, combat, entry["round"], PHASE_TIMEOUT_SECONDS)
        else:
            result["stopped"] = "round limit reached; left for the operator"
    result["final_phase"] = plain(await duel_phase(client))
    await asyncio.sleep(DUEL_CIRCLE_EXIT_SECONDS)
    return result
