"""A live log of what the wizard observes and does, so a run can be followed and explained from facts.

The report is written when a run ends. While it runs, the event log says what actually happened: which
enemies a battle had and how many rounds it took, how health and gold changed, why a walk ended, which
zone and quest the wizard is on. Nobody watching has to guess from timings. Each event is one JSON line
(time, kind, summary, fields) in runtime/events-<started>.jsonl, and its summary also goes to the
"wizardtraining.events" logger. No game access, so it is tested offline.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from collections import Counter
from pathlib import Path

from .reports import plain

logger = logging.getLogger("wizardtraining.events")


class EventLog:
    def __init__(self, path: Path | None = None):
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def in_folder(cls, folder: Path) -> "EventLog":
        return cls(folder / f"events-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl")

    def emit(self, kind: str, summary: str, **fields) -> dict:
        event = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, "summary": summary,
                 **fields}
        logger.info("%s: %s", kind, summary)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, default=plain) + "\n")
        return event


def health_text(state: dict) -> str:
    return f"{state.get('health')}/{state.get('max_health')}"


def change(before, after) -> str:
    if isinstance(before, int) and isinstance(after, int) and after != before:
        return f"{'+' if after > before else ''}{after - before}"
    return "no change"


def enemy_names(enemies: list[dict]) -> str:
    return names_with_counts(Counter(enemy.get("name") or "unknown" for enemy in enemies))


def names_with_counts(counts: Counter) -> str:
    return ", ".join(name if count == 1 else f"{name} x{count}" for name, count in counts.items()) or "none seen"


def enemies_at_once(rounds: list[dict]) -> tuple[int, Counter]:
    """The most enemies seen in one round, and for each name the most seen at once. Enemies join battles
    after the first round, and same-named enemies can't be told apart, so this is what can be said for sure."""
    most, by_name = 0, Counter()
    for battle_round in rounds:
        enemies = battle_round["view"]["enemies"]
        most = max(most, len(enemies))
        by_name |= Counter(enemy.get("name") or "unknown" for enemy in enemies)
    return most, by_name


MARKUP = re.compile(r"<[^>]*>")
DIALOG_TEXT_LIMIT = 4000


def dialog_text(pages: list[str]) -> str:
    """The pages of a conversation as plain text, one per line: the game's markup tags removed, and cut at
    DIALOG_TEXT_LIMIT characters."""
    lines = [" ".join(MARKUP.sub(" ", page).split()) for page in pages]
    return "\n".join(line for line in lines if line)[:DIALOG_TEXT_LIMIT]


def describe_round(entry: dict) -> str:
    view = entry["view"]
    enemies = ", ".join(f"{enemy['name']} {enemy['health']}"
                        f"{modifier_text(enemy.get('incoming'), enemy.get('resistances'))}"
                        f"{' (cannot be stunned now)' if enemy.get('stunnable') is False else ''}"
                        for enemy in view["enemies"]) or "none"
    mana = f", {view['mana']} mana" if view.get("mana") is not None else ""
    reopened = "reopened the card choice; " if entry.get("reopened card choice") else ""
    return (f"round {view['round_number']}: me {view['health']}/{view['max_health']} with {view['pips']} pips{mana}; "
            f"{reopened}{entry['action']}; enemies left: {enemies}{hand_text(view.get('cards'))}")


def hand_text(cards) -> str:
    """"; hand: Frost Beetle x2, Snow Serpent (2 pips)" listing the cards in hand once each, with pip costs, or ""."""
    if not cards:
        return ""
    counts = Counter(card.get("name") for card in cards)
    costs = {card.get("name"): card.get("pips") for card in cards}
    parts = [f"{name}{f' x{count}' if count > 1 else ''}{f' ({costs[name]} pips)' if costs[name] else ''}"
             for name, count in counts.items()]
    return "; hand: " + ", ".join(parts)


def modifier_text(modifiers, resistances=None) -> str:
    """" (Myth -50%; resists Fire 25%, Ice -15%)" for an enemy's shields, wards and traps, then its resistances
    (negative for a weakness), or "" without any."""
    parts = []
    if modifiers:
        parts.append(", ".join(f"{modifier['school']} {modifier['percent']:+d}%" for modifier in modifiers))
    if resistances:
        parts.append("resists " + ", ".join(f"{school} {value:.0%}" for school, value in resistances.items()))
    return f" ({'; '.join(parts)})" if parts else ""


def describe_battle(battle: dict, *, seconds: float, before: dict, after: dict, outcome: str) -> str:
    rounds = battle["rounds"]
    most, by_name = enemies_at_once(rounds)
    untaken = [str(entry["view"]["round_number"]) for entry in rounds if entry.get("sent") == []]
    untaken_text = f"; the game logged no move in rounds {', '.join(untaken)}" if untaken else ""
    return (f"{outcome} after {len(rounds)} rounds in {seconds:.0f} s against up to {most} at once "
            f"({names_with_counts(by_name)}); health {health_text(before)} -> {health_text(after)}, "
            f"gold {change(before.get('gold'), after.get('gold'))}, level {after.get('level')}{untaken_text}")


def describe_changes(before: dict | None, after: dict, quest_before: dict | None, quest_after: dict | None) -> list[tuple]:
    """(kind, summary) for each change between two readings: zone, level, and the quest or its goal."""
    found = []
    if before is not None and after["zone"] != before["zone"]:
        found.append(("zone", f"{before['zone']} -> {after['zone']}"))
    if before is not None and isinstance(after["level"], int) and after["level"] != before["level"]:
        found.append(("level", f"{before['level']} -> {after['level']}"))
    if quest_after and (quest_before is None or (quest_before.get("title"), quest_before.get("goal_id"))
                        != (quest_after.get("title"), quest_after.get("goal_id"))):
        destination = quest_after.get("goal_zone") or "this zone"
        kind = " (side quest)" if quest_after.get("main") is False else ""
        found.append(("quest", f"{quest_after.get('title') or quest_after.get('name')}{kind}: "
                               f"{quest_after.get('goal')} goal in {destination}"))
    return found
