"""Choosing the equipped deck's cards, and writing down why for each card. No game access, so it is tested offline;
the clicks that carry a plan out are in `deckpage.py` (the operator, 2026-10-28, 13:45 UTC: "Yes, bot can edit decks.").

Each spell the Deck page lists is sorted by what the combat policy does with it (`role_of`, from the effects the
game's files give it), and the deck is filled in this order, each spell up to its copy limit, while there is room
(its capacity, learned in the game: an add the Deck page refuses):
 1. An Extract spell, up to its copy limit, while a quest goal needs an essence: it enchants a damage spell, whose
    hit then takes the enemy's essence (Gilda Burke, "Know Thine Enemy"). With one copy in 14 cards it was not in the
    seven-card opening hand of the first Lost Soul fight, and one Frost Beetle ended it (10:21); three copies are in
    nine opening hands of ten.
 2. Heals, the strongest first: the policy heals below 40% health and before a big hit.
 3. Attacks, the most pips first (damage grows with pips), then the biggest hit.
 4. Stuns: the policy stuns while saving a pip for a bigger attack, and the enemy holding the most pips.
 5. Nothing else: shields, which the policy never casts (Volcanic Shield blocks only Fire and Storm), Extract
    spells no goal needs, and spells of other kinds.

Every card put in or taken out gets one line in runtime/deck-changes.jsonl, and every spell left out one line too:
the action, the card, the copies, the reason and the deck size before and after, with the time, level and zone.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path

DECK_LOG_NAME = "deck-changes.jsonl"
ADD, REMOVE, KEEP = "add", "remove", "keep"
EXTRACT, HEAL, ATTACK, STUN, SHIELD, OTHER = "extract", "heal", "attack", "stun", "shield", "other"
EFFECT_ROLES = {"collect_essence": EXTRACT, "heal": HEAL, "damage": ATTACK, "stun": STUN,
                "modify_incoming_damage": SHIELD}
NO_CAPACITY_KNOWN = 10_000

SPELLS_PER_PAGE, SPELL_COLUMNS, SPELL_ROWS = 6, 2, 3
DECK_COLUMNS, DECK_ROWS = 8, 8


@dataclass(frozen=True)
class DeckSpell:
    """A spell of the Deck page's list: its name, its copies in the deck and its copy limit, as the page reads them,
    and its role, pip cost and strength (the biggest number in its effects: Snow Serpent's "damage 155-195" is 195)."""
    name: str
    copies: int
    limit: int
    role: str = OTHER
    pips: int | None = None
    strength: int = 0


@dataclass(frozen=True)
class Wanted:
    name: str
    copies: int
    reason: str


@dataclass(frozen=True)
class DeckChange:
    action: str
    name: str
    copies: int
    reason: str


def role_of(effects) -> str:
    """What the combat policy does with a spell of these effects ("damage 65-105", "heal 400", "stun 1",
    "modify_incoming_damage -70", "collect_essence 100"): the role of its first effect the policy knows."""
    for effect in effects:
        role = EFFECT_ROLES.get(effect.split()[0] if effect.split() else "")
        if role is not None:
            return role
    return OTHER


def strength_of(effects) -> int:
    return max((int(number) for effect in effects for number in re.findall(r"\d+", effect)), default=0)


def deck_spell(name: str, copies: int, limit: int, effects, pips: int | None) -> DeckSpell:
    return DeckSpell(name, copies, limit, role_of(effects), pips, strength_of(effects))


def priority(spell: DeckSpell) -> tuple:
    order = {EXTRACT: 0, HEAL: 1, ATTACK: 2, STUN: 3}
    return order.get(spell.role, len(order)), -(spell.pips or 0) if spell.role == ATTACK else 0, -spell.strength


def why_wanted(spell: DeckSpell) -> str:
    return {
        EXTRACT: f"{spell.name} enchants a damage spell to take an essence, which a quest goal needs",
        HEAL: f"{spell.name} heals {spell.strength}: heals come first, since the policy heals below 40% health and "
              "before a big hit",
        ATTACK: f"{spell.name} hits for up to {spell.strength} with {spell.pips} pips: the strongest hits come first",
        STUN: f"{spell.name} stuns: the policy casts it while saving a pip for a bigger attack, and on the enemy "
              "holding the most pips",
    }[spell.role]


def why_left_out(spell: DeckSpell) -> str:
    return {
        EXTRACT: f"{spell.name} is an Extract spell, and no open quest goal needs an essence",
        SHIELD: f"{spell.name} is a shield, which the combat policy never casts",
    }.get(spell.role, f"{spell.name} is a kind of spell the combat policy does not cast")


def wanted_deck(spells: list[DeckSpell], capacity: int, *, essence_needed: bool) -> list[Wanted]:
    """The copies of each spell the deck should hold, and why, in the order of the rules above."""
    room = capacity
    wanted = []
    for spell in sorted(spells, key=priority):
        if spell.role not in (EXTRACT, HEAL, ATTACK, STUN) or (spell.role == EXTRACT and not essence_needed):
            wanted.append(Wanted(spell.name, 0, why_left_out(spell)))
            continue
        target = spell.limit
        copies = max(0, min(target, room))
        room -= copies
        reason = why_wanted(spell)
        if copies < target:
            reason += (f"; {copies} of {target} copies fit in the {capacity}-card deck after the cards before it"
                       if copies else f"; no room left for it in the {capacity}-card deck")
        wanted.append(Wanted(spell.name, copies, reason))
    return wanted


def plan_changes(spells: list[DeckSpell], wanted: list[Wanted]) -> list[DeckChange]:
    """The cards to take out, one copy at a time, then those to put in, each with its reason; then a KEEP line for
    each spell left out of the deck. Nothing when the deck already holds what is wanted."""
    have = {spell.name: spell.copies for spell in spells}
    removals = [DeckChange(REMOVE, want.name, 1, want.reason) for want in wanted
                for _ in range(have.get(want.name, 0) - want.copies)]
    additions = [DeckChange(ADD, want.name, 1, want.reason) for want in wanted
                 for _ in range(want.copies - have.get(want.name, 0))]
    if not removals and not additions:
        return []
    left_out = [DeckChange(KEEP, want.name, 0, want.reason) for want in wanted
                if want.copies == 0 and have.get(want.name, 0) == 0]
    return removals + additions + left_out


def first_missing(spells: list[DeckSpell], wanted: list[Wanted]) -> str | None:
    """The first spell, in the rules' order, with fewer copies in the deck than wanted: the card to try putting in
    while the deck's capacity is not known yet."""
    have = {spell.name: spell.copies for spell in spells}
    return next((want.name for want in wanted if want.copies > have.get(want.name, 0)), None)


def spell_page_and_cell(index: int) -> tuple[int, int]:
    """Which page of the spell list holds spell `index`, and its cell there (two columns by three rows)."""
    return index // SPELLS_PER_PAGE, index % SPELLS_PER_PAGE


def cell_center(rect: tuple[float, float, float, float], cell: int, columns: int, rows: int) -> tuple[int, int]:
    """The middle of cell `cell` of a grid of `columns` by `rows` over `rect` (x1, y1, x2, y2), row by row."""
    x1, y1, x2, y2 = rect
    width, height = (x2 - x1) / columns, (y2 - y1) / rows
    return int(x1 + width * (cell % columns + 0.5)), int(y1 + height * (cell // columns + 0.5))


class DeckLog:
    def __init__(self, folder: Path):
        self.path = folder / DECK_LOG_NAME

    def add(self, change: DeckChange, *, deck_before: int, deck_after: int, level, zone) -> dict:
        line = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "action": change.action,
                "card": change.name, "copies": change.copies, "reason": change.reason,
                "deck_before": deck_before, "deck_after": deck_after, "level": level, "zone": zone}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line) + "\n")
        return line


def change_text(change: DeckChange) -> str:
    """"take out Freeze x1: Freeze stuns: ...; 1 of 3 copies fit in the 14-card deck after the cards before it"."""
    if change.action == KEEP:
        return f"leave out {change.name}: {change.reason}"
    verbs = {ADD: "put in", REMOVE: "take out"}
    return f"{verbs[change.action]} {change.name} x{change.copies}: {change.reason}"
