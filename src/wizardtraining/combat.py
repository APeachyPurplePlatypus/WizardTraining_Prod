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
import datetime
import time
import traceback
from dataclasses import asdict, replace
from pathlib import Path

from wizwalker.combat import CombatHandler
from wizwalker.memory import DuelPhase
from wizwalker.memory.memory_objects.enums import WindowFlags
from wizwalker.utils import get_wiz_install

from .connection import BATTLE_LOG_TAIL_BYTES, client_log_tail, lost_connection, moves_by_round
from .geometry import flat_distance
from .movement import KeysIgnored, face_and_step
from .policy import UNIVERSAL, Card, Cast, CombatPolicy, Combatant, DamageModifier, Flee, Pass, RoundView, problem_with
from .reports import plain
from .state import attempt
from .screen import or_default, visible_names_under, window_saying
from .ui import (BOX_YES, click, click_window, decline_friend_request, enable_clicks, message_box, showing,
                 visible_children, visible_tree, visible_tree_under, window_at)

APPROACH_STEP_SECONDS = 0.4
MAX_APPROACH_STEPS = 15
MAX_ROUNDS = 30
PHASE_TIMEOUT_SECONDS = 90.0
BATTLE_TIMEOUT_SECONDS = 900.0
PHASE_POLL_SECONDS = 0.5
CARDS_DRAW_SECONDS = 0.5
EMPTY_HAND_READS = 6
PAUSE_BETWEEN_CAST_CLICKS_SECONDS = 0.5
CAST_TAKES_WITHIN_SECONDS = 3.0
FLEE_CONFIRM_WAIT_SECONDS = 1.0
PLANNING_PHASE = ["WorldView", "PlanningPhase"]
PLANNING = [*PLANNING_PHASE, "Alignment", "PlanningPhaseSubWindow"]
ACTION_BUTTONS = [*PLANNING, "SpellSelection", "ActionButtons"]
WAITING_FOR_OTHERS = [*PLANNING, "WaitingForOthers"]
CHANGE_CHOICE = [*WAITING_FOR_OTHERS, "Change"]
CHANGE_SETTLE_SECONDS = 0.5
PASS_BUTTON = [*ACTION_BUTTONS, "Focus"]
FLEE_BUTTON = [*ACTION_BUTTONS, "Flee"]
IDLE_BOX_LAYOUT = "messageBoxLayout"
LAYOUT_CENTER_BUTTON = ["AdjustmentWindow", "Layout", "centerButton"]
IDLE_BOX_WORDS = ("return to combat", "you are idle", "combatafk")
IDLE_BOX_SEARCH_DEPTH = 9
LEVELS_ABOVE_THE_CAPTION_SHOWN = 4
FLEE_WORD = "flee"
CONFIRMED = "confirmed"
BATTLE_END_CONFIRM_SECONDS = 1.0
DUEL_CIRCLE_EXIT_SECONDS = 2.0
SCHOOL_NAMES = {2343174: "Fire", 72777: "Ice", 83375795: "Storm", 2448141: "Myth", 2330892: "Life",
                78318724: "Death", 1027491821: "Balance", 2625203: "Star", 78483: "Sun", 2504141: "Moon",
                1429009101: "Shadow", 80289: UNIVERSAL}
INCOMING_DAMAGE = "modify_incoming_damage"
STUN_PROTECTION = {"stun", "stun_block"}
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


async def card_details(card) -> tuple[str | None, int | None, tuple[str, ...]]:
    """A card's school, pip cost and spell effect names ("damage", "stun", ...), each None or empty when it cannot
    be read."""
    try:
        spell = await card.wait_for_graphical_spell()
    except Exception:
        return None, None, ()
    school = SCHOOL_NAMES.get(await number(spell.magic_school_id()))
    try:
        pips = await number((await spell.pip_cost()).spell_rank())
    except Exception:
        pips = None
    try:
        effects = tuple([str(await attempt(effect.effect_type())) for effect in await spell.spell_effects()])
    except Exception:
        effects = ()
    return school, pips, effects


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


async def hanging_effects(member) -> list:
    """The effects hanging on a combatant: shields, wards, traps, stuns and stun blocks. Empty when unreadable."""
    try:
        return await (await member.get_participant()).hanging_effects()
    except Exception:
        return []


