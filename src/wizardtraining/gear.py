"""Which gear to wear, worked out from item data. No game access, so it is tested offline.

An item's stats are its equip effects: canonical stat effects such as "CanonicalMaxHealth" or
"CanonicalIceReduceDamage", each with a lookup index into the game's stat table for that stat. The tables were not
found in the installed files, so a value is estimated from its index, as measured when equipping: a flat stat
gives index + 1 (indexes 58, 19 and 4 gave +59, +20 and +5 health), a percentage stat index - 99 percent (index 100
gave 1% resistance to every school).

What a stat is worth is set for a solo wizard who never rests: health first, the buffer that saves heal rounds and
defeats; mana next, since every school spell costs it and running out lost a fight; then resistance to every
school; then the wizard's own school's damage and accuracy. Stats of other schools count for nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WEARABLE_SLOTS = ("Hat", "Robe", "Shoes", "Athame", "Amulet", "Ring")
EVERY_SCHOOL = None
SCHOOL_NAMES = ("Fire", "Ice", "Storm", "Myth", "Life", "Death", "Balance", "Shadow", "Moon", "Sun")
FLAT_STATS = {"MaxHealth", "MaxMana", "FlatDamage", "FlatReduceDamage"}
PERCENT_INDEX_BASE = 99
TYPICAL_HIT = 150.0
MANA_WEIGHT = 0.5
ONE_SCHOOL_RESIST_WEIGHT = 0.25
STAT_PATTERN = re.compile(r"^Canonical(?P<school>" + "|".join(SCHOOL_NAMES) + r"|All)?(?P<kind>[A-Za-z]+)$")
UPGRADE_MARGIN = 0.01


@dataclass(frozen=True)
class Stat:
    """`value` of `kind` ("MaxHealth", "ReduceDamage", ...) for `school`, or for every school when it is None.
    Percentages are in percent: 2.0 is 2%."""
    kind: str
    school: str | None
    value: float


@dataclass(frozen=True)
class Requirement:
    """An equip requirement. `kind` is "list" (with `parts`), "level at least" or "school" (with `value`), or the
    game's own type name for one this module does not understand. `negate` is the game's applyNOT, and `either`
    says the requirement joins the ones before it with OR instead of AND."""
    kind: str
    value: object = None
    negate: bool = False
    either: bool = False
    parts: tuple[Requirement, ...] = ()


@dataclass(frozen=True)
class Item:
    """An item in the backpack or worn. `slot` is its equipment slot ("Hat", "Robe", ...), `effects` its equip
    effects as (effect name, lookup index), and `requirement` None when anyone can wear it."""
    id: int
    name: str | None
    slot: str | None
    effects: tuple[tuple[str, int], ...]
    requirement: Requirement | None = None
    equipped: bool = False


@dataclass(frozen=True)
class Wizard:
    school: str
    level: int
    max_health: int
    max_mana: int


def stat_of(effect_name: str, index: int) -> Stat | None:
    """The stat a canonical stat effect gives at a lookup index, or None for effects this module does not read."""
    match = STAT_PATTERN.match(effect_name)
    if match is None:
        return None
    kind = match["kind"]
    school = None if match["school"] in (None, "All") else match["school"]
    value = index + 1 if kind in FLAT_STATS else index - PERCENT_INDEX_BASE
    return Stat(kind, school, float(value)) if value > 0 else None


def stats_of(item: Item) -> list[Stat]:
    return [stat for name, index in item.effects if (stat := stat_of(name, index)) is not None]


def meets(requirement: Requirement | None, wizard: Wizard) -> bool | None:
    """Whether the wizard meets a requirement: True, False, or None when a part of it is not understood."""
    if requirement is None:
        return True
    if requirement.kind == "list":
        result = True
        for index, part in enumerate(requirement.parts):
            met = meets(part, wizard)
            if met is None:
                return None
            result = met if index == 0 else (result or met) if part.either else (result and met)
    elif requirement.kind == "level at least":
        result = wizard.level >= requirement.value
    elif requirement.kind == "school":
        result = wizard.school == requirement.value
    else:
        return None
    return not result if requirement.negate else result


def wearable(item: Item, wizard: Wizard) -> bool:
    """In a slot this module fills, and the wizard surely meets its requirements."""
    return item.slot in WEARABLE_SLOTS and meets(item.requirement, wizard) is True


def stat_worth(stat: Stat, wizard: Wizard) -> float:
    """Points for one stat, about one per percent of the wizard's strength it adds."""
    mine = stat.school in (EVERY_SCHOOL, wizard.school)
    if stat.kind == "MaxHealth":
        return 100 * stat.value / wizard.max_health
    if stat.kind == "MaxMana":
        return MANA_WEIGHT * 100 * stat.value / wizard.max_mana
    if stat.kind in ("ReduceDamage", "FlatReduceDamage"):
        percent = stat.value if stat.kind == "ReduceDamage" else 100 * stat.value / TYPICAL_HIT
        if stat.school in ("Moon", "Sun"):
            return 0.0
        return percent * (1.0 if stat.school is EVERY_SCHOOL else ONE_SCHOOL_RESIST_WEIGHT)
    if stat.kind in ("Damage", "Accuracy") and mine:
        return stat.value
    if stat.kind == "FlatDamage" and mine:
        return 100 * stat.value / TYPICAL_HIT
    if stat.kind == "PowerPip":
        return stat.value
    if stat.kind == "IncHealing":
        return stat.value / 2
    return 0.0


def worth(item: Item, wizard: Wizard) -> float:
    return sum(stat_worth(stat, wizard) for stat in stats_of(item))


def upgrades(items: list[Item], wizard: Wizard) -> list[Item]:
    """For each slot in WEARABLE_SLOTS, the wearable backpack item worth the most, when it is worth more than
    what the slot holds now (an empty slot holds nothing, worth 0). In slot order."""
    chosen = []
    for slot in WEARABLE_SLOTS:
        worn = [item for item in items if item.equipped and item.slot == slot]
        held = max((worth(item, wizard) for item in worn), default=0.0)
        candidates = [item for item in items if not item.equipped and item.slot == slot and wearable(item, wizard)]
        best = max(candidates, key=lambda item: worth(item, wizard), default=None)
        if best is not None and worth(best, wizard) > held + UPGRADE_MARGIN:
            chosen.append(best)
    return chosen


def describe_stats(item: Item) -> str:
    """"+59 max health, +1% resistance (every school)"."""
    names = {"MaxHealth": "max health", "MaxMana": "max mana", "ReduceDamage": "resistance", "Damage": "damage",
             "Accuracy": "accuracy", "FlatDamage": "flat damage", "FlatReduceDamage": "flat resistance",
             "PowerPip": "power pip chance", "IncHealing": "incoming healing"}
    parts = []
    for stat in stats_of(item):
        unit = "" if stat.kind in FLAT_STATS else "%"
        parts.append(f"+{stat.value:g}{unit} {names.get(stat.kind, stat.kind)} ({stat.school or 'every school'})"
                     if stat.kind not in ("MaxHealth", "MaxMana") else f"+{stat.value:g} {names[stat.kind]}")
    return ", ".join(parts) or "no stats read"
