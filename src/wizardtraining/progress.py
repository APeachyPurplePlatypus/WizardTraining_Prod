"""Bookkeeping for a quest run: what each turn did, whether it was progress, and when to stop.
No game access, so it is tested offline.

A turn is progress only if something really changed: the wizard moved a meaningful distance, or a
battle, dialog, zone load or arrival interrupted the walk. Counting "arrived where it already stood"
as progress once kept a run looping for 200 turns.
"""

from __future__ import annotations

import re

import datetime
from dataclasses import asdict, dataclass, field

from .geometry import distance_to_path, flat_distance
from .routes import COLLISION, NAV
from .travelplan import spare_mana

ENEMY_NEAR_PATH = "an enemy is near the path ahead"
DUEL_NEAR_PATH = "a duel is near the path ahead"
ENEMIES_IN_THE_WAY = "enemies leave no route"
DUEL_BLOCKS_THE_WAY = "another player's fight leaves no route"
PATH_THREATS = {ENEMY_NEAR_PATH, DUEL_NEAR_PATH, ENEMIES_IN_THE_WAY}
STATE_CHANGING_INTERRUPTS = {"battle", "dialog", "loading", "target in reach", "arrived"}
MEANINGFUL_TRAVEL_DISTANCE = 300.0
ENEMY_PATH_CLEARANCE = 500.0
APPROACH_MARGIN = 150.0
HEALTH_WISP_BELOW_FRACTION = 0.65
WISP_ANY_DIRECTION_BELOW_FRACTION = 0.35
POTION_BELOW_FRACTION = 0.4
MANA_BELOW_FRACTION = 0.2
HEALTH_TO_TRAVEL_FRACTION = 0.4
RECHARGE_HEALTH_FRACTION = 0.9
RECHARGE_MANA_FRACTION = 0.8
RECALL_MANA_NEEDED = 8
ENGAGE_MANA_FRACTION = 0.4
ENGAGE_HEALTH_FRACTION = 0.6
TOP_UP_MANA_FRACTION = 0.9
RECALL_MANA_FRACTION = 0.8
RECALL_HEALTH_FRACTION = 0.9


def world_of(zone: str | None) -> str | None:
    """The world a zone belongs to: the first part of its path, "WizardCity" for "WizardCity/WC_Streets/WC_Triton"."""
    return zone.split("/", 1)[0] if zone else None


def leaves_world(here: str | None, destination: str | None) -> bool:
    """True when a goal's zone is in another world than the wizard's."""
    return bool(here and destination) and world_of(here) != world_of(destination)


class StopRun(Exception):
    """Ends the run. The message is the reason given in the report."""


class LimitReached(StopRun):
    """A planned end: the target level, or the time, turn or battle limit. Unlike the other stops, which say
    something is wrong or the operator asked, the run may play on a little to end somewhere safe."""


@dataclass
class Limits:
    target_level: int = 5
    minutes: float = 25.0
    max_turns: int = 200
    max_battles: int = 20
    max_turns_without_progress: int = 4
    max_step_aways: int = 40
    max_defeats: int | None = None
    max_loading_waits_in_a_row: int = 40
    max_immobile_threat_stops_in_a_row: int = 8
    max_duel_waits_in_a_row: int = 20
    max_obstacles_per_zone: int = 40
    max_zone_changes_without_quest_change: int = 10
    max_menu_choices_without_quest_change: int = 3
    stay_in_world: bool = True


