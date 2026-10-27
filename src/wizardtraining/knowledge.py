"""What runs learn about the game that later runs reuse, kept in the runtime folder. No game access, so it is
tested offline.

Kept: zones where health does not come back while resting, where each teleport volume leads, and zones whose
collision data misses obstacles, so routes there try the nav graph first. Without them, every new run rested
a minute in the same interior for nothing, walked into teleporters to find out again, and walked into
Cyclops Lane's tents again. Not kept: obstacles, because the players and enemies that caused most of them move
on, and "no effect" teleport verdicts, because a walk that fell short of a volume once looked like one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .teleports import NO_EFFECT


@dataclass
class Knowledge:
    zones_without_regeneration: list[str] = field(default_factory=list)
    teleport_outcomes: dict[str, dict[str, object]] = field(default_factory=dict)
    nav_first_zones: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Knowledge":
        """What earlier runs saved, or nothing when the file is missing or unreadable."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(zones_without_regeneration=list(data.get("zones_without_regeneration", [])),
                   teleport_outcomes={zone: dict(outcomes)
                                      for zone, outcomes in data.get("teleport_outcomes", {}).items()},
                   nav_first_zones=list(data.get("nav_first_zones", [])))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def give_to(self, record) -> None:
        """Start a run with what earlier runs learned."""
        record.zones_without_regeneration = list(self.zones_without_regeneration)
        record.teleport_outcomes = {zone: dict(outcomes) for zone, outcomes in self.teleport_outcomes.items()}
        record.nav_first_zones = list(self.nav_first_zones)

    def learn_from(self, record) -> None:
        """Keep what a run found out, leaving out "no effect" verdicts."""
        for zone in record.zones_without_regeneration:
            if zone not in self.zones_without_regeneration:
                self.zones_without_regeneration.append(zone)
        for zone in record.nav_first_zones:
            if zone not in self.nav_first_zones:
                self.nav_first_zones.append(zone)
        for zone, outcomes in record.teleport_outcomes.items():
            for volume, outcome in outcomes.items():
                if outcome != NO_EFFECT:
                    self.teleport_outcomes.setdefault(zone, {})[volume] = outcome

    def summary(self) -> str:
        volumes = sum(len(outcomes) for outcomes in self.teleport_outcomes.values())
        return (f"{len(self.zones_without_regeneration)} zones without regeneration, {volumes} teleport outcomes "
                f"in {len(self.teleport_outcomes)} zones, {len(self.nav_first_zones)} zones routed by the nav graph first")
