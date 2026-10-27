"""Battles: walk into an enemy, then play each planning phase with a `CombatPolicy`.

Cards are described by the game's own spell type ("Damage", "Steal", "AOE", "Heal"), as Deimos reads
them, and by their magic school. Enemies carry their shields, wards and traps, read from their hanging
effects the way Deimos's combat maths reads them: a "modify incoming damage" effect of one school, or of
every school when its damage type is the universal one. Clicks go through the mouseless cursor (see `ui`), switched on only for the battle.

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
from .policy import UNIVERSAL, Card, Cast, CombatPolicy, Combatant, DamageModifier, Flee, Pass, RoundView, problem_with
from .reports import plain
from .state import attempt
from .ui import enable_clicks

APPROACH_STEP_SECONDS = 0.4
MAX_APPROACH_STEPS = 15
MAX_ROUNDS = 30
PHASE_TIMEOUT_SECONDS = 90.0
BATTLE_TIMEOUT_SECONDS = 900.0
PHASE_POLL_SECONDS = 0.5
CARDS_DRAW_SECONDS = 0.5
EMPTY_HAND_READS = 6
PAUSE_BETWEEN_CAST_CLICKS_SECONDS = 0.5
BATTLE_END_CONFIRM_SECONDS = 1.0
DUEL_CIRCLE_EXIT_SECONDS = 2.0
SCHOOL_NAMES = {2343174: "Fire", 72777: "Ice", 83375795: "Storm", 2448141: "Myth", 2330892: "Life",
                78318724: "Death", 1027491821: "Balance", 2625203: "Star", 78483: "Sun", 2504141: "Moon",
                1429009101: "Shadow", 80289: UNIVERSAL}
INCOMING_DAMAGE = "modify_incoming_damage"
SCHOOLS_IN_STAT_ORDER = ("Fire", "Ice", "Storm", "Myth", "Life", "Death", "Balance", "Star", "Sun", "Moon",
                         "Gardening", "Shadow")


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


async def card_school_and_pips(card) -> tuple[str | None, int | None]:
    try:
        spell = await card.wait_for_graphical_spell()
    except Exception:
        return None, None
    school = SCHOOL_NAMES.get(await number(spell.magic_school_id()))
    try:
        pips = await number((await spell.pip_cost()).spell_rank())
    except Exception:
        pips = None
    return school, pips


async def resistances(member) -> dict[str, float]:
    """A combatant's resistance (positive) or weakness (negative) to each school, as fractions, from its
    stats: the per-school values in SCHOOLS_IN_STAT_ORDER plus the all-schools value, as Deimos adds them.
    Only schools with a value are kept; the all-schools value is kept as UNIVERSAL."""
    try:
        stats = await member.get_stats()
        by_school, every_school = await stats.dmg_reduce_percent(), await stats.dmg_reduce_percent_all()
    except Exception:
        return {}
    found = {school: round(value + every_school, 3) for school, value in zip(SCHOOLS_IN_STAT_ORDER, by_school)
             if round(value + every_school, 3)}
    if round(every_school, 3):
        found[UNIVERSAL] = round(every_school, 3)
    return found


async def incoming_modifiers(member) -> tuple[DamageModifier, ...]:
    """The shields, wards and traps on a combatant. Effects that cannot be read are left out."""
    try:
        effects = await (await member.get_participant()).hanging_effects()
    except Exception:
        return ()
    modifiers = []
    for effect in effects:
        if await attempt(effect.effect_type()) != INCOMING_DAMAGE:
            continue
        school = SCHOOL_NAMES.get(await number(effect.damage_type()))
        percent = await number(effect.effect_param())
        if school is not None and percent:
            modifiers.append(DamageModifier(school, percent))
    return tuple(modifiers)


async def read_round(combat):
    """The round as a policy sees it, plus the game objects needed to act on its choice."""
    me = await combat.get_client_member()
    enemies = [member for member in await combat.get_all_monster_members() if not await member.is_dead()]
    cards = await combat.get_cards()
    schools_and_pips = [await card_school_and_pips(card) for card in cards]
    view = RoundView(
        round_number=await number(combat.round_number()),
        health=await number(me.health()),
        max_health=await number(me.max_health()),
        pips=await number(me.normal_pips()),
        mana=await number(me.mana()),
        power_pips=await number(me.power_pips()),
        cards=tuple([Card(name=await attempt(card.name()), spell_type=await attempt(card.type_name()),
                          castable=await attempt(card.is_castable()) is True, school=school, pips=pips,
                          accuracy=await number(card.accuracy()))
                     for card, (school, pips) in zip(cards, schools_and_pips)]),
        enemies=tuple([Combatant(name=await attempt(enemy.name()), health=await number(enemy.health()),
                                 incoming=await incoming_modifiers(enemy), resistances=await resistances(enemy))
                       for enemy in enemies]),
    )
    return view, me, cards, enemies


async def read_hand(combat):
    """`read_round`, read again every CARDS_DRAW_SECONDS while the hand reads empty and the wizard is alive, up to
    EMPTY_HAND_READS times. A hand read too early once came back empty, and the wizard passed with 107 health
    and three pips until it was defeated."""
    for _ in range(EMPTY_HAND_READS):
        view, me, cards, enemies = await read_round(combat)
        if view.cards or not view.health:
            break
        await asyncio.sleep(CARDS_DRAW_SECONDS)
    return view, me, cards, enemies


async def play_round(combat, policy: CombatPolicy) -> dict:
    view, me, cards, enemies = await read_hand(combat)
    entry = {"round": view.round_number, "view": asdict(view)}
    if not view.cards:
        await combat.pass_button()
        entry["action"] = "pass: the hand read empty"
        return entry
    choice = policy.choose(view)
    if isinstance(choice, Flee):
        await combat.flee_button()
        entry["action"] = f"flee: {choice.reason}"
        return entry
    if choice is None or isinstance(choice, Pass):
        await combat.pass_button()
        entry["action"] = "pass" if choice is None else f"pass: {choice.reason}"
        return entry
    if problem := problem_with(choice, view):
        await combat.pass_button()
        entry["action"] = f"pass: {problem}"
        return entry
    await cards[choice.card].cast(cast_target(choice, me, enemies), sleep_time=PAUSE_BETWEEN_CAST_CLICKS_SECONDS)
    card = view.cards[choice.card]
    entry["action"] = f"cast {card.name}{f' ({card.school})' if card.school else ''} on {choice.target}"
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