@dataclass
class RunRecord:
    limits: Limits
    started_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))
    turns: list[dict] = field(default_factory=list)
    battles: int = 0
    defeats: int = 0
    turns_without_progress: int = 0
    loading_waits_in_a_row: int = 0
    immobile_threat_stops_in_a_row: int = 0
    duel_waits_in_a_row: int = 0
    step_aways: list = field(default_factory=list)
    battle_log: list[dict] = field(default_factory=list)
    dialog_log: list[dict] = field(default_factory=list)
    nav_first_zones: list[str] = field(default_factory=list)
    obstacles: dict[str, list] = field(default_factory=dict)
    zone_changes_without_quest_change: int = 0
    last_place: tuple | None = None
    menu_choices_without_quest_change: int = 0
    last_menu_goal: tuple | None = None
    planner_status: dict[str, dict] = field(default_factory=dict)
    quest: dict | None = None
    hooks: dict | None = None
    start: dict | None = None
    end: dict | str | None = None
    quest_end: dict | None = None
    stopped: str | None = None
    traceback: str | None = None
    hooks_removed: bool | str | None = None
    events_file: str | None = None
    talks_leaving_goal_open: dict[str, int] = field(default_factory=dict)
    teleport_outcomes: dict[str, dict[str, object]] = field(default_factory=dict)
    failed_gaps: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    quests_activated: dict[str, int] = field(default_factory=dict)
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
    deck_capacity: dict[str, int] = field(default_factory=dict)
    enemy_zones: dict[str, list[str]] = field(default_factory=dict)
    essence_quests: dict[str, str] = field(default_factory=dict)
    trainers: dict[str, dict] = field(default_factory=dict)
    heavy_fights: dict[str, int] = field(default_factory=dict)
    enemy_hits: dict[str, int] = field(default_factory=dict)
    refill_after_heavy_fight: bool = False
    dead_search_points: dict[str, list] = field(default_factory=dict)
    held_quests: dict[str, str] = field(default_factory=dict)
    trapping_marks: dict[str, list] = field(default_factory=dict)
    zone_doors: dict[str, dict] = field(default_factory=dict)
    left_dungeon: dict | None = None
    dungeon_zones: list[str] = field(default_factory=list)
    opportunities: dict[str, dict] = field(default_factory=dict)
    measures: dict[str, list] = field(default_factory=dict)
    deck_size: int | None = None
    school_quests_checked: dict[str, int] = field(default_factory=dict)
    walk_strategies_tried: dict[str, list[str]] = field(default_factory=dict)
    tried_wisps: dict[str, float] = field(default_factory=dict)
    visited_objects: list[str] = field(default_factory=list)
    arrivals: dict[str, dict] = field(default_factory=dict)
    explored: dict[str, list] = field(default_factory=dict)
    zones_with_enemies: list[str] = field(default_factory=list)
    path_sightings: dict[str, dict[str, int]] = field(default_factory=dict)
    path_views: dict[str, dict[str, int]] = field(default_factory=dict)
    known_spells: list[int] = field(default_factory=list)
    entered_with_x: list[str] = field(default_factory=list)
    trained_at_level: int = 0

    def record_turn(self, turn: dict) -> None:
        self.turns.append(turn)
        self.turns_without_progress = 0 if turn["progress"] else self.turns_without_progress + 1

    def note_place(self, zone, quest_goal) -> None:
        """Count zone changes since the quest goal last changed. Doors count as progress, so a wizard
        walking back and forth through the same doors would otherwise never trip a limit. A travel button (Go Home,
        Recall, a dungeon's return button) clears `last_place` and starts the count again: a refill trip is no door
        loop, and the walk from the Commons to Curfew!'s door five zones on, with three refill trips on the way,
        stopped the run at the door (19:28)."""
        if self.last_place is None:
            self.zone_changes_without_quest_change = 0
        else:
            last_zone, last_goal = self.last_place
            if quest_goal != last_goal:
                self.zone_changes_without_quest_change = 0
            elif zone != last_zone:
                self.zone_changes_without_quest_change += 1
        self.last_place = (zone, quest_goal)

    def note_menu_choice(self, quest_goal) -> None:
        """Count NPC-menu choices made while the quest goal stays the same. Dialogs count as progress, so a
        menu that reopens after every conversation would otherwise never trip a limit."""
        same_goal = self.last_menu_goal == quest_goal
        self.menu_choices_without_quest_change = self.menu_choices_without_quest_change + 1 if same_goal else 1
        self.last_menu_goal = quest_goal

    def as_report(self) -> dict:
        return {"source": "wizwalker", "simulated": False, **asdict(self)}


def progressed(did: str, **details) -> dict:
    return {"did": did, "progress": True, **details}


