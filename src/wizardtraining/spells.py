"""Spells the wizard learns, noticed by comparing its learned spells with those seen before, and logged with
whether each is in the equipped deck, so the deck can be changed when a better spell comes. No game access, so it
is tested offline.

The log is one JSON line per spell in runtime/spells-learned.jsonl: the first check lists every spell already
known ("known at the first check"); later checks list each newly learned one ("learned"), with the time, level and
zone, so it is clear when and where it came.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SPELL_LOG_NAME = "spells-learned.jsonl"
KNOWN_AT_FIRST_CHECK = "known at the first check"
LEARNED = "learned"


@dataclass(frozen=True)
class Spell:
    template_id: int
    name: str | None = None
    school: str | None = None
    pips: int | None = None
    effects: tuple[str, ...] = ()

    def text(self) -> str:
        """"Freeze (Ice, 0 pips; stun 1)", or "spell 1887199642" when the game files could not name it."""
        if self.name is None:
            return f"spell {self.template_id}"
        details = ", ".join(part for part in (self.school, None if self.pips is None else f"{self.pips} pips") if part)
        effects = f"; {', '.join(self.effects)}" if self.effects else ""
        return f"{self.name} ({details}{effects})" if details or effects else self.name


def newly_learned(known, learned: list[int]) -> list[int]:
    """The learned spells not among `known`, in the order the game lists them, each once."""
    seen = set(known)
    new = []
    for template_id in learned:
        if template_id not in seen:
            seen.add(template_id)
            new.append(template_id)
    return new


def spell_entry(spell: Spell, *, kind: str, deck: dict[int, int], level, zone) -> dict:
    """One line of the spell log: the spell, and whether and how often it is in the equipped deck."""
    return {"kind": kind, **asdict(spell), "in_deck": deck.get(spell.template_id, 0),
            "deck_cards": sum(deck.values()), "level": level, "zone": zone}


def learned_text(spell: Spell, deck: dict[int, int]) -> str:
    """"learned Freeze (Ice, 0 pips; stun 1); not in the equipped deck (24 cards)"."""
    copies = deck.get(spell.template_id, 0)
    where = f"in the equipped deck x{copies}" if copies else "not in the equipped deck"
    return f"learned {spell.text()}; {where} ({sum(deck.values())} cards)"


class SpellLog:
    def __init__(self, folder: Path):
        self.path = folder / SPELL_LOG_NAME

    def add(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = {"time": datetime.datetime.now().isoformat(timespec="seconds"), **entry}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line) + "\n")
