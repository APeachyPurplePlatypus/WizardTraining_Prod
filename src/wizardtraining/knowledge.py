"""What runs learn about the game that later runs reuse, kept in the runtime folder. No game access, so it is
tested offline.

Kept: where each teleport volume leads, zones whose collision data misses obstacles, so routes there try the
nav graph first, how often each patrol path was in view and how often an enemy was seen on it
(`patrols.note_sightings`), so routes stop counting paths no enemy walks as street, the spells the wizard knows,
so a spell learned between runs is still noticed (`spells.newly_learned`), and zones where enemies have been met,
so a run that starts in Cyclops Lane, or meets no enemy at its entrance, does not take it for a place to wait for
mana, the zones entered with X at a prompt, towers and dungeons the wizard does not leave to train
(`training.in_dungeon`), and the level it last trained at, so the school is visited once a level, and the steps across a gap between two
walkable pieces that did not land in the other piece, which the same two pieces will not do on another day, and the
combat strategy the last defeat changed to, with the strategies already lost with against each group of enemies, so
a run started again after a defeat does not fight with the one that lost. Without them, every new run walked into teleporters
to find out again, and walked into Cyclops Lane's tents again. Not kept: obstacles, because the players and
enemies that caused most of them move on, and "no effect" teleport verdicts, because a walk that fell short of a
volume once looked like one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .teleports import NO_EFFECT


@dataclass
class Knowledge:
    teleport_outcomes: dict[str, dict[str, object]] = field(default_factory=dict)
    nav_first_zones: list[str] = field(default_factory=list)
    zones_with_enemies: list[str] = field(default_factory=list)
    path_sightings: dict[str, dict[str, int]] = field(default_factory=dict)
    path_views: dict[str, dict[str, int]] = field(default_factory=dict)
    known_spells: list[int] = field(default_factory=list)
    entered_with_x: list[str] = field(default_factory=list)
    trained_at_level: int = 0
    failed_gaps: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    combat_strategy: str = "default"
    combat_strategies_tried: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Knowledge":
        """What earlier runs saved, or nothing when the file is missing or unreadable."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(teleport_outcomes={zone: dict(outcomes)
                                      for zone, outcomes in data.get("teleport_outcomes", {}).items()},
                   nav_first_zones=list(data.get("nav_first_zones", [])),
                   zones_with_enemies=list(data.get("zones_with_enemies", [])),
                   path_sightings=counts_by_zone(data.get("path_sightings", {})),
                   path_views=counts_by_zone(data.get("path_views", {})),
                   known_spells=[int(spell) for spell in data.get("known_spells", [])],
                   entered_with_x=list(data.get("entered_with_x", [])),
                   trained_at_level=int(data.get("trained_at_level", 0)),
                   failed_gaps={zone: [(int(a), int(b)) for a, b in pairs]
                                for zone, pairs in data.get("failed_gaps", {}).items()},
                   combat_strategy=str(data.get("combat_strategy", "default")),
                   combat_strategies_tried={enemies: list(names)
                                            for enemies, names in data.get("combat_strategies_tried", {}).items()})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def give_to(self, record) -> None:
        """Start a run with what earlier runs learned."""
        record.teleport_outcomes = {zone: dict(outcomes) for zone, outcomes in self.teleport_outcomes.items()}
        record.nav_first_zones = list(self.nav_first_zones)
        record.zones_with_enemies = list(self.zones_with_enemies)
        record.path_sightings = counts_by_zone(self.path_sightings)
        record.path_views = counts_by_zone(self.path_views)
        record.known_spells = list(self.known_spells)
        record.entered_with_x = list(self.entered_with_x)
        record.trained_at_level = self.trained_at_level
        record.failed_gaps = {zone: list(pairs) for zone, pairs in self.failed_gaps.items()}
        record.combat_strategy = self.combat_strategy
        record.combat_strategies_tried = {enemies: list(names) for enemies, names in self.combat_strategies_tried.items()}

    def learn_from(self, record) -> None:
        """Keep what a run found out, leaving out "no effect" verdicts."""
        for zone in record.nav_first_zones:
            if zone not in self.nav_first_zones:
                self.nav_first_zones.append(zone)
        for zone in record.zones_with_enemies:
            if zone not in self.zones_with_enemies:
                self.zones_with_enemies.append(zone)
        for zone in record.entered_with_x:
            if zone not in self.entered_with_x:
                self.entered_with_x.append(zone)
        self.trained_at_level = max(self.trained_at_level, record.trained_at_level)
        self.combat_strategy = record.combat_strategy
        for enemies, names in record.combat_strategies_tried.items():
            kept = self.combat_strategies_tried.setdefault(enemies, [])
            kept.extend(name for name in names if name not in kept)
        for zone, pairs in record.failed_gaps.items():
            kept = self.failed_gaps.setdefault(zone, [])
            kept.extend(pair for pair in map(tuple, pairs) if pair not in kept)
        for mine, theirs in ((self.path_sightings, record.path_sightings), (self.path_views, record.path_views)):
            for zone, counts in theirs.items():
                for path, count in counts.items():
                    kept = mine.setdefault(zone, {})
                    kept[path] = max(kept.get(path, 0), count)
        self.known_spells = sorted(set(self.known_spells) | set(record.known_spells))
        for zone, outcomes in record.teleport_outcomes.items():
            for volume, outcome in outcomes.items():
                if outcome != NO_EFFECT:
                    self.teleport_outcomes.setdefault(zone, {})[volume] = outcome

    def summary(self) -> str:
        volumes = sum(len(outcomes) for outcomes in self.teleport_outcomes.values())
        return (f"{volumes} teleport outcomes in {len(self.teleport_outcomes)} zones, "
                f"{len(self.nav_first_zones)} zones routed by the nav graph first, "
                f"{len(self.zones_with_enemies)} zones with enemies, patrol paths watched in "
                f"{len(self.path_views)} zones")


def counts_by_zone(data: dict) -> dict[str, dict[str, int]]:
    """A copy of per-zone counts. A run starts from the saved counts and only adds to them, so the larger of two
    counts is the later one."""
    return {zone: {path: int(count) for path, count in counts.items()} for zone, counts in data.items()}