def stalled(did: str, **details) -> dict:
    return {"did": did, "progress": False, **details}


def check_limits(record: RunRecord, *, seconds_left: float, stop_requested: bool) -> None:
    limits = record.limits
    if stop_requested:
        raise StopRun("stop requested (STOP file)")
    if seconds_left <= 0:
        raise LimitReached("time limit reached")
    if len(record.turns) >= limits.max_turns:
        raise LimitReached("turn limit reached")
    if record.battles >= limits.max_battles:
        raise LimitReached("battle limit reached")
    if record.turns_without_progress >= limits.max_turns_without_progress:
        raise StopRun("several turns without progress")
    if len(record.step_aways) >= limits.max_step_aways:
        raise StopRun("stepped away from enemies too often")
    if record.zone_changes_without_quest_change > limits.max_zone_changes_without_quest_change:
        raise StopRun("changed zones many times without the quest changing; possibly going back and forth through doors")
    if record.menu_choices_without_quest_change > limits.max_menu_choices_without_quest_change:
        raise StopRun("an NPC's menu kept reopening without the quest changing; left for the operator")


def wanted_wisp(health: float | None, mana: float | None) -> str | None:
    """"health" below WISP_ANY_DIRECTION_BELOW_FRACTION, then "mana" below MANA_BELOW_FRACTION, then "health" below
    HEALTH_WISP_BELOW_FRACTION, else None. Every spell costs a mana per pip, wand spells too, so a wizard out of
    mana can neither attack nor heal: low mana comes before middling health. A mana wisp gave only +3 of 28, and
    used-up ones still show as entities, so mana wisps are sought only when mana is low."""
    if health is not None and health < WISP_ANY_DIRECTION_BELOW_FRACTION:
        return "health"
    if mana is not None and mana < MANA_BELOW_FRACTION:
        return "mana"
    if health is not None and health < HEALTH_WISP_BELOW_FRACTION:
        return "health"
    return None


def mana_for_a_fight(mana: float | None) -> bool:
    """At least ENGAGE_MANA_FRACTION of the mana pool, or mana unknown. A Warhorn fight took 6 to 10 mana of 30,
    and with 1 mana the wizard walked into General Akilles and his Cyclops and could only pass."""
    return mana is None or mana >= ENGAGE_MANA_FRACTION


def health_for_a_fight(health: float | None) -> bool:
    """At least ENGAGE_HEALTH_FRACTION of max health, or health unknown. Won fights at level 8 cost up to 435
    health of 717, and a wizard logged back in with 1 health was defeated in its first round."""
    return health is None or health >= ENGAGE_HEALTH_FRACTION


def safe_to_stand(zone, zones_with_enemies, enemies_in_sight: int) -> bool:
    """Whether the wizard may stand still here: no enemy in sight, in a zone where none has ever been met. A street
    can have none loaded for a moment: at level 10 the run stopped in Firecat Alley with none in sight, and left
    the wizard idle where they patrol."""
    return zone not in zones_with_enemies and enemies_in_sight == 0


def mana_to_travel(mana: float | None) -> bool:
    """At least MANA_BELOW_FRACTION of the pool, or unknown. Below it the wizard refills mana before any goal, not
    only before a fight the quest asks for: walking to a Firecat Alley waypoint with 3 of 32, any fight on the way
    would be lost, and the zones that give mana back are next door."""
    return mana is None or mana >= MANA_BELOW_FRACTION


def health_to_travel(health: float | None) -> bool:
    """At least HEALTH_TO_TRAVEL_FRACTION of max health, or unknown. Below it the wizard refills health before any
    goal, not only before a fight the quest asks for: defeated by two Flame Servants in the Pyramid's Chamber, it
    woke in the Krokotopia hub with 1 health and walked straight back toward them at 55 of 1102 to talk to the
    assistant behind them."""
    return health is None or health >= HEALTH_TO_TRAVEL_FRACTION


RESUME_TRIP_SECONDS = 20 * 60.0