async def stunnable(effects) -> bool:
    """No stun and no stun block among a combatant's hanging effects: a stun on it would not be wasted."""
    return not any([await attempt(effect.effect_type()) in STUN_PROTECTION for effect in effects])


async def incoming_modifiers(effects) -> tuple[DamageModifier, ...]:
    """The shields, wards and traps among a combatant's hanging effects. Effects that cannot be read are left out."""
    modifiers = []
    for effect in effects:
        if await attempt(effect.effect_type()) != INCOMING_DAMAGE:
            continue
        school = SCHOOL_NAMES.get(await number(effect.damage_type()))
        percent = await number(effect.effect_param())
        if school is not None and percent:
            modifiers.append(DamageModifier(school, percent))
    return tuple(modifiers)


async def pips_of(member) -> int | None:
    """What a combatant can spend next round: its pips, a power pip counting two. None when unreadable."""
    normal, power = await number(member.normal_pips()), await number(member.power_pips())
    return None if normal is None else normal + 2 * (power or 0)


async def read_round(combat):
    """The round as a policy sees it, plus the game objects needed to act on its choice."""
    me = await combat.get_client_member()
    enemies = [member for member in await combat.get_all_monster_members() if not await member.is_dead()]
    cards = await combat.get_cards()
    details = [await card_details(card) for card in cards]
    effects = [await hanging_effects(enemy) for enemy in enemies]
    view = RoundView(
        round_number=await number(combat.round_number()),
        health=await number(me.health()),
        max_health=await number(me.max_health()),
        pips=await number(me.normal_pips()),
        mana=await number(me.mana()),
        power_pips=await number(me.power_pips()),
        cards=tuple([Card(name=await attempt(card.name()), spell_type=await attempt(card.type_name()),
                          castable=await attempt(card.is_castable()) is True, school=school, pips=pips,
                          accuracy=await number(card.accuracy()), effects=card_effects)
                     for card, (school, pips, card_effects) in zip(cards, details)]),
        enemies=tuple([Combatant(name=await attempt(enemy.name()), health=await number(enemy.health()),
                                 incoming=await incoming_modifiers(hanging), resistances=await resistances(enemy),
                                 stunnable=await stunnable(hanging), pips=await pips_of(enemy))
                       for enemy, hanging in zip(enemies, effects)]),
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


class BoxInTheWay(Exception):
    """A message box the battle code does not answer is open. It takes every click, so no card can be played."""


async def clear_the_way(client) -> list[str]:
    """Decline a friend request and answer the idle box, saying what was done; raise `BoxInTheWay` when another
    message box is still open."""
    answered = [done for done in (await decline_friend_request(client), await return_to_combat(client)) if done]
    if (box := await message_box(client)) is not None:
        raise BoxInTheWay(f"a message box titled {box.title!r} is open and takes every click")
    return answered


async def play_round(combat, policy: CombatPolicy, can_flee: bool = True) -> dict:
    answered = await clear_the_way(combat.client)
    changed = await reopen_card_choice(combat.client)
    view, me, cards, enemies = await read_hand(combat)
    view = replace(view, can_flee=can_flee and await flee_button_enabled(combat.client))
    entry = {"round": view.round_number, "view": asdict(view), "reopened card choice": changed}
    if answered:
        entry["returned to combat"] = "; ".join(answered)
    if not view.cards:
        await pass_round(combat)
        entry["action"] = (f"pass: the hand read empty; on top: {await visible_children(combat.client, [])}, in the "
                           f"world view: {await visible_children(combat.client, ['WorldView'])}")
        return entry
    choice = policy.choose(view)
    acting_since = datetime.datetime.now().replace(microsecond=0)
    if isinstance(choice, Flee):
        entry["action"] = f"flee: {choice.reason} ({await flee(combat)})"
    elif choice is None or isinstance(choice, Pass):
        await pass_round(combat)
        entry["action"] = "pass" if choice is None else f"pass: {choice.reason}"
    elif problem := problem_with(choice, view):
        await pass_round(combat)
        entry["action"] = f"pass: {problem}"
    else:
        await cards[choice.card].cast(cast_target(choice, me, enemies), sleep_time=PAUSE_BETWEEN_CAST_CLICKS_SECONDS)
        card = view.cards[choice.card]
        target = f"{choice.target} {view.enemies[choice.enemy].name}" if choice.target == "enemy" else choice.target
        entry["action"] = f"cast {card.name}{f' ({card.school})' if card.school else ''} on {target}"
        if not await cast_taken(combat.client):
            _, me, cards, enemies = await read_round(combat)
            await cards[choice.card].cast(cast_target(choice, me, enemies), sleep_time=PAUSE_BETWEEN_CAST_CLICKS_SECONDS)
            entry["action"] += " (cast again: the first did not take)"
    entry["acting_since"] = acting_since.isoformat(timespec="seconds")
    return entry


def note_moves_sent(rounds: list[dict]) -> None:
    """Set each round's "sent" to the moves the client logged for it (`connection.moves_by_round`)."""
    acted = [entry for entry in rounds if "acting_since" in entry]
    starts = [datetime.datetime.fromisoformat(entry["acting_since"]) for entry in acted]
    log_tail = client_log_tail(Path(get_wiz_install()), size=BATTLE_LOG_TAIL_BYTES)
    for entry, sent in zip(acted, moves_by_round(starts, log_tail)):
        entry["sent"] = sent


async def cast_taken(client) -> bool:
    """Within CAST_TAKES_WITHIN_SECONDS the duel leaves planning, as it does at once when the wizard is alone in
    battle, or the planning window says it is waiting for others. About one cast in four spent no mana and did
    nothing, most often the first of a battle: the client's log shows no move sent for it."""
    deadline = time.monotonic() + CAST_TAKES_WITHIN_SECONDS
    while time.monotonic() < deadline:
        if await duel_phase(client) is not DuelPhase.planning or await showing(client, WAITING_FOR_OTHERS):
            return True
        await asyncio.sleep(PHASE_POLL_SECONDS)
    return False


async def pass_round(combat) -> None:
    """Click the Pass action button (the window named Focus) by its path. WizWalker's pass_button and flee_button
    click the DoneWindow's "Defeated" buttons, meant for a wizard knocked out in battle, whenever DoneWindow says it
    is visible, and in this client it always does: no pass or flee click took, and the round timer passed instead.
    After such a flee click, the wizard's casts stopped landing for the rest of the battle."""
    await click(combat.client, PASS_BUTTON)


async def reopen_card_choice(client) -> bool:
    """When the planning window still shows "waiting for others" at the start of the wizard's turn to choose, click
    its Change button to get the hand back. A click on Flee that did not end the battle left that panel up, and
    from then on no card click landed, into the next battle too: a Warhorn stayed at 285 for 13 rounds while the
    wizard's casts and heals did nothing. True when it clicked."""
    if not await showing(client, WAITING_FOR_OTHERS):
        return False
    try:
        await click(client, CHANGE_CHOICE)
    except LookupError:
        return False
    await asyncio.sleep(CHANGE_SETTLE_SECONDS)
    return True


async def return_to_combat(client) -> str | None:
    """Answer the game's idle box with its button, and say so; None when it is not showing. Until answered the game
    passes for the wizard every round and keeps the planning window hidden: after joining another player's fight,
    the client's log showed "KeepWindowHidden(True)" every round, no move from the wizard, and its hand read empty
    from round 5. ("MSG_CombatAFK" starts every round of every battle, so it says nothing.) The box is found by its
    text anywhere on screen: "You Are Idle" (GUI_CombatAFKTitle), "Would you like to return to combat?"
    (GUI_CombatAFKMessage), or those keys, as the game's own idleMessage.gui holds them. Looked for by window name,
    under the planning phase, on top and four levels down, it was never found. Its one button, "Return"
    (GUI_ReturnToCombat), is looked for where the flee box has Yes; when it is not there, the window names around the
    text are reported."""
    chain = await window_saying(client.root_window, IDLE_BOX_WORDS, IDLE_BOX_SEARCH_DEPTH)
    if chain is None:
        return None
    names = [await or_default(window.name(), "?") for window in chain]
    where = "/".join(names)
    layout = next((window for window, name in zip(chain, names) if name == IDLE_BOX_LAYOUT), None)
    button = None if layout is None else await or_default(window_at(layout, LAYOUT_CENTER_BUTTON), None)
    if button is None:
        around = chain[max(0, len(chain) - 1 - LEVELS_ABOVE_THE_CAPTION_SHOWN)]
        return (f"found the idle box at {where} but no button at {IDLE_BOX_LAYOUT}/{'/'.join(LAYOUT_CENTER_BUTTON)}; "
                f"around it: {await visible_names_under(around, LEVELS_ABOVE_THE_CAPTION_SHOWN + 2)}")
    await click_window(client, button)
    await asyncio.sleep(CHANGE_SETTLE_SECONDS)
    return f"answered the idle box at {where}"


async def flee_button_enabled(client) -> bool:
    """The Flee action button is there and not disabled (WizWalker's WindowFlags.disabled). Some battles cannot be
    fled; then the wizard plays its cards instead of losing the round."""
    try:
        button = await window_at(client.root_window, FLEE_BUTTON)
        return button is not None and WindowFlags.disabled not in await button.flags()
    except Exception:
        return False


async def flee(combat) -> str:
    """Click the Flee action button, then answer Yes (the box's centerButton) to the game's "Are you sure you want
    to flee? You will lose all your Mana..." box. Says what followed. The box shows under WorldView/PlanningPhase;
    looked for on top only, it was never found and never answered, and while it stayed up it hid the hand: no card
    click sent a move for the rest of the battle. Confirmed, the battle ends and the wizard is sent to the Commons
    with no mana."""
    client = combat.client
    await click(client, FLEE_BUTTON)
    await asyncio.sleep(FLEE_CONFIRM_WAIT_SECONDS)
    box = await message_box(client)
    if box is None:
        return (f"no confirmation box; the planning window shows {await visible_tree(client, PLANNING)}; the planning "
                f"phase shows {await visible_tree(client, PLANNING_PHASE, depth=4)}; on top: "
                f"{await visible_tree(client, [], depth=1)}")
    if FLEE_WORD not in box.caption.lower():
        return f"a message box titled {box.title!r} that does not mention fleeing was left alone"
    button = await or_default(window_at(box.window, BOX_YES), None)
    if button is None:
        return (f"found {box.caption!r} but no button at {'/'.join(BOX_YES)}; "
                f"it shows {await visible_tree_under(box.window, 6)}")
    await click_window(client, button)
    return f"{CONFIRMED} {box.caption!r}"


def fled_in(battle_round: dict) -> bool:
    """The round's flee was confirmed. A flee sends the wizard to the Commons, which otherwise reads as a defeat."""
    return battle_round["action"].startswith("flee") and CONFIRMED in battle_round["action"]


def no_planning_reason() -> str:
    """Why no planning phase came: a lost server connection when the client's log shows one, else a timeout."""
    lost = lost_connection(client_log_tail(Path(get_wiz_install())))
    if lost:
        return (f"the game lost its connection to the server at {lost} (WizardClient.log), so the battle stopped; "
                "a login is needed, left for the operator")
    return "no planning phase within the timeout; left for the operator"


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
    can_flee = True
    started = time.monotonic()
    await enable_clicks(client)
    async with client.mouse_handler:
        while len(result["rounds"]) < MAX_ROUNDS:
            if time.monotonic() - started > BATTLE_TIMEOUT_SECONDS:
                result["stopped"] = "battle time limit reached; left for the operator"
                break
            phase = await wait_for_phase(client, {DuelPhase.planning, DuelPhase.ended}, PHASE_TIMEOUT_SECONDS)
            if phase is None:
                result["stopped"] = no_planning_reason()
                break
            if phase is DuelPhase.ended:
                if await battle_over(client):
                    break
                continue
            await asyncio.sleep(CARDS_DRAW_SECONDS)
            try:
                entry = await play_round(combat, policy, can_flee)
            except Exception as exc:
                result["stopped"] = f"round failed: {type(exc).__name__}: {exc}; left for the operator"
                result["traceback"] = traceback.format_exc()
                break
            result["rounds"].append(entry)
            if on_round is not None:
                on_round(entry)
            entry["then"] = await wait_for_next_round(client, combat, entry["round"], PHASE_TIMEOUT_SECONDS)
            if entry["action"].startswith("flee") and entry["then"] == "next round":
                can_flee = False
        else:
            result["stopped"] = "round limit reached; left for the operator"
    result["final_phase"] = plain(await duel_phase(client))
    await asyncio.sleep(DUEL_CIRCLE_EXIT_SECONDS)
    note_moves_sent(result["rounds"])
    return result
