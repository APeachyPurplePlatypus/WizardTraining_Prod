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
combat strategies already lost with against each group of enemies, so a run started again after a defeat does not
fight them with one that lost, and whether the wizard was still recharging after a defeat (`progress.
still_to_recharge`): a run started again in the hub after one walked out with 31 of 89 mana, and the zone the
Recall button's mark is in, with the place the button names and why it was set, so a defeat or a new run can
still recall to it, and for planning with the travel buttons (`travelplan`): which zones a door leads between, each
world's hub, and the measured walk speed, zone crossing time and load times of Go Home and Recall, and the
dungeons found reset after a refill trip out by the travel buttons, refilled in place from then on, and the
world being cleared of its quests (`--clear-world`) with the quest paused for it, and the doors a zone's data does
not list, where a walk changed the zone by accident (`routes.hidden_doors_to_keep_out_of`), the dungeon a door
mark is for, the quests parked while clearing a world, with the level each was parked at, and the zones each
reagent grows in, the one where it was last found first, with the zones searched for it since without a find,
so a run started again does not search them again, and the reagents still wanted by parked quests. Without them, every new run walked into teleporters
to find out again, and walked into Cyclops Lane's tents again. Not kept: obstacles, because the players and
enemies that caused most of them move on, and "no effect" teleport verdicts, because a walk that fell short of a
volume once looked like one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .teleports import NO_EFFECT
from .routes import add_hidden_door
from .travelplan import link_zones


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
    combat_strategies_tried: dict[str, list[str]] = field(default_factory=dict)
    recharging: bool = False
    marked_in: str | None = None
    mark_tip: str | None = None
    zone_links: dict[str, list[str]] = field(default_factory=dict)
    travel_costs: dict[str, float] = field(default_factory=dict)
    hubs: dict[str, str] = field(default_factory=dict)
    mark_purpose: str | None = None
    mark_quest: str | None = None
    leaving_resets: list[str] = field(default_factory=list)
    clearing_world: str | None = None
    paused_quest: str | None = None
    hidden_doors: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    mark_door_for: str | None = None
    parked_quests: dict[str, int] = field(default_factory=dict)
    reagent_zones: dict[str, list[str]] = field(default_factory=dict)
    reagent_searched: dict[str, list[str]] = field(default_factory=dict)
    wanted_reagents: dict[str, str] = field(default_factory=dict)

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
                   combat_strategies_tried={enemies: list(names)
                                            for enemies, names in data.get("combat_strategies_tried", {}).items()},
                   recharging=bool(data.get("recharging", False)),
                   marked_in=data.get("marked_in"), mark_tip=data.get("mark_tip"),
                   zone_links={zone: list(others) for zone, others in data.get("zone_links", {}).items()},
                   travel_costs={name: float(value) for name, value in data.get("travel_costs", {}).items()},
                   hubs=dict(data.get("hubs", {})), mark_purpose=data.get("mark_purpose"),
                   mark_quest=data.get("mark_quest"), leaving_resets=list(data.get("leaving_resets", [])),
                   clearing_world=data.get("clearing_world"), paused_quest=data.get("paused_quest"),
                   hidden_doors={zone: [(int(x), int(y)) for x, y in points]
                                 for zone, points in data.get("hidden_doors", {}).items()},
                   mark_door_for=data.get("mark_door_for"),
                   parked_quests={title: int(level) for title, level in data.get("parked_quests", {}).items()},
                   reagent_zones={reagent: list(zones) for reagent, zones in data.get("reagent_zones", {}).items()},
                   reagent_searched={reagent: list(zones)
                                     for reagent, zones in data.get("reagent_searched", {}).items()},
                   wanted_reagents=dict(data.get("wanted_reagents", {})))

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
        record.combat_strategies_tried = {enemies: list(names) for enemies, names in self.combat_strategies_tried.items()}
        record.recharging = self.recharging
        record.marked_in, record.mark_tip = self.marked_in, self.mark_tip
        record.mark_purpose, record.mark_quest = self.mark_purpose, self.mark_quest
        record.zone_links = {zone: list(others) for zone, others in self.zone_links.items()}
        record.travel_costs, record.hubs = dict(self.travel_costs), dict(self.hubs)
        record.leaving_resets = list(self.leaving_resets)
        record.clearing_world, record.paused_quest = self.clearing_world, self.paused_quest
        record.hidden_doors = {zone: list(points) for zone, points in self.hidden_doors.items()}
        record.mark_door_for, record.parked_quests = self.mark_door_for, dict(self.parked_quests)
        record.reagent_zones = {reagent: list(zones) for reagent, zones in self.reagent_zones.items()}
        record.reagent_searched = {reagent: list(zones) for reagent, zones in self.reagent_searched.items()}
        record.wanted_reagents = dict(self.wanted_reagents)

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
        self.recharging = record.recharging
        self.marked_in, self.mark_tip = record.marked_in, record.mark_tip
        self.mark_purpose, self.mark_quest = record.mark_purpose, record.mark_quest
        for zone, others in record.zone_links.items():
            for other in others:
                link_zones(self.zone_links, zone, other)
        self.travel_costs.update(record.travel_costs)
        self.hubs.update(record.hubs)
        self.leaving_resets.extend(zone for zone in record.leaving_resets if zone not in self.leaving_resets)
        self.clearing_world, self.paused_quest = record.clearing_world, record.paused_quest
        self.mark_door_for, self.parked_quests = record.mark_door_for, dict(record.parked_quests)
        self.reagent_zones = {reagent: list(zones) for reagent, zones in record.reagent_zones.items()}
        self.reagent_searched = {reagent: list(zones) for reagent, zones in record.reagent_searched.items()}
        self.wanted_reagents = dict(record.wanted_reagents)
        for zone, points in record.hidden_doors.items():
            for point in points:
                add_hidden_door(self.hidden_doors, zone, point)
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