def resume_in_time(left_at, now: float) -> bool:
    """A trip out of a dungeon is back within RESUME_TRIP_SECONDS of leaving it (wall-clock seconds, kept across
    restarts). The dungeon's timer runs 30 minutes (the operator, 2026-10-28 20:48 UTC: "This confirms the 30 min
    timer"); the margin covers the refill and the load back in."""
    return isinstance(left_at, (int, float)) and 0 <= now - left_at <= RESUME_TRIP_SECONDS


def dungeon_held(left: dict, zone_now: str | None, enemies_now: int | None) -> bool:
    """Back by the dungeon's return button: it held when the wizard is in the zone it left and, when the enemies near
    it were counted on leaving (`left["enemies"]`), no more than one more stand near it now; killed ones that came
    back mean the dungeon reset."""
    if zone_now != left.get("zone"):
        return False
    before = left.get("enemies")
    return not (isinstance(before, int) and isinstance(enemies_now, int) and enemies_now > before + 1)


def still_to_recharge(health: float | None, mana: float | None) -> str | None:
    """After a defeat, or with health below HEALTH_TO_TRAVEL_FRACTION: "health" or "mana", whichever is still below
    RECHARGE_HEALTH_FRACTION or RECHARGE_MANA_FRACTION of its pool, health first; None when both are there or
    unknown. The operator: "seek out blue and red wisps in safe areas to recharge after death". Woken in the
    Krokotopia hub with 1 health, the wizard walked back to the Pyramid at 55 of 1102 and lost again."""
    if health is not None and health < RECHARGE_HEALTH_FRACTION:
        return "health"
    if mana is not None and mana < RECHARGE_MANA_FRACTION:
        return "mana"
    return None


def worth_marking(here: str, goal_zone: str | None, marked_in: str | None, mana, *, enemies_here: bool,
                  refused: bool) -> bool:
    """Arrived in the zone the goal is in, where enemies have been met, with no mark there yet and mana for Mark
    Location (about 5) to spare (`travelplan.spare_mana`): a defeat here wakes the wizard in the world's hub, and a mark brings it back by Recall
    Location. At 22:55 and 23:11 the wizard woke in the Krokotopia hub with no mark in the Pyramid's Chamber and
    walked back through the same enemies."""
    return (goal_zone == here and marked_in != here and enemies_here and not refused
            and spare_mana(mana))


def trapped_by(reason: str | None) -> str | None:
    """What leaves the wizard no route from where it stands, from a walk's failure `reason`: "the map" when every
    route method failed with no enemy to blame, as on Kraken Isle; "enemies" when enemies crowd every route
    (ENEMIES_IN_THE_WAY), which they stop doing as they move; None for any other reason."""
    return {"every route method failed": "the map", ENEMIES_IN_THE_WAY: "enemies"}.get(reason)


def worth_recalling(here: str, goal_zone: str | None, marked_in: str | None, mana, door_for: str | None = None,
                    came_from: str | None = None, next_door: bool = False) -> bool:
    """The Recall button holds a mark in the zone the goal is in, or at the door of the dungeon the goal is in
    (`door_for`), the wizard is elsewhere, not in the goal's zone, and it has the mana for Recall Location (about 5).
    The operator: "you might have forgot to use the teleport to the chamber of fire you created to get back there".
    In Cyclops Lane, the goal's zone, the wizard recalled to a mark set in the Dark Cave at a "door" for Cyclops Lane
    (11:39). Not when the goal's zone is one door from here (`next_door`): out of H1 under Triton Avenue, whose door
    opens on the next goal's zone, the wizard recalled to a mark in Triton Avenue and walked back (21:57). Not when
    the wizard walked here from the mark's zone (`came_from`): it is on its way from the door, and
    the Recall would undo the walk. Triton Avenue's door to the underwater zone was marked for the instance below
    it, and the wizard, through the door, recalled back to Triton at once (19:09:58)."""
    if next_door:
        return False
    return (marked_in is not None and goal_zone in (marked_in, door_for) and here not in (marked_in, goal_zone)
            and came_from != marked_in and isinstance(mana, int) and mana >= RECALL_MANA_NEEDED)


PARK_AFTER_STRATEGIES = 3
HEAVY_FIGHT_FRACTION = 0.35
HEAVY_ZONE_FIGHTS = 2


