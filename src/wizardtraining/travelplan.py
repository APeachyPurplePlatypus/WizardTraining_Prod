"""Whether the game's own travel buttons get the wizard to its goal sooner than walking. No game access, so it is
tested offline.

The operator, 2026-10-28: "teleport is now a funcion you can incorperate to improve movement efficency in your
planning of routes, this could help a lot with but not limited to back tracking". The teleports are the game's own
buttons: Go Home to the world's hub (free, with a cooldown), Recall Location to the mark (about 5 mana, with a
cooldown) and Mark Location (about 5 mana). Deimos and WizWalker teleports stay forbidden.

Each way is estimated in seconds: walking, the walk to this zone's door plus a learned time for each further zone;
a teleport, its learned load time plus the zones from where it lands. Zones are linked as the wizard walks between
them (`link_zones`), and the times are learned as they are measured (`TravelCosts.learn`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

WALK, GO_HOME, RECALL = "walk", "go home", "recall"
TRAVEL_MANA_COST = 5
TRAVEL_MANA_RESERVE = 30
DETOUR = 1.3
WORTH_IT_SECONDS = 20.0
WORTH_IT_SHARE = 0.25
LEARNING_WEIGHT = 0.3
HUBS = {"WizardCity": "WizardCity/WC_Hub", "Krokotopia": "Krokotopia/KT_Hub"}
# Where Go Home lands in each world: "Go to The Commons" in Wizard City; in Krokotopia it went to KT_Hub (23:18).


@dataclass
class TravelCosts:
    """Measured in the game: a 17,594-unit walk through the Pyramid's Chamber took 49 s (about 360 a second); Go
    Home and Recall each changed zones within about 6 to 12 s. A zone's crossing is a guess until measured."""
    walk_speed: float = 360.0
    go_home_seconds: float = 12.0
    recall_seconds: float = 12.0
    zone_seconds: float = 60.0

    def learn(self, name: str, measured: float) -> None:
        setattr(self, name, (1 - LEARNING_WEIGHT) * getattr(self, name) + LEARNING_WEIGHT * measured)

    def as_dict(self) -> dict[str, float]:
        return {name: round(value, 1) for name, value in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: dict | None) -> "TravelCosts":
        known = cls()
        return cls(**{name: float(value) for name, value in (data or {}).items() if hasattr(known, name)})


@dataclass(frozen=True)
class TravelChoice:
    way: str
    estimates: dict[str, float | None]
    reason: str

    def describe(self, here: str, goal_zone: str) -> str:
        shown = ", ".join(f"{way} {'?' if seconds is None else f'~{seconds:.0f} s'}"
                          for way, seconds in self.estimates.items())
        return f"from {here} to {goal_zone}: {shown}; {self.way}: {self.reason}"


def link_zones(links: dict[str, list[str]], one: str, other: str) -> None:
    """Remember that a door leads between two zones, both ways."""
    for start, end in ((one, other), (other, one)):
        if end not in links.setdefault(start, []):
            links[start].append(end)


def zone_hops(links: dict[str, list[str]], start: str, goal: str) -> int | None:
    """How many doors lie between two zones by the links known, or None when no way is known."""
    if start == goal:
        return 0
    seen, queue = {start}, deque([(start, 0)])
    while queue:
        zone, hops = queue.popleft()
        for following in links.get(zone, []):
            if following == goal:
                return hops + 1
            if following not in seen:
                seen.add(following)
                queue.append((following, hops + 1))
    return None


def spare_mana(mana) -> bool:
    """Mana for a travel button with TRAVEL_MANA_RESERVE left over for fights (two or three heals' worth)."""
    return isinstance(mana, int) and not isinstance(mana, bool) and mana >= TRAVEL_MANA_RESERVE + TRAVEL_MANA_COST


def from_landing(hops: int, costs: TravelCosts) -> float:
    """From where a teleport lands to a goal `hops` zones away: half a zone in the goal's zone itself, else the way to
    the door, each zone between, and half the goal's zone, about a zone each."""
    return costs.zone_seconds / 2 if hops == 0 else hops * costs.zone_seconds


def choose_travel(*, here: str, goal_zone: str, door_distance: float, links: dict[str, list[str]], hub: str | None,
                  marked_in: str | None, mana, costs: TravelCosts, go_home_ready: bool,
                  recall_ready: bool) -> TravelChoice:
    """Walk, Go Home or Recall, whichever is expected to reach the goal's zone first. A teleport has to save at
    least WORTH_IT_SECONDS and WORTH_IT_SHARE of the walk, as the estimates are rough; when the way on foot is not
    known, only a teleport that lands in the goal's zone is taken."""
    hops_on_foot = zone_hops(links, here, goal_zone)
    walk = (None if hops_on_foot is None else
            door_distance * DETOUR / costs.walk_speed + max(hops_on_foot - 1, 0) * costs.zone_seconds
            + costs.zone_seconds / 2)
    landings: dict[str, int] = {}
    if go_home_ready and hub and here != hub and (hops := zone_hops(links, hub, goal_zone)) is not None:
        landings[GO_HOME] = hops
    if recall_ready and marked_in and here != marked_in and spare_mana(mana):
        if (hops := zone_hops(links, marked_in, goal_zone)) is not None:
            landings[RECALL] = hops
    estimates = {WALK: walk,
                 GO_HOME: (costs.go_home_seconds + from_landing(landings[GO_HOME], costs)) if GO_HOME in landings else None,
                 RECALL: (costs.recall_seconds + from_landing(landings[RECALL], costs)) if RECALL in landings else None}
    teleports = sorted((estimates[way], way) for way in landings)
    if not teleports:
        return TravelChoice(WALK, estimates, "no travel button lands nearer")
    seconds, way = teleports[0]
    if walk is None:
        if landings[way] == 0:
            return TravelChoice(way, estimates, "the way on foot is not known, and it lands in the goal's zone")
        return TravelChoice(WALK, estimates, "the way on foot is not known, and no button lands in the goal's zone")
    if walk - seconds >= max(WORTH_IT_SECONDS, WORTH_IT_SHARE * walk):
        return TravelChoice(way, estimates, f"saves about {walk - seconds:.0f} s")
    return TravelChoice(WALK, estimates, f"{way} would save {max(walk - seconds, 0):.0f} s at most, too little to "
                                         "count on")


def worth_going_home_for_wisps(here: str, hub: str | None, went_home_from: set[str]) -> bool:
    """A safe zone searched with no wisp of the kind needed left, and not the hub: Go Home (free) and search the hub,
    once from each zone. Woken after a defeat, the wizard searched the Krokotopia world teleporter room for wisps,
    found none and stood for mana, about 2 a minute; the hub next to it gave 35 to 80 mana in wisps in a minute."""
    return hub is not None and here != hub and here not in went_home_from


def worth_a_way_back_mark(here: str, finished_zone: str | None, next_goal_zone: str | None, hub: str | None,
                          links: dict[str, list[str]], marked_in: str | None, mana) -> bool:
    """A goal was just finished here and the next one is in another zone: quests often come back to where they were
    given or advanced ("Back to the Archeologist"), so mark the spot to recall to, unless the hub is no more than a
    door away (Go Home, free, nearly gets there) or it is already marked, and only with mana to spare."""
    if finished_zone != here or not next_goal_zone or next_goal_zone == here or marked_in == here:
        return False
    if hub == here or (hub is not None and (zone_hops(links, hub, here) or 0) == 1):
        return False
    return spare_mana(mana)
