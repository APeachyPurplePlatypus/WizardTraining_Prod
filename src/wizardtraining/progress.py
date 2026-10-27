"""Bookkeeping for a quest run: what each turn did, whether it was progress, and when to stop.
No game access, so it is tested offline.

A turn is progress only if something really changed: the wizard moved a meaningful distance, or a
battle, dialog, zone load or arrival interrupted the walk. Counting "arrived where it already stood"
as progress once kept a run looping for 200 turns.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field

ENEMY_NEAR_PATH = "an enemy is near the path ahead"
DUEL_NEAR_PATH = "a duel is near the path ahead"
PATH_THREATS = {ENEMY_NEAR_PATH, DUEL_NEAR_PATH}
STATE_CHANGING_INTERRUPTS = {"battle", "dialog", "loading", "target in reach", "arrived"}
MEANINGFUL_TRAVEL_DISTANCE = 300.0
ENEMY_PATH_CLEARANCE = 500.0
APPROACH_MARGIN = 150.0
REST_BELOW_FRACTION = 0.65
POTION_BELOW_FRACTION = 0.4


class StopRun(Exception):
    """Ends the run. The message is the reason given in the report."""


@dataclass
class Limits:
    target_level: int = 5
    minutes: float = 25.0
    max_turns: int = 200
    max_battles: int = 20
    max_turns_without_progress: int = 4
    max_step_aways: int = 40
    max_defeats: int = 0
    max_loading_waits_in_a_row: int = 40
    max_immobile_threat_stops_in_a_row: int = 8
    max_obstacles_per_zone: int = 40
    max_zone_changes_without_quest_change: int = 10
    max_menu_choices_without_quest_change: int = 3


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
    step_aways: list = field(default_factory=list)
    battle_log: list[dict] = field(default_factory=list)
    dialog_log: list[dict] = field(default_factory=list)
    zones_without_regeneration: list[str] = field(default_factory=list)
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

    def record_turn(self, turn: dict) -> None:
        self.turns.append(turn)
        self.turns_without_progress = 0 if turn["progress"] else self.turns_without_progress + 1

    def note_place(self, zone, quest_goal) -> None:
        """Count zone changes since the quest goal last changed. Doors count as progress, so a wizard
        walking back and forth through the same doors would otherwise never trip a limit."""
        if self.last_place is not None:
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
        raise StopRun("time limit reached")
    if len(record.turns) >= limits.max_turns:
        raise StopRun("turn limit reached")
    if record.battles >= limits.max_battles:
        raise StopRun("battle limit reached")
    if record.turns_without_progress >= limits.max_turns_without_progress:
        raise StopRun("several turns without progress")
    if len(record.step_aways) >= limits.max_step_aways:
        raise StopRun("stepped away from enemies too often")
    if record.zone_changes_without_quest_change > limits.max_zone_changes_without_quest_change:
        raise StopRun("changed zones many times without the quest changing; possibly going back and forth through doors")
    if record.menu_choices_without_quest_change > limits.max_menu_choices_without_quest_change:
        raise StopRun("an NPC's menu kept reopening without the quest changing; left for the operator")


def needs_rest(fraction: float | None) -> bool:
    return fraction is not None and fraction < REST_BELOW_FRACTION


def should_drink_potion(fraction: float | None, charges) -> bool:
    """Below POTION_BELOW_FRACTION with a full charge left. Potions are scarce, so a merely tired wizard rests."""
    return (fraction is not None and fraction < POTION_BELOW_FRACTION
            and isinstance(charges, (int, float)) and not isinstance(charges, bool) and charges >= 1)


def travel_outcome(did: str, stop_reason: str | None, moved: float, record: RunRecord, *,
                   new_obstacles: int = 0, **details) -> dict:
    """`stop_reason` is why the walk ended early, or None. Waiting for an enemy to clear the path counts
    as progress for a few stops in a row, no more. Finding new obstacles is progress, because the next
    route goes around them; `remember_obstacles` caps how many a zone may collect."""
    waiting_for_the_path = (stop_reason in PATH_THREATS and record.immobile_threat_stops_in_a_row
                            <= record.limits.max_immobile_threat_stops_in_a_row)
    if (moved >= MEANINGFUL_TRAVEL_DISTANCE or stop_reason in STATE_CHANGING_INTERRUPTS or waiting_for_the_path
            or new_obstacles > 0):
        return progressed(did, new_obstacles=new_obstacles, **details)
    return stalled(did, new_obstacles=new_obstacles, **details)


def remember_obstacles(record: RunRecord, zone: str, found: list) -> int:
    """Keep newly found obstacles for the zone, up to Limits.max_obstacles_per_zone. Returns how many were kept."""
    known = record.obstacles.setdefault(zone, [])
    room = max(0, record.limits.max_obstacles_per_zone - len(known))
    kept = [(round(x), round(y)) for x, y in found[:room]]
    known.extend(kept)
    return len(kept)


class PlannedRoute:
    """How close each enemy was to a route when walking it began. The planner may accept passing an enemy
    it could not avoid; only a new enemy, or one that has come closer since, is a threat to stop for.
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