def short_for_a_heavy_zone(health: float | None, heavy_fights_there: int) -> bool:
    """Under RECHARGE_HEALTH_FRACTION of health for a zone with HEAVY_ZONE_FIGHTS heavy fights or more: there pairs
    walk in on every walk, and each fight cost 39 to 59% of the wizard's health in Triton's underwater zone; the
    wizard walked on at 46% and lost (19:02), and came out of an instance into it at 59% (19:45). The coordinator,
    2026-10-28 23:46 UTC: refill to 90% before walking on there, or before stepping out of an instance into it."""
    return health is not None and heavy_fights_there >= HEAVY_ZONE_FIGHTS and health < RECHARGE_HEALTH_FRACTION


NOT_A_MOVE = ("battle", "settled after arriving", "waited for loading", "dialog", "deck", "gear",
              "pressed OK", "could not equip")


def acted_after_battle(did: str | None) -> bool:
    """A turn that moved the wizard or sent it somewhere (a walk, a travel button, a door), as opposed to settling,
    reading a dialog or checking gear: what the timeline after a battle waits for."""
    return isinstance(did, str) and not did.startswith(NOT_A_MOVE)


def short_for_an_instance_goal(goal_zone: str | None, mana: float | None, dungeons: list[str] = ()) -> bool:
    """The goal is in an instance (`is_an_instance`, or a zone behind a dungeon-entry box) and mana is under
    RECHARGE_MANA_FRACTION, which its door asks for (`short_before_entering`): top up where it is safe before setting
    off, not at the door. From the Commons at 67, then 52, then 47 of 98 mana, the wizard Recalled to Curfew!'s
    instance door, where the door sent it home for mana, 10 mana a round trip in Mark and Recall (20:54 to 21:01)."""
    return ((is_an_instance(goal_zone) or goal_zone in dungeons) and mana is not None
            and mana < RECHARGE_MANA_FRACTION)


def heavy_zone_on_the_way(here: str | None, ways: list[str | None], heavy_fights: dict[str, int],
                          zones_with_enemies: list[str]) -> str | None:
    """The first of `ways` (the goal's zone, the zone the goal was last entered from, the zone a Recall lands in)
    other than `here` that has enemies and HEAVY_ZONE_FIGHTS heavy fights or more, else None. "We Need to Talk"'s
    goal was in Curfew!'s instance, whose own zone had seen no heavy fight, so the wizard Recalled from the Commons at
    75% into Triton's underwater zone outside it (20:46)."""
    for way in ways:
        if way and way != here and way in zones_with_enemies and heavy_fights.get(way, 0) >= HEAVY_ZONE_FIGHTS:
            return way
    return None


def heavy_fight(health_before, health_after, max_health) -> bool:
    """A won fight that cost HEAVY_FIGHT_FRACTION of the wizard's health or more: in Colossus Boulevard pairs of Evil
    Snowmen and Gobbler Scouters cost 400 to 900 of 1,133, and two of three fights went under 25% (12:39 to 12:53)."""
    return (all(isinstance(value, int) for value in (health_before, health_after, max_health)) and max_health > 0
            and health_before - health_after >= HEAVY_FIGHT_FRACTION * max_health)


GOAL_PUSH_DISTANCE = 3500.0
GOAL_PUSH_HEALTH_FRACTION = 0.5
GOAL_HEADWAY = 1000.0
STALLED_TRIPS_TO_PARK = 2


def made_headway(distance_to_goal: float | None, at_last_trip: float | None) -> bool:
    """Since the last refill trip for this goal, the wizard came GOAL_HEADWAY nearer it, or there is nothing to
    compare. The Gravulum Order's bounty lay about 6,800 from the Colossus Boulevard mark, and every Recall there
    landed in a Snowman fight that sent the wizard back to the Commons from the same spot (15:56 to 16:04)."""
    return distance_to_goal is None or at_last_trip is None or distance_to_goal <= at_last_trip - GOAL_HEADWAY


ENTER_ACTION = "enter"
INSTANCE_NAME = re.compile(r"_T\d+$|tower|dungeon", re.IGNORECASE)


