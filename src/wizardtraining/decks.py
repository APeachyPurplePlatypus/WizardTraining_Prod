"""Deciding which cards the equipped deck gains and loses when a spell is learned, and writing down why for each
card. No game access, so it is tested offline. The clicks that carry a plan out in the deck page are not here.

The deck holds 14 cards, so a new spell always means taking another card out. Every card that is put in, taken out
or left alone because of a new spell gets one line in runtime/deck-changes.jsonl: the action, the card, the copies,
the reason and the deck size before and after, with the time, level and zone. The reason names the rule that chose
the card, so a change can be checked against the rule and a rule judged by the changes it made.

Rules, in order:
 - A new spell goes in up to DECK_COPIES_WANTED copies, or its copy limit when that is lower.
 - A free slot is used first. When the deck is full, a copy is taken from the first card a removal rule picks.
 - A shield that blocks only some schools is the first to go (Volcanic Shield: it blocks Fire and Storm only,
   verified in the game 2026-10-27). One copy at a time, from the card with the most copies.
 - With no card a rule picks, the deck is left as it is and the log says so: the framework does not guess.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from .training import same_spell

DECK_LOG_NAME = "deck-changes.jsonl"
DECK_CAPACITY = 14
DECK_COPIES_WANTED = 3
ADD, REMOVE, KEEP = "add", "remove", "keep"

# Shields that cover only some schools, by the schools they block. Only shields checked in the game belong here.
PARTIAL_SHIELDS = {"Volcanic Shield": ("Fire", "Storm")}


@dataclass(frozen=True)
class DeckCard:
    name: str
    copies: int
    limit: int = DECK_COPIES_WANTED


@dataclass(frozen=True)
class DeckChange:
    action: str
    name: str
    copies: int
    reason: str


def partial_shield(name: str) -> tuple[str, ...] | None:
    return next((blocked for shield, blocked in PARTIAL_SHIELDS.items() if same_spell(shield, name)), None)


def removal_choice(deck: list[DeckCard]) -> tuple[DeckCard, str] | None:
    """The card to take a copy from and the reason, or None when no rule picks one."""
    shields = [card for card in deck if card.copies > 0 and partial_shield(card.name)]
    if not shields:
        return None
    card = max(shields, key=lambda shield: shield.copies)
    blocked = " and ".join(partial_shield(card.name))
    return card, f"{card.name} blocks only {blocked}, a shield that covers some schools goes before other cards"


def plan_deck_changes(new_spell: DeckCard, deck: list[DeckCard], *, capacity: int = DECK_CAPACITY,
                      copies_wanted: int = DECK_COPIES_WANTED) -> list[DeckChange]:
    """The changes that put `new_spell` into `deck`, one per card copy moved, each with its reason. `new_spell`
    carries the copies already in the deck and the copy limit."""
    working = [DeckCard(card.name, card.copies, card.limit) for card in deck]
    have = next((card.copies for card in working if same_spell(card.name, new_spell.name)), new_spell.copies)
    target = min(copies_wanted, new_spell.limit)
    if have >= target:
        return [DeckChange(KEEP, new_spell.name, have, f"already in the deck x{have}, as many as wanted "
                                                       f"({target}: the lower of {copies_wanted} wanted and a limit "
                                                       f"of {new_spell.limit})")]
    changes: list[DeckChange] = []
    total = sum(card.copies for card in working)
    added = 0
    while have + added < target:
        if total >= capacity:
            choice = removal_choice([card for card in working if not same_spell(card.name, new_spell.name)])
            if choice is None:
                left = target - have - added
                changes.append(DeckChange(KEEP, new_spell.name, left,
                                          f"the deck is full ({total} of {capacity}) and no rule picks a card to "
                                          f"take out, so {left} {'copy' if left == 1 else 'copies'} of "
                                          f"{new_spell.name} stay out"))
                break
            card, reason = choice
            working[working.index(card)] = DeckCard(card.name, card.copies - 1, card.limit)
            changes.append(DeckChange(REMOVE, card.name, 1, reason))
            total -= 1
        added += 1
        total += 1
        changes.append(DeckChange(ADD, new_spell.name, 1, add_reason(new_spell, have, target, total, capacity)))
    return changes


def add_reason(spell: DeckCard, have: int, target: int, total: int, capacity: int) -> str:
    return (f"{spell.name} was just learned and is wanted x{target}; it has {have} copies in the deck "
            f"(deck holds {total} of {capacity} cards with this one)")


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

    def add_plan(self, changes: list[DeckChange], deck: list[DeckCard], *, level, zone) -> list[dict]:
        """Log a plan card by card, tracking the deck's size as each change is made."""
        size = sum(card.copies for card in deck)
        lines = []
        for change in changes:
            after = size + {ADD: change.copies, REMOVE: -change.copies, KEEP: 0}[change.action]
            lines.append(self.add(change, deck_before=size, deck_after=after, level=level, zone=zone))
            size = after
        return lines


def change_text(change: DeckChange) -> str:
    """"deck: take out Volcanic Shield x1: it blocks only Fire and Storm, ..."."""
    verbs = {ADD: "put in", REMOVE: "take out", KEEP: "leave out"}
    return f"{verbs[change.action]} {change.name} x{change.copies}: {change.reason}"