def is_an_instance(zone: str | None) -> bool:
    """A zone named as a tower or instance the wizard does not walk out of partway: "..._T1", "...Tower...",
    "...Dungeon..." (its last part)."""
    return bool(zone) and bool(INSTANCE_NAME.search(zone.rsplit("/", 1)[-1]))


def short_before_entering(action: str | None, health: float | None, mana: float | None,
                          destination: str | None = None, dungeons: list[str] = ()) -> str | None:
    """Before pressing X at a "to Enter" door, "health" or "mana" when the wizard should refill first, health first;
    None otherwise or for other prompts. A door known to open on an instance (`destination`, from the doors learned
    walking, `is_an_instance`) asks for a full recharge (RECHARGE_HEALTH_FRACTION, RECHARGE_MANA_FRACTION): Triton
    Avenue's underwater "Odd Tidings" waypoint was the door of WC_Triton_Underwater_T1, entered at 45% health after a
    costly fight, and health does not come back inside (18:40 to 18:42). A door known to open elsewhere (a shop, a
    house) asks for nothing; a door not known yet, only that the wizard not be low (HEALTH_TO_TRAVEL_FRACTION,
    MANA_BELOW_FRACTION), so shops and houses do not cost a trip to the Commons."""
    if (action or "").strip().lower() != ENTER_ACTION:
        return None
    if destination is not None and not is_an_instance(destination) and destination not in dungeons:
        return None
    health_bar, mana_bar = ((RECHARGE_HEALTH_FRACTION, RECHARGE_MANA_FRACTION) if destination is not None
                            else (HEALTH_TO_TRAVEL_FRACTION, MANA_BELOW_FRACTION))
    if health is not None and health < health_bar:
        return "health"
    if mana is not None and mana < mana_bar:
        return "mana"
    return None


def worth_pushing_on(health: float | None, distance_to_goal: float | None, *, stalled: bool = False) -> bool:
    """After a heavy fight, the goal is within GOAL_PUSH_DISTANCE and the wizard has GOAL_PUSH_HEALTH_FRACTION of
    its health or more: go on to the goal rather than refill first. On Colossus Boulevard every fight cost more than
    a third of the wizard's health, so each was followed by a Commons trip and a Recall that landed in the next fight
    at the same mark, about 3,000 from the quest object, and the wizard made no headway for half an hour (15:00 to
    15:34). A defeat on the way costs about what a refill trip does: the wizard wakes in the Commons and Recalls.
    When the last refill trip made no headway (`made_headway`), at any distance: the coordinator, 2026-10-28, of
    the Gravulum Order's bounty."""
    return (health is not None and distance_to_goal is not None and health >= GOAL_PUSH_HEALTH_FRACTION
            and (stalled or distance_to_goal <= GOAL_PUSH_DISTANCE))


MARK_AT_DOOR_REACH = 1500.0
MARK_AT_DOOR_RADIUS = 150.0


def walk_to_mark_at_the_door(here, door, enemies: list) -> bool:
    """Before a refill trip from a zone where fights are heavy, with the goal behind a door (a house, an instance, a
    dungeon): walk to that door and mark there instead of where the fight ended, when the door is farther than
    MARK_AT_DOOR_RADIUS (else mark here: it is the door) and within MARK_AT_DOOR_REACH, and no enemy stands within
    ENEMY_PATH_CLEARANCE of the straight walk. A fight's spot is where patrols cross: Recalls to marks set 2 to 9 s
    after a fight in Triton's underwater zone landed in the next fight within 2 to 12 s (20:48, 21:10). At the door,
    the Recall is followed by X before a patrol closes."""
    distance = flat_distance(here, door)
    if distance <= MARK_AT_DOOR_RADIUS or distance > MARK_AT_DOOR_REACH:
        return False
    return all(distance_to_path(enemy, [here, door]) > ENEMY_PATH_CLEARANCE for enemy in enemies)


HOUSE_DOOR_DISTANCE = 1000.0
GO_IN_FIRST_HEALTH_FRACTION = 0.6
INTERIOR_PART = "/Interiors/"


def worth_going_in_first(health: float | None, door_distance: float | None, goal_zone: str | None,
                         dungeons: list[str] = ()) -> bool:
    """The goal is in an interior that is not an instance (a house, a shop), its door (the quest arrow) is within
    HOUSE_DOOR_DISTANCE, and the wizard has GO_IN_FIRST_HEALTH_FRACTION of its health: go in before refilling, and
    refill after. Inside, nothing attacks; outside, the refill trip costs a Mark and a Recall (about 10 mana) and
    minutes of wisp walking. At 830 of 1195 by H1's door under Triton Avenue, for a talk inside, the wizard went home
    for health first (21:07). Instances keep the full refill: health does not come back inside them."""
    return (health is not None and door_distance is not None and isinstance(goal_zone, str)
            and INTERIOR_PART in goal_zone and not is_an_instance(goal_zone) and goal_zone not in dungeons
            and door_distance <= HOUSE_DOOR_DISTANCE and health >= GO_IN_FIRST_HEALTH_FRACTION)


def parked(parked_quests: dict[str, int], title: str | None, level, held: dict[str, str] | None = None) -> bool:
    """A quest parked while clearing a world (its fight lost with PARK_AFTER_STRATEGIES strategies) stays parked
    until the wizard is past the level it was parked at; a held one (`held`, title to reason) stays parked whatever
    the level. The operator, 2026-10-28 20:21 UTC: "We will continue parked quests after the API from wizard404 is
    connected"."""
    name = " ".join(title.split()) if title else None
    if name and held and name in held:
        return True
    parked_at = parked_quests.get(name) if name else None
    return parked_at is not None and (not isinstance(level, int) or level <= parked_at)


def on_a_refill_trip(here: str | None, marked_in: str | None, *, dungeon_here: bool, enemies_here: bool) -> bool:
    """The wizard is still out on a refill trip from the mark in `marked_in`: elsewhere, and somewhere to refill, not a
    dungeon nor a zone with enemies. Back in Curfew!'s instance by another Recall, with the trip's mark still set, the
    wizard searched the instance for mana wisps it does not have and stood there for mana that does not come back
    (19:40)."""
    return marked_in is not None and here != marked_in and not dungeon_here and not enemies_here


def ready_to_recall(mana: float | None, health: float | None) -> bool:
    """After a trip to the Commons for a refill: mana at least RECALL_MANA_FRACTION and health at least
    RECALL_HEALTH_FRACTION of their pools, or unknown. Recall costs about 5 mana, and the fights it returns to
    are the ones that sent the wizard away."""
    return ((mana is None or mana >= RECALL_MANA_FRACTION) and (health is None or health >= RECALL_HEALTH_FRACTION))


def topped_up(mana: float | None) -> bool:
    """Mana is at least TOP_UP_MANA_FRACTION of the pool, or unknown. Waiting for mana goes on until then, not just
    to ENGAGE_MANA_FRACTION: the zones that give mana back are a walk from the fights, and a Warhorn fight took 6
    to 10 of 30."""
    return mana is None or mana >= TOP_UP_MANA_FRACTION


def short_for_a_fight(health: float | None, mana: float | None) -> str | None:
    """"health" or "mana", whichever is too low for a fight the quest asks for, else None. Health comes first: a
    fight at 1 health is lost in a round whatever the mana, and a health wisp gives about a quarter of it back."""
    if not health_for_a_fight(health):
        return "health"
    if not mana_for_a_fight(mana):
        return "mana"
    return None


def should_drink_potion(fraction: float | None, charges) -> bool:
    """Below POTION_BELOW_FRACTION with a full charge left. Potions are scarce, so a merely tired wizard rests."""
    return (fraction is not None and fraction < POTION_BELOW_FRACTION
            and isinstance(charges, (int, float)) and not isinstance(charges, bool) and charges >= 1)


def travel_outcome(did: str, stop_reason: str | None, moved: float, record: RunRecord, *,
                   new_obstacles: int = 0, **details) -> dict:
    """`stop_reason` is why the walk ended early, or None. Waiting for an enemy to clear the path counts
    as progress for a few stops in a row, no more; waiting for another player's fight to end, which leaves the
    only way unwalkable, counts for `max_duel_waits_in_a_row` stops. Finding new obstacles is progress, because
    the next route goes around them; `remember_obstacles` caps how many a zone may collect."""
    waiting_for_the_path = (stop_reason in PATH_THREATS and record.immobile_threat_stops_in_a_row
                            <= record.limits.max_immobile_threat_stops_in_a_row)
    waiting_for_a_duel = (stop_reason == DUEL_BLOCKS_THE_WAY
                          and record.duel_waits_in_a_row <= record.limits.max_duel_waits_in_a_row)
    if (moved >= MEANINGFUL_TRAVEL_DISTANCE or stop_reason in STATE_CHANGING_INTERRUPTS or waiting_for_the_path
            or waiting_for_a_duel or new_obstacles > 0):
        return progressed(did, new_obstacles=new_obstacles, **details)
    return stalled(did, new_obstacles=new_obstacles, **details)


TURN_FAILED = "turn failed"


def nav_did_better(attempts: list[dict]) -> bool:
    """A trip where the collision route got stuck on the way and the nav route then walked on: the collision
    data misses something there. A collision walk that failed because a turn would not settle ("turn failed:
    facing did not converge") says nothing about the data: in the Commons it made the hub a nav-first zone, and
    the nav route from the Nightside gate's arrival point began with the gate's own waypoint, so the wizard
    walked back through it, six times, until the run stopped."""
    results = {attempt["method"]: attempt.get("result") for attempt in attempts}
    collision_reason = next((attempt.get("reason") or "" for attempt in attempts if attempt["method"] == COLLISION), "")
    return (results.get(COLLISION) == "failed" and results.get(NAV) in ("arrived", "interrupted")
            and not collision_reason.startswith(TURN_FAILED))


def remember_obstacles(record: RunRecord, zone: str, found: list) -> int:
    """Keep newly found obstacles for the zone, up to Limits.max_obstacles_per_zone. Returns how many were kept."""
    known = record.obstacles.setdefault(zone, [])
    room = max(0, record.limits.max_obstacles_per_zone - len(known))
    kept = [(round(x), round(y)) for x, y in found[:room]]
    known.extend(kept)
    return len(kept)


OBSTACLE_FORGET_RADIUS = 600.0


def forget_obstacles_near(record: RunRecord, zone: str, point, radius: float = OBSTACLE_FORGET_RADIUS) -> int:
    """Drop the obstacles learned this run within `radius` of `point` in the zone; how many were dropped. In the
    Shopping District, cells learned near the wizard left every route method without a way for two minutes, and a
    restart, which forgets them, walked on at once (16:54 to 16:58)."""
    known = record.obstacles.get(zone, [])
    kept = [cell for cell in known if (cell[0] - point[0]) ** 2 + (cell[1] - point[1]) ** 2 > radius ** 2]
    record.obstacles[zone] = kept
    return len(known) - len(kept)


class PlannedRoute:
    """How close each enemy was expected to come to a route when walking it began, given where it was heading.
    The planner may accept passing an enemy it could not avoid; only a new enemy, or one now expected to come
    closer, is a threat to stop for.
    Without this, a watcher that stopped for every enemy near the path fought the planner and stood still."""

    def __init__(self):
        self._legs = ()
        self._clearance = {}

    def is_new(self, path_ahead) -> bool:
        legs = tuple(path_ahead[1:])
        return not self._legs or legs != self._legs[len(self._legs) - len(legs):]

    def remember_clearances(self, clearances: dict, path_ahead) -> None:
        """`clearances` maps each enemy's id to its distance from the whole route."""
        self._legs = tuple(path_ahead[1:])
        self._clearance = dict(clearances)

    def threatens(self, enemy_id, distance_now: float) -> bool:
        if distance_now >= ENEMY_PATH_CLEARANCE:
            return False
        planned = self._clearance.get(enemy_id)
        return planned is None or distance_now < planned - APPROACH_MARGIN
