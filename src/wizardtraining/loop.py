"""Play main quests up to a target level, within time, turn and battle limits.

Each turn reads the game state and does one thing:
- loading: wait;
- a battle is showing: play it with the combat policy;
- a dialog is open: read it, with any follow-ups;
- health is low: rest where health comes back;
- otherwise the active main quest's first open goal decides, through `goal_handlers()`. A goal in
  another zone goes through its door first.

Anything else stops the run for the operator, with the reason in the report: a non-main active quest,
an unknown goal type, an offer the offer policy will not handle, a defeat, ignored keys, turns without
progress, or a limit. To add a goal type, subclass `QuestLoop` and extend `goal_handlers()`.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from dataclasses import replace
from functools import partial

from wizwalker import XYZ, Keycode

from .combat import approach, fight, fled_in
from .config import Settings
from .dialog import (DIALOG_FINISHED, FOLLOW_UP_WAIT_SECONDS, NPC_ARRIVE_DISTANCE, OBJECT_USE_DISTANCE, OFFER_LEFT_FOR_OPERATOR,
                     TALK_KEY_SECONDS, choose_service, close_enough, dialog_open, leave_services, near_npc, read_conversation, service_options,
                     services_open, talk, use_object, wait_for_dialog)
from .decks import (ADD, EXTRACT, KEEP, NO_CAPACITY_KNOWN, REMOVE, DeckChange, DeckLog, change_text, deck_spell,
                    first_missing, plan_changes, role_of, wanted_deck)
from .deckpage import (REFUSED, DeckEditStopped, add_copy, close_book, open_deck_page, read_deck_page,
                       take_out_copy)
from .doors import CHANGE_START_SECONDS, change_begins, push_through
from .photomancy import BOX_SHOWN, NOT_IN_FRAME, PHOTO_ITEM, PHOTO_OF, TOOK, take_photo
from .entities import (display_code, objects_named, HEALTH_WISP, MANA_WISP, dungeon_entrance_near, nearby_enemies, nearest_npc, step_away,
                       surroundings, wisps)
from .equipment import count_items, equip, read_experience, read_items, read_wizard
from .experience import progress_text, xp_gained, xp_to_reach
from .events import (EventLog, describe_battle, describe_changes, describe_round, dialog_text, enemies_at_once,
                     enemy_names, health_text, threat_text)
from .gear import describe_stats, upgrades
from .gametravel import RECALL_NOT_REACHED, go_home_ready, go_to_the_commons, has_mark, mark_here, recall, recall_ready, recall_tip
from .geometry import Point, distance_to_path, flat_distance, path_within, xy
from .keys import tap
from .knowledge import Knowledge
from .motion import WALK_UNITS_PER_SECOND, ApproachLog, MotionTracker, closest_approach
from .movement import LOADING, KeysIgnored, Reroute, face, travel
from .navigation import load_planner
from .policy import LEAVE_MENU, CombatPolicy, MainQuestsOnly, OfferPolicy, SpellTypePolicy, biggest_hits
from .progress import (DUEL_BLOCKS_THE_WAY, DUEL_NEAR_PATH, ENEMIES_IN_THE_WAY, ENEMY_NEAR_PATH, LimitReached, Limits, PATH_THREATS,
                       PlannedRoute, RunRecord, StopRun, check_limits, leaves_world, health_to_travel, mana_for_a_fight, mana_to_travel, still_to_recharge, worth_marking, worth_recalling,
                       PARK_AFTER_STRATEGIES, HEAVY_ZONE_FIGHTS, RECALL_MANA_NEEDED, RECHARGE_HEALTH_FRACTION, heavy_fight, parked, worth_pushing_on, made_headway, GOAL_HEADWAY, STALLED_TRIPS_TO_PARK,
                       nav_did_better, progressed, ready_to_recall, remember_obstacles, safe_to_stand, short_for_a_fight,
                       should_drink_potion, stalled, topped_up, travel_outcome, wanted_wisp,
                       WISP_ANY_DIRECTION_BELOW_FRACTION, world_of)
from .questbook import journal_zones, same_title, activate_quest
from .quests import arrow_shows_no_target, game_language, open_goals, read_quest_arrow, read_quests
from .reports import plain, save_report
from .patrols import VIEWS_TO_JUDGE, note_sightings, unwalked_paths
from .routes import (HIDDEN_DOOR_RADIUS, GapStep, Hazards, RoutePlanner, add_hidden_door, duel_clearance,
                     hidden_door_centre, hidden_doors_to_keep_out_of)
from .sidequests import (FINDER_SAME_GIVER_LIMIT, QUEST_FINDER, WORLD_DOOR, WORLD_DOOR_ROOMS, finder_points_into,
                         in_world, leads_to_the_world_door, next_quest_in_world, unsupported_reason)
from .strategies import (COMBAT_STRATEGIES, CROWD_STRATEGIES, NO_CLOSER_SECONDS, CombatStrategy, GoalApproach,
                         fight_situation, next_combat_strategy, next_walk_strategy)
from .travelplan import (GO_HOME, HUBS, RECALL, TRAVEL_MANA_RESERVE, WALK, TravelCosts, choose_travel, link_zones,
                         zone_hops,
                         spare_mana,
                         worth_a_way_back_mark, worth_going_home_for_wisps)
from .screen import or_default, prompt_action, prompt_is_not_a_doors, prompt_offers_talk
from .spellbook import SpellCatalog, deck_spells, learned_spell_ids, load_level_table
from .spells import KNOWN_AT_FIRST_CHECK, LEARNED, SpellLog, learned_text, newly_learned, spell_entry
from .session import NoClient, attached, hooks_ready
from .state import attempt, battle_showing, free_to_move, health_fraction, mana_fraction, snapshot
from .placed import gate_toward, objects_for_goal
from .targets import (area_in_zone, essence_enemy, fought_in, found_in, is_essence, is_reagent, looks_like_a_reagent, worth_a_detour, zones_to_search_for, bystanders, enemies_to_route_around, in_grace_after_battle, keeps_blocking,
                      leads_to_another_zone, named_enemies_not_in_a_duel, next_area_to_explore, others, quest_targets,
                      refill_reach, safe_wisps,
                      summary, too_close, WISP_REACH)
from .teleports import LEFT_ZONE, NO_EFFECT, TeleportVolume, describe_outcome, volume_at
from .trainer import OPENED_DIALOG, OPENED_MENU, close_training, learn_free_spells, open_training, open_with_professor
from .training import (COMMONS, GATE, SCHOOLS, TRAINER, School, in_dungeon, in_tower, travel_buttons_allowed, spells_to_learn, way_to_school, way_toward_zone,
                       zone_for_area)
from .worldgate import go_to_world, leave_the_map, spiral_map_open
from .ui import POTION_BUTTON, answer_known_popup, click, interact_prompt_text, message_box, visible_children

TARGET_REACH = 1200.0
ARROW_ARRIVE_RADIUS = 250.0
WAYPOINT_ARRIVE_RADIUS = 150.0
PROMPT_DOOR_REACH = 2500.0
NPC_PROMPT_RANGE = 400.0
NOT_A_DOOR_RADIUS = 600.0
ENTRANCE_ARRIVE_RADIUS = 80.0
INTERACT_PROMPT = "interact prompt"
LOADING_WAIT_SECONDS = 3.0
DOOR_WAIT_SECONDS = 15.0
MAX_PROFESSOR_DIALOGS = 2
DOOR_POLL_SECONDS = 0.5
WATCHED_PATH_LENGTH = 2000.0
MIN_SECONDS_BETWEEN_REROUTES = 0.3
PATH_SAMPLE_SECONDS = 1.0
GAP_EDGE_RADIUS = 80.0
GAP_OVERSHOOT = 120.0
SPELL_CHECK_SECONDS = 60.0
BARELY_MOVED_DISTANCE = 100.0
ENEMY_PASS_WAIT_SECONDS = 1.5
ARRIVAL_SETTLE_SECONDS = 1.5
SETTLE_LOOK_SECONDS = 0.25
NEAREST_ENEMIES_NOTED = 3
EXIT_WORD = "exit"
INTERIOR_WORD = "/Interiors/"
FIGHT_GOALS = ("bounty", "bountycollect")
WISP_RESPAWN_SECONDS = 180.0
FINISH_SAFELY_MINUTES = 15.0
MANA_WAIT_SECONDS = 90.0
MANA_WAIT_POLL_SECONDS = 10.0
ENEMIES_IN_THE_WAY_WAIT_SECONDS = 4.0
DUEL_WAIT_SECONDS = 30.0
MAX_ACTIVATIONS_PER_QUEST = 2
FULL_HEALTH_FRACTION = 0.95
WAIT_FOR_THE_WAY_SECONDS = 30.0
MARK_MANA_NEEDED = 8
TELEPORT_LOAD_LIMIT_SECONDS = 60.0
DEFEAT_ARRIVAL_SECONDS = 30.0
ZONE_SAMPLE_SECONDS = (15.0, 180.0)
WALK_SAMPLE_MOVED = 1500.0
MAX_TELEPORTS_PER_GOAL = 2
GATHER_SETTLE_SECONDS = 3.0
REAGENT_ZONES_PER_TRY = 3
DECK_RETRY_SECONDS = 60.0
PHOTO_TRIES = 2
RECALL_WAIT_CAP_SECONDS = 180.0
SEARCH_WALKS_BEFORE_STANDING = 3
SEARCH_POINT_FAILURES_TO_DROP = 2
PHOTO_DISTANCE = 600.0
PHOTO_SUBJECT_TRIES = 4
DECK_EDIT_CLEARANCE = 3000.0
GATHERED_FORGET_SECONDS = 120.0
BOX_CLOSE_WAIT_SECONDS = 10.0
LOAD_STUCK_SECONDS = 60.0
BOX_CLOSE_POLL_SECONDS = 0.5
WAY_BACK, AFTER_A_DEFEAT, FOR_A_REFILL = "way back", "after a defeat", "refill"
FEW_PLACES_TO_LOOK = 2
DUEL_WAIT_POLL_SECONDS = 3.0
DEFEATED_HEALTH_FRACTION = 0.05
NOT_FREE_TO_MOVE_WAIT_SECONDS = 3.0
POTION_SETTLE_SECONDS = 3.0
WISP_ARRIVE_RADIUS = 40.0
WISP_SETTLE_SECONDS = 1.5
TELEPORT_WAIT_SECONDS = 8.0
TELEPORT_POLL_SECONDS = 0.25
JUMP_DISTANCE = 500.0
LET_PASS_SECONDS = 8.0
LET_PASS_POLL_SECONDS = 0.25
TELEPORTED = "teleported"
TELEPORT_CONFIRM_SECONDS = 2.0
KEYS_IGNORED = ("the game ignored a turn key while free to move; a popup (such as the Endorse Wizard window) "
                "may be holding the keyboard; left for the operator")

log = logging.getLogger(__name__)


def reached_its_point(turn: dict) -> bool:
    """A travel turn whose walk arrived where it was going, whatever the distance."""
    return turn.get("trip", {}).get("result") == "arrived"


class QuestLoop:
    def __init__(self, client, settings: Settings, record: RunRecord, *,
                 combat_policy: CombatPolicy, offer_policy: OfferPolicy, events: EventLog | None = None,
                 use_potions: bool = False, wear_gear: bool = False, use_travel_buttons: bool = False,
                 leave_dungeons: bool = False, edit_deck: bool = False):
        self.client = client
        self.leave_dungeons = leave_dungeons
        self.edit_deck = edit_deck
        self.deck_log = DeckLog(settings.runtime_folder)
        self._deck_checked: tuple | None = None
        self._deck_retry_at = 0.0
        self._photos_taken = 0
        self._trip_stat: str | None = None
        self._trip_started = 0.0
        self._mark_position = None
        self._trip_distances: dict[str, float] = {}
        self._search_point_failures: dict[tuple, int] = {}
        self._stalled_trips: dict[str, int] = {}
        self._level_table: dict[int, int] | None = None
        self._experience: tuple[int, int] | None = None
        self._run_start_experience: tuple[int, int] | None = None
        self._run_started_at = time.monotonic()
        self._enemy_names: dict[str, str] = {}
        self.use_potions = use_potions
        self.wear_gear = wear_gear
        self.use_travel_buttons = use_travel_buttons
        self._marked_in: str | None = None
        self._unmarkable: set[str] = set()
        self._no_recall_until = 0.0
        self.travel_costs = TravelCosts.from_dict(record.travel_costs)
        self._teleport_pressed: tuple[str, float] | None = None
        self._defeated_at = 0.0
        self._zone_entered_at: float | None = None
        self._entered_walking = False
        self._entered_from: str | None = None
        self._last_goal: tuple | None = None
        self._last_goal_zone: str | None = None
        self._teleports_for: dict[tuple, int] = {}
        self._travel_planned_for: tuple | None = None
        self._no_teleport_until = 0.0
        self._left_dungeon: tuple[str, int] | None = None
        self._went_home_for_wisps: set[str] = set()
        self._journal_zones: tuple[frozenset, dict] | None = None
        self._finder_givers: dict[tuple, int] = {}
        self._finder_just_activated = False
        self._walking_at: tuple[str, dict] | None = None
        self._reagents_revisited = False
        self._loading_since: float | None = None
        self._gathered: list[tuple[int, float]] = []
        self._dungeons_give_nothing_back = False
        self._refill_fully = False
        self._fight_situation: str | None = None
        if isinstance(combat_policy, SpellTypePolicy):
            combat_policy.strategy_for = self.strategy_against
            combat_policy.essence_from = self.essence_enemies
            combat_policy.hit_seen = lambda enemy: self.record.enemy_hits.get(enemy)
        self.goal_approach = GoalApproach()
        self._gear_checked: tuple | None = None
        self._finishing_since: float | None = None
        self.approaches = ApproachLog()
        self._sighted_at = 0.0
        self._not_doors: list[tuple[str, tuple[float, float]]] = []
        self._spells_checked_at: float | None = None
        self._spell_catalog: SpellCatalog | None = None
        self._to_learn: list[str] | None = None
        self._training_checked: tuple | None = None
        self._said_last: dict[str, str] = {}
        self._professor_dialogs = 0
        self._quest_areas: dict[str, str] = {}
        self._areas_asked: set[str] = set()
        self._entering_with_x_from: str | None = None
        self.spell_log = SpellLog(settings.runtime_folder)
        self._topping_up_in: str | None = None
        self._potion_failed = False
        self._object_in_use = None
        self._dodges: list[float] = []
        self._battle_ended_at: float | None = None
        self._settled_in: str | None = None
        self.motion = MotionTracker()
        self.events = events or EventLog()
        self._last_state = self._last_quest = None
        self.settings = settings
        self.record = record
        self.limits = record.limits
        self.combat_policy = combat_policy
        self.offer_policy = offer_policy
        self._planners: dict[str, RoutePlanner] = {}

    def goal_handlers(self) -> dict:
        """Goal type to `async handler(arrow, goal) -> turn`. A turn is `progressed(...)` or `stalled(...)`."""
        return {"bounty": self.bounty_turn, "bountycollect": self.bounty_turn, "persona": self.persona_turn,
                "waypoint": self.waypoint_turn, "usage": self.usage_turn}

    async def play(self) -> None:
        """Run turns until something stops the run. Never raises StopRun or ordinary errors: they become
        the report's "stopped" reason."""
        try:
            if not hooks_ready(self.record.hooks or {}):
                raise StopRun("reading hooks not ready")
            self.record.start = start = await snapshot(self.client)
            self.events.emit("run", f"started at level {start['level']} in {start['zone']}, health {health_text(start)}, "
                                    f"gold {start['gold']}; target level {self.limits.target_level}")
            await self.run_turns()
        except StopRun as stop:
            self.record.stopped = str(stop)
        except Exception as exc:
            self.record.stopped = f"error: {type(exc).__name__}: {exc}"
            self.record.traceback = traceback.format_exc()
        except asyncio.CancelledError:
            self.record.stopped = "interrupted"
            raise
        finally:
            await self.record_end_state()
            self.events.emit("run", f"stopped: {self.record.stopped}", turns=len(self.record.turns),
                             battles=self.record.battles)

    async def run_turns(self) -> None:
        deadline = time.monotonic() + self.limits.minutes * 60
        while True:
            state = await snapshot(self.client)
            try:
                if self.record.turns_without_progress >= self.limits.max_turns_without_progress:
                    await self.try_another_walk_strategy(state, f"{self.record.turns_without_progress} turns without "
                                                                "progress")
                check_limits(self.record, seconds_left=deadline - time.monotonic(),
                             stop_requested=self.settings.stop_requested())
                if isinstance(state["level"], int) and state["level"] >= self.limits.target_level:
                    raise LimitReached(f"reached level {state['level']}")
            except LimitReached as reached:
                await self.finish_safely(reached, state)
            started = time.monotonic()
            turn = await self.checked_turn(state)
            turn_seconds = time.monotonic() - started
            quest = self.record.quest or {}
            turn.update(level=state["level"], health=state["health"], zone=state["zone"], position=plain_xy(state),
                        goal=(quest.get("goal"), quest.get("goal_zone")), arrow=plain_xy({"position": quest.get("arrow")}))
            self.record.record_turn(turn)
            self.record.note_place(state["zone"], (quest.get("name"), quest.get("goal_id")))
            await self.check_getting_closer(state, turn, quest, turn_seconds)
            self.learn_walk_speed(turn, turn_seconds)
            await self.check_spells(state)
            await self.check_experience(turn)
            log.info("turn %d: %s (progress=%s, level=%s, health=%s, zone=%s, goal=%s %s)", len(self.record.turns),
                     turn["did"], turn["progress"], state["level"], health_text(state), state["zone"], quest.get("goal"),
                     quest.get("goal_zone") or "")
            self.note_changes(state)

    async def refill_after_heavy_fight_turn(self, state: dict) -> dict | None:
        """After a heavy fight (`progress.heavy_fight`), refill health from wisps to RECHARGE_HEALTH_FRACTION before
        walking on, not only below the travel line: fights there start when pairs walk in. Health only; mana keeps
        its own refills. Not in a dungeon refilled in place, where the wizard does not leave to refill. Kept in
        knowledge.json, so a restart in the middle of the refill finishes it (the coordinator, after a restart in the
        Commons at 50% health would have Recalled at once, 15:26)."""
        zone = state["zone"]
        heavy_zone = self.record.heavy_fights.get(zone, 0) >= HEAVY_ZONE_FIGHTS
        low_mana = isinstance(state["mana"], int) and state["mana"] < TRAVEL_MANA_RESERVE
        if heavy_zone and low_mana and self.use_travel_buttons and self._marked_in is None \
                and self.travel_allowed_in(zone) and (trip := await self.commons_trip_turn("mana", state)) is not None:
            self.events.emit("mana", f"{state['mana']} mana, under the {TRAVEL_MANA_RESERVE} kept for fights, in "
                                     f"{zone}, where fights are heavy: refilling in the Commons first")
            return trip
        fraction = health_fraction(state)
        low_among_enemies = fraction is not None and not health_to_travel(fraction) and zone in self.record.zones_with_enemies
        if not self.record.refill_after_heavy_fight and not low_among_enemies:
            return None
        if fraction is None or fraction >= RECHARGE_HEALTH_FRACTION:
            self.record.refill_after_heavy_fight = False
            return None
        if in_dungeon(zone, self.record.entered_with_x) and not self.travel_allowed_in(zone):
            return None
        distance = await self.distance_to_the_goal_here(zone)
        title = " ".join(((self.record.quest or {}).get("title") or "").split())
        stalled = not made_headway(distance, self._trip_distances.get(title))
        if distance is not None and worth_pushing_on(fraction, distance, stalled=stalled):
            self.record.refill_after_heavy_fight = False
            why = "the last refill trip left from no nearer it" if stalled else "it is in this zone"
            self.events.emit("health", f"{state['health']} of {state['max_health']} health after a heavy fight, and the "
                                       f"goal is {distance:.0f} away and {why}: going on to it before refilling")
            return None
        if await self.safe_here():
            return await self.keep_looking_turn("health", state, await self.planner())
        if ((heavy_zone or low_among_enemies) and self.use_travel_buttons and self._marked_in is None
                and self.travel_allowed_in(zone)):
            self._stalled_trips[title] = self._stalled_trips.get(title, 0) + 1 if stalled else 0
            if self._stalled_trips[title] >= STALLED_TRIPS_TO_PARK and self.record.clearing_world:
                self._stalled_trips.pop(title, None)
                self._trip_distances.pop(title, None)
                return await self.park_the_active_quest(f"{STALLED_TRIPS_TO_PARK} refill trips from {zone} in a row "
                                                        f"left from no {GOAL_HEADWAY:.0f} nearer its goal")
            if distance is not None:
                self._trip_distances[title] = distance
            if stalled:
                self.forget_the_mark_in(zone)
            trip = await self.commons_trip_turn("health", state, mark=not stalled)
            if trip is not None:
                why = (f"{self.record.heavy_fights.get(zone, 0)} heavy fights in {zone}" if heavy_zone else
                       f"{state['health']} of {state['max_health']} health in {zone}, among enemies")
                back = ("then walk back in, since the last trip left from no nearer the goal" if stalled
                        else "then Recall back")
                self.events.emit("health", f"{why}: refilling in the Commons, {back}, rather than looking for wisps "
                                           "among its enemies")
                return trip
        return await self.refill_turn("health", state)

    async def check_experience(self, turn: dict) -> None:
        """After each turn, read the experience (`equipment.read_experience`, no clicks); when it changed, log what the
        turn gave (a fight, a quest's hand-in) and the progress to the next level, with the hourly rate this run and
        the time it puts to the target level. The operator, 2026-10-28: "Can we future out a way to read the XP
        bar ?" """
        now = await read_experience(self.client)
        if now is None:
            return
        if self._level_table is None:
            self._level_table = await asyncio.to_thread(load_level_table)
            self._run_start_experience = now
            self.events.emit("xp", f"{progress_text(*now, self._level_table)}; "
                                   f"{self.to_target_text(now)}", level=now[0], xp=now[1])
        before, self._experience = self._experience, now
        if before is None or before == now:
            return
        if now[0] > before[0] and self.record.heavy_fights:
            self.events.emit("health", f"level {now[0]}: the heavy fights counted by zone are forgotten "
                                       f"({', '.join(sorted(self.record.heavy_fights))})")
            self.record.heavy_fights.clear()
        gained = xp_gained(before, now, self._level_table)
        hours = (time.monotonic() - self._run_started_at) / 3600
        so_far = xp_gained(self._run_start_experience, now, self._level_table) if self._run_start_experience else None
        rate = f"; {so_far / hours:,.0f} XP an hour this run" if so_far and hours > 0.05 else ""
        self.events.emit("xp", f"+{gained if gained is not None else '?'} XP from {turn.get('did')}: "
                               f"{progress_text(*now, self._level_table)}{rate}; {self.to_target_text(now, so_far, hours)}",
                         level=now[0], xp=now[1], gained=gained)

    def to_target_text(self, now: tuple[int, int], so_far: int | None = None, hours: float = 0.0) -> str:
        left = xp_to_reach(*now, self.limits.target_level, self._level_table or {})
        if left is None:
            return f"level {self.limits.target_level}: unknown"
        eta = f", about {left / (so_far / hours):.1f} h at this run's rate" if so_far and hours > 0.05 else ""
        return f"{left:,} XP to level {self.limits.target_level}{eta}"

    async def check_getting_closer(self, state: dict, turn: dict, quest: dict, turn_seconds: float) -> None:
        """For a goal that is not a fight, a walk that gets no closer to the quest arrow for a while is a stall
        (`strategies.GoalApproach`), and another walk strategy is tried, the crowd strategies first: waiting for
        the way to clear, then the Commons and back another way."""
        arrow, position = quest.get("arrow"), state.get("position")
        if not isinstance(arrow, dict) or not isinstance(position, dict) or quest.get("goal") in FIGHT_GOALS:
            return
        key = (state["zone"], quest.get("name"), quest.get("goal_id"))
        distance = flat_distance(XYZ(position["x"], position["y"], 0.0), XYZ(arrow["x"], arrow["y"], 0.0))
        fight_seconds = turn_seconds if turn.get("did") == "battle" else None
        if self.goal_approach.note(key, distance, time.monotonic(), fight_seconds):
            await self.try_another_walk_strategy(
                state, f"no closer to the goal than {self.goal_approach.best:.0f} units ({distance:.0f} now) over "
                       f"{self.goal_approach.fights} fights or {NO_CLOSER_SECONDS / 60:.0f} minutes of walking",
                first=CROWD_STRATEGIES)
            self.goal_approach.restart(time.monotonic())

    async def try_another_walk_strategy(self, state: dict, what_failed: str, first=()) -> None:
        """A walk is not getting there (`what_failed`): take the next walk strategy not yet tried in this zone for this
        goal (`strategies.next_walk_strategy`), say which and why, and count the turns again. When every one has
        been tried here, the run stops for the operator, naming them."""
        quest = self.record.quest or {}
        situation = f"{state['zone']} | {quest.get('title') or quest.get('name')} | {quest.get('goal')}"
        tried = self.record.walk_strategies_tried.setdefault(situation, [])
        available = {"nav graph first", "collision data first", "forget the obstacles here", "wait for the way to clear"}
        if self.travel_allowed_in(state["zone"]):
            available |= {"go to the Commons and come back", "go to the Commons and walk back"}
        choice = next_walk_strategy(tried, available, first)
        if choice is None:
            raise StopRun(f"{what_failed} at {situation}, after trying {', '.join(tried) or 'nothing'}")
        name, why = choice
        tried.append(name)
        self.events.emit("strategy", f"{what_failed} at {situation}; trying '{name}': {why}")
        await self.apply_walk_strategy(name, state)
        self.record.turns_without_progress = 0

    async def apply_walk_strategy(self, name: str, state: dict) -> None:
        zone = state["zone"]
        planner = await self.planner()
        if name == "nav graph first":
            planner.nav_first = True
        elif name == "collision data first":
            planner.nav_first = False
            if zone in self.record.nav_first_zones:
                self.record.nav_first_zones.remove(zone)
        elif name == "forget the obstacles here":
            self.record.obstacles[zone] = []
        elif name == "wait for the way to clear":
            deadline = time.monotonic() + WAIT_FOR_THE_WAY_SECONDS
            while time.monotonic() < deadline and not self.settings.stop_requested():
                await asyncio.sleep(1.0)
        elif name == "go to the Commons and come back":
            await self.commons_trip_turn("mana", state)
        elif name == "go to the Commons and walk back":
            await self.commons_trip_turn("mana", state, mark=False)

    async def check_spells(self, state: dict) -> None:
        """Every SPELL_CHECK_SECONDS, and at once after a level up, compare the learned spells with those known
        before and log each new one (`spells.SpellLog`), with whether it is in the equipped deck, so the deck can
        be changed when a better spell comes. The first check ever lists every spell already known. Reads
        memory only, never clicks, so it runs anywhere the wizard is free to move."""
        now = time.monotonic()
        leveled = self._last_state is not None and state["level"] != self._last_state["level"]
        due = self._spells_checked_at is None or now - self._spells_checked_at >= SPELL_CHECK_SECONDS
        if not (due or leveled) or not free_to_move(state):
            return
        self._spells_checked_at = now
        learned = await or_default(learned_spell_ids(self.client), None)
        if learned is None:
            return
        first = not self.record.known_spells
        new = newly_learned(self.record.known_spells, learned)
        if not new:
            return
        deck = await or_default(deck_spells(self.client), {})
        if self._spell_catalog is None:
            self._spell_catalog = SpellCatalog(game_language())
        for template_id in new:
            spell = await self._spell_catalog.describe(template_id)
            entry = spell_entry(spell, kind=KNOWN_AT_FIRST_CHECK if first else LEARNED, deck=deck,
                                level=state["level"], zone=state["zone"])
            self.spell_log.add(entry)
            if not first:
                self.events.emit("spell", learned_text(spell, deck), spell=entry)
        if first:
            self.events.emit("spell", f"knows {len(new)} spells, {sum(1 for spell in new if spell in deck)} of them "
                                      f"in the equipped deck ({sum(deck.values())} cards); listed in "
                                      f"{self.spell_log.path.name}")
        self.record.known_spells = sorted(set(self.record.known_spells) | set(new))

    def note_changes(self, state: dict) -> None:
        for kind, text in describe_changes(self._last_state, state, self._last_quest, self.record.quest):
            self.events.emit(kind, text)
        arrived = self._last_state is not None and state["zone"] != self._last_state["zone"]
        if arrived and isinstance(state["zone"], str) and self._entering_with_x_from is not None:
            if state["zone"] != self._entering_with_x_from and state["zone"] not in self.record.entered_with_x:
                self.record.entered_with_x.append(state["zone"])
            self._entering_with_x_from = None
        if arrived and isinstance(state["zone"], str) and isinstance(state["position"], dict):
            self.record.arrivals[state["zone"]] = {"from": self._last_state["zone"],
                                                   "position": (state["position"]["x"], state["position"]["y"])}
        if arrived and isinstance(state["zone"], str):
            self.learn_the_way(self._last_state["zone"], state["zone"])
        self._last_state, self._last_quest = state, dict(self.record.quest or {})

    async def box_closes_by_itself(self) -> bool:
        """Wait up to BOX_CLOSE_WAIT_SECONDS for an open message box to close with no click. After Recall could not
        reach a mark in a dungeon, the game showed a box titled "INFO" that closed by itself, but the run had already
        stopped for it, twice (01:12, 01:13)."""
        deadline = time.monotonic() + BOX_CLOSE_WAIT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(BOX_CLOSE_POLL_SECONDS)
            if await message_box(self.client) is None:
                return True
        return False

    async def checked_turn(self, state: dict) -> dict:
        """A turn, after answering known popups. An open message box the framework does not answer takes every
        click, so the run stops for the operator with the box's title (never its text, which can name a player):
        an unanswered friend request kept every card the wizard played out of its battles for over half an hour."""
        if answered := await answer_known_popup(self.client):
            self.events.emit("popup", answered)
            return progressed(answered)
        if (box := await message_box(self.client)) is not None:
            if await self.box_closes_by_itself():
                self.events.emit("popup", f"a message box titled {box.title!r} closed by itself")
                return stalled("waited for a message box to close by itself", title=box.title)
            raise StopRun(f"a message box titled {box.title!r} is open and takes every click; left for the operator")
        try:
            return await self.play_turn(state)
        except KeysIgnored:
            if answered := await answer_known_popup(self.client):
                self.events.emit("popup", f"{answered}; the popup was holding the keyboard")
                return progressed(answered)
            if await self.busy_now():
                return stalled("a turn key was ignored while a dialog or menu was opening")
            if free_to_move(state):
                raise StopRun(KEYS_IGNORED)
            return stalled("a turn key was ignored while busy")

    async def busy_now(self) -> bool:
        """A dialog or NPC menu can open a moment after a turn began, and then it swallows the turn keys."""
        return (await dialog_open(self.client) or await services_open(self.client)
                or not free_to_move(await snapshot(self.client)))

    async def play_turn(self, state: dict) -> dict:
        if state["loading"] is True:
            self._settled_in = None
            self._loading_since = self._loading_since or time.monotonic()
            if time.monotonic() - self._loading_since > LOAD_STUCK_SECONDS:
                raise StopRun(f"a zone load has lasted {time.monotonic() - self._loading_since:.0f} s, likely a lost "
                              "connection to the game's server; left for the operator")
            self.record.loading_waits_in_a_row += 1
            await asyncio.sleep(LOADING_WAIT_SECONDS)
            if self.record.loading_waits_in_a_row > self.limits.max_loading_waits_in_a_row:
                return stalled("waited for loading")
            return progressed("waited for loading")
        self.record.loading_waits_in_a_row = 0
        self._loading_since = None
        if state["zone"] != self._settled_in:
            await self.settle()
            return progressed("settled after arriving")
        if battle_showing(state):
            return await self.battle_turn()
        if await dialog_open(self.client):
            return await self.dialog_turn()
        if await services_open(self.client):
            return await self.services_turn()
        if not free_to_move(state):
            await asyncio.sleep(NOT_FREE_TO_MOVE_WAIT_SECONDS)
            return stalled("waited: not free to move", state=state,
                           windows=await visible_children(self.client, ["WorldView"]))
        if self.wear_gear and (turn := await self.gear_turn()) is not None:
            return turn
        if self.edit_deck and (turn := await self.deck_turn(state)) is not None:
            return turn
        if self._finishing_since is not None and (turn := await self.leave_for_safety_turn(state)) is not None:
            return turn
        if self._finishing_since is None and (turn := await self.training_turn(state)) is not None:
            return turn
        return await self.quest_turn(state)

    async def training_turn(self, state: dict) -> dict | None:
        """The operator's rule for new spells: when the wizard's level allows school spells it does not know
        (`training.spells_to_learn`), and it is not inside a dungeon (`training.in_dungeon`), walk to the school's
        professor and learn them, then go back to the quest at hand. Checked when the level or the zone changes, and
        the school is visited once a level. None when there is nothing to do here, so the quest goes on."""
        zone, level = state["zone"], state["level"]
        if not isinstance(level, int) or level <= self.record.trained_at_level:
            return None
        if self._to_learn is None and (level, zone) != self._training_checked:
            self._training_checked = (level, zone)
            self._to_learn = await self.spells_to_learn_now()
        wizard = await read_wizard(self.client) if self._to_learn else None
        if wizard is None:
            return None
        school, wanted = SCHOOLS[wizard.school], ", ".join(self._to_learn)
        if in_dungeon(zone, self.record.entered_with_x):
            self.say_once("training", f"level {level} allows {wanted}, but the wizard is in a dungeon ({zone}); "
                                      "training waits until it is out")
            return None
        planner = await self.planner()
        way = way_to_school(zone, school, [volume.name for volume, _ in planner.teleports])
        door = None if way is None else self.door_on_the_way(way, planner)
        if door is None and (way is None or way.kind != TRAINER):
            self.events.emit("training", f"no way known from {zone} to {school.professor}; training waits for "
                                         "another zone")
            self._to_learn = None
            return None
        self.say_once("training", f"level {level} allows {wanted}, and the wizard is not in a dungeon: going to "
                                  f"{school.professor} to train, then back to the quest")
        if way.kind == TRAINER:
            return await self.professor_turn(school, level)
        return await self.walk_to_door_turn("walk toward the school to train", *door)

    async def walk_to_door_turn(self, did: str, point, radius: float) -> dict:
        """Walk toward a door of the way to somewhere, and through it once the wizard stands at it."""
        if flat_distance(await self.client.body.position(), point) <= max(WAYPOINT_ARRIVE_RADIUS, radius):
            return await self.zone_door_turn(point)
        return await self.travel_turn(did, point, arrive_radius=WAYPOINT_ARRIVE_RADIUS,
                                      avoid=await nearby_enemies(self.client))

    async def go_to_goal_zone_turn(self, goals: list[dict], here: str) -> dict | None:
        """With no quest arrow: walk one door toward the nearest zone of this world that an open goal names
        (`destination_zone`) and a way is known to. "Find the Smiths" has a "Go To" goal per hidden Smith, one in
        Firecat Alley, one in Colossus Boulevard and so on; the arrow shows nothing outside the goal's zone, and the run
        stopped in the Dark Cave (10:58). None when a goal is here, or no goal's zone can be walked to."""
        zones = {goal.get("destination_zone") for goal in goals} - {None, ""}
        if here in zones:
            return None
        planner = await self.planner()
        names = [volume.name for volume, _ in planner.teleports]
        reachable = []
        for zone in zones:
            if world_of(zone) != world_of(here):
                continue
            way = way_toward_zone(here, zone, names)
            door = None if way is None else self.door_on_the_way(way, planner)
            if door is not None:
                reachable.append((zone_hops(self.record.zone_links, here, zone) or 99, zone, door))
        if not reachable:
            return None
        _, zone, door = min(reachable)
        self.say_once("quest", f"no quest arrow; an open goal is in {zone}: going there")
        return await self.walk_to_door_turn(f"walk toward {zone} for the quest", *door)

    async def go_to_quest_area_turn(self, quest: dict, goals: list[dict]) -> dict | None:
        """A quest whose goals show no arrow can be in another zone than the wizard's: the quest page names its
        area ("Cyclops Lane", `questbook.Activation.area`). When that zone is known (`training.zone_for_area`) and is
        not this one, and no open goal's target is in sight here, walk one door of the way there
        (`training.way_toward_zone`). None when the area is unknown, is this zone, no way is known, or a goal's
        target can be found here."""
        zone = await self.client.zone_name()
        title = quest.get("title")
        if title and title not in self._quest_areas and title not in self._areas_asked:
            self._areas_asked.add(title)
            if area := (await activate_quest(self.client, title, click_activate=False)).area:
                self._quest_areas[title] = area
        target = zone_for_area(self._quest_areas.get(title))
        if target is None or target == zone:
            return None
        for goal in goals:
            if await self.target_without_arrow(goal) is not None:
                return None
        planner = await self.planner()
        way = way_toward_zone(zone, target, [volume.name for volume, _ in planner.teleports])
        door = None if way is None else self.door_on_the_way(way, planner)
        if door is None:
            self.say_once("quest", f"{quest.get('title')} is in {target}, and no way there is known from {zone}")
            return None
        self.say_once("quest", f"{quest.get('title')} is in {target}: walking there by way of {way.name}")
        return await self.walk_to_door_turn(f"walk toward {target} for a quest", *door)

    def door_on_the_way(self, way, planner: RoutePlanner) -> tuple[XYZ, float] | None:
        """Where the next door of `way` is in this zone, and its radius: a gate toward the zone it names, or the
        teleport volume it names."""
        if way.kind == GATE:
            gate = gate_toward(planner.placed_objects, way.name)
            return None if gate is None else (XYZ(gate.x, gate.y, gate.z), 0.0)
        volume = next((volume for volume, _ in planner.teleports if volume.name == way.name), None)
        return None if volume is None else (XYZ(volume.x, volume.y, volume.z), volume.radius)

    def say_once(self, kind: str, text: str) -> None:
        """Emit `text` unless it was the last thing said this way, so a turn repeated while walking says it once."""
        if self._said_last.get(kind) != text:
            self._said_last[kind] = text
            self.events.emit(kind, text)

    async def spells_to_learn_now(self) -> list[str] | None:
        """The school spells the wizard's level allows that it does not know yet, by name (`training`)."""
        wizard = await read_wizard(self.client)
        learned = await or_default(learned_spell_ids(self.client), None)
        if wizard is None or learned is None or wizard.school not in SCHOOLS:
            return None
        if self._spell_catalog is None:
            self._spell_catalog = SpellCatalog(game_language())
        known = [spell.name for spell in [await self._spell_catalog.describe(spell_id) for spell_id in learned]
                 if spell.name]
        return spells_to_learn(wizard.school, wizard.level, known) or None

    async def professor_turn(self, school: School, level: int) -> dict:
        """In the school: walk to its professor, the only NPC there, open the spell training from their menu, learn
        every free spell offered at or below the wizard's level (`trainer`), and close it. A professor who speaks
        first is heard out by the next turns' dialog handling, at most MAX_PROFESSOR_DIALOGS times."""
        professor = await nearest_npc(self.client)
        if professor is None:
            return stalled(f"{school.professor} is not in sight in the school")
        if flat_distance(await self.client.body.position(), professor) > NPC_ARRIVE_DISTANCE:
            return await self.travel_turn(f"walk to {school.professor}", professor, arrive_radius=NPC_ARRIVE_DISTANCE)
        opened = await open_with_professor(self.client, professor)
        if opened == OPENED_DIALOG and self._professor_dialogs < MAX_PROFESSOR_DIALOGS:
            self._professor_dialogs += 1
            return progressed(f"{school.professor} spoke first")
        learned, left = [], []
        try:
            if opened == OPENED_MENU and await open_training(self.client):
                learned, left = await learn_free_spells(self.client, level)
        finally:
            await close_training(self.client)
        self.record.trained_at_level = level
        self._to_learn = None
        self._spells_checked_at = None
        self.events.emit("training", f"learned {', '.join(learned) or 'nothing'} from {school.professor} at level "
                                     f"{level}; next offered: {', '.join(left[:3]) or 'nothing'}; back to the quest")
        return progressed(f"trained with {school.professor}", learned=learned, opened=opened)

    async def no_enemy_within(self, distance: float) -> bool:
        """No enemy loaded within `distance` of the wizard: docs/safety.md allows deck edits "only in a zone with no
        enemy nearby". In Unicorn Way, hunting Lost Souls, the deck's Extract copies would otherwise wait until the
        wizard left the zone."""
        state = await snapshot(self.client)
        if state["loading"] is not False:
            return False
        return all(enemy["distance"] > distance for enemy in await nearby_enemies(self.client))

    async def safe_here(self) -> bool:
        """`progress.safe_to_stand` here, with enemies recognised up to about 4,000 units away. A zone's patrol paths
        do not tell: the Commons, Ravenwood, the Shopping District and Olde Town have them for their friendly NPCs,
        and General Akilles' tower has none, though he stands in it."""
        state = await snapshot(self.client)
        if state["loading"] is not False:
            return False
        return safe_to_stand(state["zone"], self.record.zones_with_enemies, len(await nearby_enemies(self.client)))

    async def finish_safely(self, reached: LimitReached, state: dict) -> None:
        """Stop for a planned limit only where it is safe; until then, play on for up to FINISH_SAFELY_MINUTES.
        A run that stopped in Cyclops Lane left the wizard idle among enemies, and one pulled it into a fight
        (the operator: "ur in a fight because you didnt go to a safe area")."""
        if self._finishing_since is None:
            self._finishing_since = time.monotonic()
            self.events.emit("run", f"{reached}; playing on until in a zone without enemies "
                                    f"(at most {FINISH_SAFELY_MINUTES:g} minutes)")
        if battle_showing(state) or not free_to_move(state):
            return
        if await self.safe_here():
            raise StopRun(f"{reached}, in a zone without enemies")
        if time.monotonic() - self._finishing_since > FINISH_SAFELY_MINUTES * 60:
            raise StopRun(f"{reached}; no zone without enemies reached in {FINISH_SAFELY_MINUTES:g} minutes")

    async def gear_turn(self) -> dict | None:
        """Wear the best gear the wizard has (`gear.upgrades`). Checked again after a level-up or new loot, and only
        where it is safe, with no enemy loaded (`safe_here`), since the spellbook stays open a few seconds per item.
        None when there is nothing to do here, so the turn goes on."""
        if not await self.safe_here():
            return None
        wizard = await read_wizard(self.client)
        count = await attempt(count_items(self.client))
        if wizard is None or not isinstance(count, int) or (wizard.level, count) == self._gear_checked:
            return None
        self._gear_checked = (wizard.level, count)
        items = await read_items(self.client)
        chosen = upgrades(items, wizard)
        if not chosen:
            self.events.emit("gear", f"level {wizard.level}, {len(items)} items: the best wearable gear is on")
            return None
        before = await snapshot(self.client)
        worn = []
        for item in chosen:
            problem = await equip(self.client, item)
            self.events.emit("gear", f"{item.slot}: {item.name} ({describe_stats(item)}): {problem or 'equipped'}")
            if problem is None:
                worn.append(item.name)
        after = await snapshot(self.client)
        self.events.emit("gear", f"max health {before['max_health']} -> {after['max_health']}, max mana "
                                 f"{before['max_mana']} -> {after['max_mana']}")
        return progressed("equipped gear", items=worn) if worn else stalled("could not equip gear")

    async def settle(self) -> None:
        """Wait ARRIVAL_SETTLE_SECONDS after a loading screen or a zone change, until two zone readings a moment
        apart agree. Right after loading the zone once read as the zone just left: the loop walked toward that
        zone's door coordinates inside the Myth school, straight back out through its exit. The wait is spent
        watching the enemies, so the first route out of a door knows where they are heading: with nothing
        observed yet every enemy counted as standing still, and 9 seconds after leaving the Witch's house a
        patrolling Fire Elf walked into the wizard."""
        self.motion.forget()
        self.approaches.forget()
        await self.watch_enemies(ARRIVAL_SETTLE_SECONDS)
        zone = await self.client.zone_name()
        while (again := await self.client.zone_name()) != zone and not self.settings.stop_requested():
            zone = again
            await asyncio.sleep(ARRIVAL_SETTLE_SECONDS)
        self._settled_in = zone

    async def watch_enemies(self, seconds: float) -> None:
        """Note where the loaded enemies are every SETTLE_LOOK_SECONDS for `seconds`, for their velocities."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            enemies = await or_default(nearby_enemies(self.client), None)
            if enemies is not None:
                self.motion.observe(enemies, time.monotonic())
            await asyncio.sleep(SETTLE_LOOK_SECONDS)

    async def battle_turn(self) -> dict:
        self.record.battles += 1
        before = await snapshot(self.client)
        self.saw_enemies(before["zone"])
        started = time.monotonic()
        self.events.emit("battle", f"battle {self.record.battles} started in {before['zone']}, health {health_text(before)}")
        self._fight_situation = None
        if isinstance(self.combat_policy, SpellTypePolicy):
            self.combat_policy.new_fight()
        battle = await fight(self.client, self.combat_policy,
                             on_round=lambda entry: self.events.emit("round", describe_round(entry)))
        self.record.battle_log.append(battle)
        self._battle_ended_at = time.monotonic()
        self.learn_enemy_hits(battle)
        fought_in(self.record.enemy_zones, enemies_at_once(battle.get("rounds", []))[1], before["zone"])
        after = await snapshot(self.client)
        fraction = health_fraction(after)
        fled = bool(battle["rounds"]) and fled_in(battle["rounds"][-1])
        defeated = not fled and (after["zone"] != before["zone"]
                                 or (fraction is not None and fraction <= DEFEATED_HEALTH_FRACTION))
        outcome = ("left for the operator" if "stopped" in battle else "lost" if defeated else "fled" if fled
                   else "won")
        self.events.emit("battle", describe_battle(battle, seconds=time.monotonic() - started, before=before,
                                                   after=after, outcome=outcome), outcome=outcome)
        if "stopped" in battle:
            raise StopRun(battle["stopped"])
        battle["after"] = {key: after[key] for key in ("zone", "level", "health", "max_health", "mana", "gold")}
        if not defeated and not fled and heavy_fight(before["health"], after["health"], after["max_health"]):
            self.record.heavy_fights[before["zone"]] = self.record.heavy_fights.get(before["zone"], 0) + 1
            self.record.refill_after_heavy_fight = True
            self.events.emit("health", f"the fight cost {before['health'] - after['health']} of {after['max_health']} "
                                       f"health; refilling to {RECHARGE_HEALTH_FRACTION:.0%} from wisps before going on")
        if defeated and self.record.clearing_world and self.record.heavy_fights.get(before["zone"], 0) >= HEAVY_ZONE_FIGHTS:
            self.park_the_quest_in_a_heavy_zone(before["zone"], battle)
        if defeated:
            self.record.defeats += 1
            self.record.recharging = True
            self._defeated_at = time.monotonic()
            if self.limits.max_defeats is not None and self.record.defeats > self.limits.max_defeats:
                raise StopRun("defeated in battle; stopping for the operator")
            self.change_combat_strategy(battle)
        casts = sum(1 for battle_round in battle["rounds"] if battle_round["action"].startswith("cast"))
        return progressed("battle", rounds=len(battle["rounds"]), casts=casts, final_phase=battle["final_phase"],
                          after=battle["after"])

    def learn_enemy_hits(self, battle: dict) -> None:
        """Keep the biggest hit seen from each kind of enemy (`policy.biggest_hits`), across runs, for the combat
        policy's estimate of what the enemies could deal next round."""
        for enemy, hit in biggest_hits(battle.get("rounds", [])).items():
            if hit > self.record.enemy_hits.get(enemy, 0):
                self.record.enemy_hits[enemy] = hit
                self.events.emit("knowledge", f"{enemy} hit for up to {hit} so far")

    def park_the_quest_in_a_heavy_zone(self, zone: str, battle: dict) -> None:
        """A fight lost in a zone where HEAVY_ZONE_FIGHTS fights this run cost a third of the wizard's health or more:
        while clearing a world, the quest is parked until the next level, and the world's other quests go first. The
        coordinator, 2026-10-28, of Colossus Boulevard: park its quests until level 14 if a fight is lost there."""
        title = " ".join(((self.record.quest or {}).get("title") or "").split())
        level = (battle.get("after") or {}).get("level")
        if not title or not isinstance(level, int):
            return
        self.record.parked_quests[title] = level
        self.events.emit("strategy", f"lost in {zone}, where {self.record.heavy_fights[zone]} fights cost a third of the "
                                     f"wizard's health or more; parking {title} until past level {level}")

    def strategy_against(self, situation: str) -> CombatStrategy:
        """The first combat strategy not yet lost with against these enemies, in this run or an earlier one
        (`strategies.next_combat_strategy`); asked by the combat policy at a fight's first round."""
        self._fight_situation = situation
        lost_with = self.record.combat_strategies_tried.get(situation, [])
        strategy = next_combat_strategy(lost_with) or COMBAT_STRATEGIES[0]
        if lost_with:
            self.events.emit("strategy", f"against {situation}, lost before with {', '.join(lost_with)}; "
                                         f"playing '{strategy.name}'")
        return strategy

    def park_the_quest_if_lost_too_often(self, situation: str, tried: list[str], battle: dict) -> None:
        """While clearing a world, a quest whose fight was lost with PARK_AFTER_STRATEGIES strategies is parked
        (`progress.parked`) until the wizard levels up: the Quest Finder goes on to other givers, and the quest is
        tried again, with the next strategy, from the next level on. Eyus Maximus, who resists Myth by 40%, beat
        the wizard at level 13 on its first try (01:27)."""
        title = " ".join(((self.record.quest or {}).get("title") or "").split())
        level = (battle.get("after") or {}).get("level")
        if not self.record.clearing_world or not title or len(tried) < PARK_AFTER_STRATEGIES or not isinstance(level, int):
            return
        self.record.parked_quests[title] = level
        self.events.emit("strategy", f"lost to {situation} with {', '.join(tried)}; parking {title} until the wizard "
                                     f"is past level {level}, then trying it again with the next strategy")

    def change_combat_strategy(self, battle: dict) -> None:
        """After a lost fight, the next fight against these enemies plays by the next combat strategy not yet tried
        against them (`strategy_against`), and says which and why. The operator: "There should be no retry limit as
        you should be trying different strategies if something isn't working." When every strategy has lost against
        them, the run stops for the operator."""
        _, names = enemies_at_once(battle.get("rounds", []))
        situation = self._fight_situation or fight_situation(list(names))
        tried = self.record.combat_strategies_tried.setdefault(situation, [])
        current = getattr(self.combat_policy, "strategy", None)
        if current is None:
            raise StopRun(f"lost to {situation}; the combat policy has no strategies to change; left for the operator")
        if current.name not in tried:
            tried.append(current.name)
        self.park_the_quest_if_lost_too_often(situation, tried, battle)
        following = next_combat_strategy(tried)
        if following is None:
            raise StopRun(f"lost to {situation} with every combat strategy ({', '.join(tried)}); left for the operator")
        self._refill_fully = following.refill_fully_first
        self.events.emit("strategy", f"lost to {situation} playing '{current.name}'; the next fight against them "
                                     f"plays '{following.name}': {following.why}")

    async def dialog_turn(self) -> dict:
        record = {}
        result = await read_conversation(self.client, record, self.offer_policy)
        self.record.dialog_log.append(record)
        self.note_dialog(record, result)
        if result == OFFER_LEFT_FOR_OPERATOR:
            raise StopRun(result)
        return progressed("dialog", result=result, pages=len(record["pages"]))

    def note_dialog(self, record: dict, result: str) -> None:
        """Log a conversation with its text. The text goes to the event log only: the report keeps page lengths."""
        offers = [page["offer"] for page in record.get("pages", []) if "offer" in page]
        self.events.emit("dialog", f"{len(record.get('pages', []))} pages, {record.get('follow_ups', 0)} follow-ups"
                                   f"{', offers: ' + ', '.join(offers) if offers else ''}; {result}",
                         text=dialog_text(record.pop("texts", [])))

    async def services_turn(self) -> dict:
        """Pick an option of an NPC's services menu, as the offer policy decides."""
        options = await service_options(self.client)
        labels = [label for label, _ in options]
        active = await self.active_quest()
        self.record.note_menu_choice((active["name_key"], tuple(goal["id"] for goal in open_goals(active)))
                                     if active else None)
        choice = self.offer_policy.choose_service(labels, active_quest=active["title"] if active else None,
                                                  business_here=active is not None and await self.business_here(active))
        if choice is None:
            raise StopRun(f"an NPC's menu offers {labels}, and none is the active quest or an approved title; "
                          "left for the operator (approve one with --approve-quest)")
        if choice == LEAVE_MENU:
            await leave_services(self.client)
            self.events.emit("menu", f"left an NPC's menu offering {labels}")
            return progressed("left an NPC's menu", options=labels)
        await choose_service(self.client, options[choice][1])
        self.events.emit("menu", f"chose {labels[choice]!r} from an NPC's menu offering {labels}")
        return progressed("chose from an NPC's menu", option=labels[choice])

    async def business_here(self, quest: dict) -> bool:
        """The quest's next goal is to talk to the NPC at the arrow, and the wizard is there. Turning a quest in
        is such a goal too. `ready_to_turn_in` is not used: it read true for quests whose goals were all open."""
        goals = open_goals(quest)
        if not goals or goals[0]["type"] != "persona":
            return False
        try:
            return await near_npc(self.client, await read_quest_arrow(self.client, wait_seconds=1.0))
        except Exception:
            return False

    async def wisp_heading(self, wanted: str, state: dict) -> XYZ | None:
        """Where the quest goes next, so that a wisp is fetched only on the way there. None, any direction, for
        mana (sought only when low, and without it the wizard can neither attack nor heal), when health is below
        WISP_ANY_DIRECTION_BELOW_FRACTION, or when the arrow shows no target."""
        health = health_fraction(state)
        if wanted == "mana" or (health is not None and health < WISP_ANY_DIRECTION_BELOW_FRACTION):
            return None
        try:
            arrow = await read_quest_arrow(self.client)
        except Exception:
            return None
        return None if arrow_shows_no_target(arrow) else arrow

    def recently_tried_wisps(self) -> set[str]:
        """Wisps that gave nothing within WISP_RESPAWN_SECONDS: used-up wisps come back, so after that they count
        again, and the wizard can go round a zone's mana wisps when it has nothing else to fight with."""
        now = time.time()
        return {wisp for wisp, tried in self.record.tried_wisps.items() if now - tried < WISP_RESPAWN_SECONDS}

    async def wisp_turn(self, wanted: str, state: dict, heading=None, reach: float = WISP_REACH) -> dict | None:
        """Walk to the nearest safe health or mana wisp on the way to `heading` and touch it. None when there is
        no such wisp, so the quest goes on. A wisp trip that gives nothing, whether it arrived or was cut short,
        is not tried again: used-up wisps still show as entities, and retrying them walked the wizard back and
        forth between them."""
        kind = HEALTH_WISP if wanted == "health" else MANA_WISP
        enemies, circles = await surroundings(self.client)
        candidates = safe_wisps(await wisps(self.client, kind), me=await self.client.body.position(), enemies=enemies,
                                duel_circles=circles, tried=self.recently_tried_wisps(), heading=heading, reach=reach)
        if not candidates:
            return None
        wisp = candidates[0]
        start = await self.client.body.position()
        planner = await self.planner()
        hazards, _ = self.hazards_for(planner, state["zone"], start, wisp["position"], WISP_ARRIVE_RADIUS,
                                      avoid=enemies, duel_circles=circles)
        trip = await travel(self.client, planner, wisp["position"], arrive_radius=WISP_ARRIVE_RADIUS,
                            watch=self.watcher(reroute=self.rerouter(planner, hazards, wisp["position"])),
                            hazards=hazards)
        await asyncio.sleep(WISP_SETTLE_SECONDS)
        after = await snapshot(self.client)
        stat = "health" if wanted == "health" else "mana"
        gained = isinstance(after[stat], int) and isinstance(state[stat], int) and after[stat] > state[stat]
        if not gained:
            self.record.tried_wisps[str(wisp["id"])] = time.time()
        self.events.emit("wisp", f"{kind} {flat_distance(start, wisp['position']):.0f} away: {trip['result']}"
                                 f"{' (' + trip['reason'] + ')' if trip['reason'] else ''}; {stat} {state[stat]} -> "
                                 f"{after[stat]}")
        if gained:
            return progressed(f"picked up a {kind}", before=state[stat], after=after[stat])
        moved = flat_distance(start, await self.client.body.position())
        return travel_outcome(f"walk to a {kind}", trip["reason"], moved, self.record)

    async def potion_turn(self, state: dict) -> dict:
        """Drink a health potion the wizard already has, with a click on the HUD's potion button. Only with
        `use_potions` (the operator's permission); potions are never bought. If health does not rise, the
        button is not tried again this run."""
        charges_before = await attempt(self.client.stats.potion_charge())
        await click(self.client, POTION_BUTTON)
        await asyncio.sleep(POTION_SETTLE_SECONDS)
        after = await snapshot(self.client)
        charges_after = await attempt(self.client.stats.potion_charge())
        self.events.emit("potion", f"drank a health potion: health {state['health']} -> {after['health']} of "
                                   f"{after['max_health']}, mana {state['mana']} -> {after['mana']}, "
                                   f"charges {charges_before} -> {charges_after}")
        if isinstance(after["health"], int) and isinstance(state["health"], int) and after["health"] > state["health"]:
            return progressed("drank a health potion", health_before=state["health"], health=after["health"])
        self._potion_failed = True
        return stalled("clicked the potion button, but health did not rise")

    async def quest_turn(self, state: dict) -> dict:
        fraction = health_fraction(state)
        if self.use_potions and not self._potion_failed:
            if should_drink_potion(fraction, await attempt(self.client.stats.potion_charge())):
                return await self.potion_turn(state)
        if self.use_travel_buttons and self._marked_in is not None:
            if (back := await self.back_from_the_commons_turn(state)) is not None:
                return back
        if self._left_dungeon is not None and self._marked_in is None:
            await self.check_the_dungeon_held(state)
        if (detour := await self.reagent_detour_turn(state)) is not None:
            return detour
        if (refill := await self.refill_after_heavy_fight_turn(state)) is not None:
            return refill
        wanted = wanted_wisp(fraction, mana_fraction(state))
        if wanted is not None:
            turn = await self.wisp_turn(wanted, state, heading=await self.wisp_heading(wanted, state))
            if turn is not None:
                return turn
        quest = await self.active_quest()
        if quest is None:
            if await wait_for_dialog(self.client, FOLLOW_UP_WAIT_SECONDS, poll=0.5):
                return await self.dialog_turn()
            if (cleared := await self.clear_world_turn(None, state)) is not None:
                return cleared
            if (switched := await self.switch_quest_turn()) is not None:
                return switched
            raise StopRun("no active main quest and no dialog offering one")
        if (cleared := await self.clear_world_turn(quest, state)) is not None:
            return cleared
        if (reason := unsupported_reason(quest.get("title"))) is not None:
            self.say_once("quest", f"skipping {quest['title']}: {reason}")
            if (switched := await self.switch_quest_turn()) is not None:
                return switched
        goals = open_goals(quest)
        await self.forget_a_finished_essence(quest, goals)
        goal = goals[0] if goals else {"type": "persona", "destination_zone": ""}
        arrow = await read_quest_arrow(self.client)
        goal_world, here_world = world_of(goal.get("destination_zone")), world_of(state["zone"])
        if (arrow_shows_no_target(arrow) and goal_world and goal_world != here_world
                and not self.record.limits.stay_in_world):
            return await self.to_the_world_turn(goal_world, state["zone"])
        if goal["type"] == "scavenge":
            self.record.quest = {"name": quest["name_key"], "title": quest.get("title"), "goal": goal["type"],
                                 "goal_id": goal.get("id"), "main": quest["mainline"] is True, "goal_zone": "",
                                 "arrow": None}
            if (refilled := await self.recharge_first_turn(state)) is not None:
                return refilled
            return await self.scavenge_turn(goal, state)
        if arrow_shows_no_target(arrow):
            if (travelled := await self.go_to_quest_area_turn(quest, goals)) is not None:
                return travelled
            if (travelled := await self.go_to_goal_zone_turn(goals, state["zone"])) is not None:
                return travelled
            arrow, goal = await self.goal_with_a_target(goals, goal)
            if arrow is None and goal["type"] in ("bounty", "bountycollect") and goal.get("target_code"):
                return await self.explore_turn(goal, goals)
            if arrow is None and self.record.clearing_world:
                return await self.park_the_active_quest(f"the quest arrow shows no target for its {goal['type']} goal "
                                                        "and no open goal's zone can be walked to",
                                                        title=quest.get("title"))
            if arrow is None:
                raise StopRun(f"the quest arrow shows no target for the {goal['type']} goal of "
                              f"{quest.get('title') or quest['name_key']}, and neither its tags {goal.get('tags')} "
                              f"nor its enemy {goal.get('target_code')} could be found; left for the operator")
        self.record.quest = {"name": quest["name_key"], "title": quest.get("title"), "goal": goal["type"],
                             "goal_id": goal.get("id"), "main": quest["mainline"] is True,
                             "goal_zone": goal["destination_zone"], "arrow": plain(arrow)}
        here = await self.client.zone_name()
        if await spiral_map_open(self.client):
            return await self.world_gate_turn(goal, here)
        if self.record.limits.stay_in_world and leaves_world(here, goal["destination_zone"]):
            if (switched := await self.switch_quest_turn(side_quests_only=True)) is not None:
                return switched
            left_open = [entry.get("title") or entry["name_key"] for entry in (await read_quests(self.client))["journal"]
                         if entry["mainline"] is not True]
            raise StopRun(f"the main quest {quest.get('title') or quest['name_key']} moves on to "
                          f"{world_of(goal['destination_zone'])}; no side quest of {world_of(here)} is left to switch to "
                          f"(still in the journal: {', '.join(left_open) or 'none'}); run again with --leave-world "
                          "to follow it")
        if topped_up(mana_fraction(state)):
            self._topping_up_in = None
        stuck_inside = (in_dungeon(state["zone"], self.record.entered_with_x)
                        and not self.travel_allowed_in(state["zone"]))
        mana_for_the_gate = 1.0 if stuck_inside else mana_fraction(state)
        refill = short_for_a_fight(health_fraction(state), mana_for_the_gate) if goal["type"] in FIGHT_GOALS else None
        if refill is None and goal["type"] in FIGHT_GOALS and self._refill_fully and not stuck_inside:
            health = health_fraction(state)
            refill = ("health" if health is not None and health < FULL_HEALTH_FRACTION
                      else "mana" if not topped_up(mana_fraction(state)) else None)
        if not stuck_inside and not health_to_travel(health_fraction(state)):
            self.record.recharging = True
        if refill is None and self.record.recharging and not stuck_inside:
            refill = still_to_recharge(health_fraction(state), mana_fraction(state))
            self.record.recharging = refill is not None
        if refill is None and (self._topping_up_in == state["zone"] or not mana_to_travel(mana_fraction(state))):
            refill = "mana"
        if refill is not None:
            turn = await self.refill_turn(refill, state)
            if turn is not None:
                return turn
        if refill is None and self.use_travel_buttons and not stuck_inside:
            if (recalled := await self.recall_toward_the_goal_turn(state, goal)) is not None:
                return recalled
            await self.mark_the_way_back(state, goal)
            await self.mark_the_goal_zone(state, goal)
            if (shortcut := await self.travel_plan_turn(state, goal, arrow)) is not None:
                return shortcut
        if leads_to_another_zone(goal, await self.client.zone_name()):
            return await self.waypoint_turn(arrow, goal)
        handler = self.goal_handlers().get(goal["type"])
        if handler is None:
            raise StopRun(f"goal type {goal['type']} is not handled yet")
        return await handler(arrow, goal)

    async def target_without_arrow(self, goal: dict):
        """Where a goal's target is when the quest arrow has none: the nearest placed object matching the goal's
        tags that has not been used yet, else the nearest loaded enemy whose display code the goal names."""
        me = await self.client.body.position()
        planner = await self.planner()
        zone = await self.client.zone_name()
        if goal.get("destination_zone") not in ("", None, zone):
            arrival = self.record.arrivals.get(zone, {})
            gate = gate_toward(planner.placed_objects, goal["destination_zone"],
                               arrival=arrival.get("position") if arrival.get("from") == goal["destination_zone"] else None)
            if gate is not None:
                self.events.emit("target", f"no quest arrow; the goal is in {goal['destination_zone']}, so going through "
                                           f"{gate.template} at ({gate.x:.0f}, {gate.y:.0f})")
                return XYZ(gate.x, gate.y, gate.z)
            return None
        objects = objects_for_goal(planner.objects_with_tags(goal.get("tags") or []), goal.get("tags") or [], me=(me.x, me.y),
                                   visited=self.record.visited_objects)
        if objects:
            self._object_in_use = objects[0]
            self.events.emit("target", f"no quest arrow; going to placed object {objects[0].template} at "
                                       f"({objects[0].x:.0f}, {objects[0].y:.0f}), {len(objects)} not yet used")
            return XYZ(objects[0].x, objects[0].y, objects[0].z)
        code = goal.get("target_code")
        matching = named_enemies_not_in_a_duel(await nearby_enemies(self.client), code)
        if matching:
            self.events.emit("target", f"no quest arrow; going to {matching[0]['name']} ({code}), "
                                       f"{matching[0]['distance']:.0f} away, {len(matching)} in sight")
            return matching[0]["position"]
        return await self.patrol_of_goal_enemy(goal, planner, me)

    async def patrol_of_goal_enemy(self, goal: dict, planner: RoutePlanner, me):
        """The nearest point on the patrol path of the enemy a goal names, matched by name: the goal's enemy is
        "Scarlet Screamer" and the zone has "Path 10_Screamer". Enemies load only nearby; their paths are in
        the zone's files."""
        code = goal.get("target_code")
        if not code or not planner.patrols:
            return None
        enemy_name = await game_language().text(code) or ""
        paths = planner.patrols.paths_named_like(enemy_name, *(goal.get("tags") or []))
        point = planner.patrols.nearest_point_on(paths, (me.x, me.y))
        if point is None:
            return None
        self.events.emit("target", f"no quest arrow and no {enemy_name or code} in sight; going to its patrol path "
                                   f"{', '.join(paths)} at ({point[0]:.0f}, {point[1]:.0f})")
        return XYZ(point[0], point[1], 0.0)

    async def goal_with_a_target(self, goals: list[dict], first: dict):
        """With no quest arrow, work on the first open goal whose target can be found, by its tags or by its
        enemies in sight, rather than searching for the first goal's while another's is known."""
        for goal in goals:
            arrow = await self.target_without_arrow(goal)
            if arrow is not None:
                return arrow, goal
        return None, first

    async def explore_turn(self, goal: dict, goals: list[dict] = ()) -> dict:
        """Look for a goal's enemies when none is in sight: walk to the nearest part of the zone not explored
        yet, stopping as soon as one shows up. Stops the run once every part has been seen."""
        code = goal["target_code"]
        zone = await self.client.zone_name()
        planner = await self.planner()
        explored = self.record.explored.setdefault(f"{zone}|{code}", [])
        me = await self.client.body.position()
        quest_objects = [thing for other in goals for thing in objects_for_goal(planner.objects_with_tags(other.get("tags") or []),
                                                                                 other.get("tags") or [], me=(me.x, me.y))]
        prefer = {planner.piece_of(thing.point) for thing in quest_objects} - {None} if planner.piece_of else set()
        area = next_area_to_explore(planner.exploration_points, me=(me.x, me.y), explored=explored, prefer=prefer)
        if area is None:
            raise StopRun(f"explored all of {zone} without seeing the enemy {code}; left for the operator")
        (x, y), _ = area
        self.events.emit("explore", f"looking for {code}: walking to ({x:.0f}, {y:.0f}), "
                                    f"{len(planner.exploration_points) - len(explored)} of "
                                    f"{len(planner.exploration_points)} areas left")

        async def target_in_sight():
            enemies = await nearby_enemies(self.client)
            return "target in sight" if any(enemy.get("display_code") == code for enemy in enemies) else None

        turn = await self.travel_turn("explore for quest enemies", XYZ(x, y, 0.0), arrive_radius=WAYPOINT_ARRIVE_RADIUS * 3,
                                      also=target_in_sight, avoid=await nearby_enemies(self.client))
        if turn.get("trip", {}).get("reason") in (None, "target in sight", "every route method failed"):
            explored.append((round(x), round(y)))
        return turn

    async def world_gate_turn(self, goal: dict, here: str) -> dict:
        """The Spiral Map is open (X at the Spiral Door): go to the world the goal is in when that is another world and
        the run may leave this one (`--leave-world`); otherwise close the map. "A Whole New World" sends the wizard
        through it to Krokotopia: X at the door's prompt ("to Interact") opened the map, and the run pressed X again
        and again while it stayed open."""
        world = world_of(goal.get("destination_zone"))
        if world and world != world_of(here) and not self.record.limits.stay_in_world:
            problem = await go_to_world(self.client, world)
            if problem is None:
                self.events.emit("door", f"went through the world gate to {world}")
                self.record.last_place = None
                return progressed("went through the world gate", world=world)
            self.events.emit("door", f"could not go through the world gate to {world}: {problem}")
            await leave_the_map(self.client)
            return stalled("could not go through the world gate", problem=problem)
        await leave_the_map(self.client)
        self.events.emit("door", "closed the Spiral Map: the goal is not in another world the run may go to")
        return stalled("closed the Spiral Map")

    async def clear_world_turn(self, quest: dict | None, state: dict) -> dict | None:
        """While clearing a world of its quests (`--clear-world`; the operator, 2026-10-28: "I feel like we did not
        actually clear wizard city. There is a quest finder you can use in the quest journal. Go there and finish the
        quests. That will make continuing easier"): outside that world, go there by the Spiral Door
        (`to_the_world_turn`); in it, do the quests the quest page lists there, then make the journal's Quest Finder
        the active quest and talk to the giver it points to, until it points out of the world or keeps pointing to a
        giver with nothing new; then the quest paused for it is the active one again. None to play the active quest
        as usual."""
        world = self.record.clearing_world
        if not world:
            return None
        here = state["zone"]
        title = " ".join(((quest or {}).get("title") or "").split())
        goals = open_goals(quest) if quest and quest.get("goals") is not None else []
        goal_zone = goals[0].get("destination_zone") if goals else None
        if title and title != QUEST_FINDER and self.record.paused_quest is None and not finder_points_into(goal_zone, world):
            self.record.paused_quest = title
        if world_of(here) != world:
            return await self.to_the_world_turn(world, here)
        if title == QUEST_FINDER:
            return await self.follow_the_finder(world, goals)
        if title and not unsupported_reason(title) and not parked(self.record.parked_quests, title, state["level"],
                                                                  self.record.held_quests):
            if finder_points_into(goal_zone, world) or in_world((await self.journal_zones()).get(title), world):
                return None
        zones = await self.journal_zones()
        skip = {name for name, count in self.record.quests_activated.items() if count >= MAX_ACTIVATIONS_PER_QUEST}
        skip |= {name for name in self.record.parked_quests if parked(self.record.parked_quests, name, state["level"],
                                                                      self.record.held_quests)}
        skip |= set(self.record.held_quests)
        if (target := next_quest_in_world(zones, world, skip=skip)) is not None:
            return await self.activate_for_world(target, f"a quest of {world} in the journal")
        if (visit := await self.school_quest_turn(world, state)) is not None:
            return visit
        if QUEST_FINDER not in zones:
            return await self.finish_clearing(world, "the journal has no Quest Finder")
        self._finder_just_activated = True
        return await self.activate_for_world(QUEST_FINDER, f"to find the next quest giver in {world}")

    async def school_quest_turn(self, world: str, state: dict) -> dict | None:
        """While clearing Wizard City, once a level: go to the professor of the wizard's school and talk; their menu's
        new quest, if any, is taken (`policy.TakeAllQuests`). School quests pay far more than side quests: "Introduction
        to Ice", from Lydia Greyrose's menu, gave 190 XP where Wizard City's side quests gave about 35, and the
        journal's Quest Finder never pointed at her (the coordinator, 2026-10-28). Kept per world and level in the
        knowledge file (`Knowledge.school_quests_checked`). None when done for this level, or no way is known."""
        level = state["level"]
        if world != world_of(COMMONS) or not isinstance(level, int) or self.record.school_quests_checked.get(world) == level:
            return None
        wizard = await read_wizard(self.client)
        school = SCHOOLS.get(wizard.school) if wizard is not None else None
        if school is None:
            self.record.school_quests_checked[world] = level
            return None
        planner = await self.planner()
        way = way_to_school(state["zone"], school, [volume.name for volume, _ in planner.teleports])
        if way is None:
            self.record.school_quests_checked[world] = level
            self.events.emit("quest", f"no way known to {school.professor} for school quests; going on")
            return None
        if way.kind != TRAINER:
            door = self.door_on_the_way(way, planner)
            if door is None:
                self.record.school_quests_checked[world] = level
                return None
            self.say_once("quest", f"visiting {school.professor} for school quests (level {level})")
            return await self.walk_to_door_turn(f"walk toward {school.professor} for school quests", *door)
        professor = await nearest_npc(self.client)
        if professor is None:
            return None
        if flat_distance(await self.client.body.position(), professor) > NPC_ARRIVE_DISTANCE:
            return await self.travel_turn(f"walk to {school.professor}", professor, arrive_radius=NPC_ARRIVE_DISTANCE)
        self.record.school_quests_checked[world] = level
        opened = await open_with_professor(self.client, professor)
        self.events.emit("quest", f"talked to {school.professor} for school quests: {opened}")
        return progressed(f"visited {school.professor} for school quests", opened=opened)

    async def follow_the_finder(self, world: str, goals: list[dict]) -> dict | None:
        """The Quest Finder is active: when it points into the world, the talk goal leads to the giver (None); when it
        points elsewhere, at nothing, or a third time to the same giver, the world is cleared."""
        goal = goals[0] if goals else {}
        goal_zone = goal.get("destination_zone")
        if not finder_points_into(goal_zone, world):
            return await self.finish_clearing(world, f"the Quest Finder points to {goal_zone or 'nothing'}")
        arrow = await read_quest_arrow(self.client)
        if arrow_shows_no_target(arrow):
            return await self.finish_clearing(world, f"the Quest Finder shows no giver in {goal_zone}")
        if self._finder_just_activated:
            self._finder_just_activated = False
            self.record.talks_leaving_goal_open.pop(str(goal.get("id")), None)
            giver = (goal_zone, round(arrow.x, -2), round(arrow.y, -2))
            self._finder_givers[giver] = self._finder_givers.get(giver, 0) + 1
            self.events.emit("quest", f"the Quest Finder points to a quest giver in {goal_zone} at "
                                      f"({arrow.x:.0f}, {arrow.y:.0f})")
            if self._finder_givers[giver] > FINDER_SAME_GIVER_LIMIT:
                return await self.finish_clearing(world, f"the Quest Finder keeps pointing to the same giver in "
                                                         f"{goal_zone}, who offers nothing new")
        if self.record.talks_leaving_goal_open.get(str(goal.get("id")), 0) >= 2:
            return await self.finish_clearing(world, f"the giver the Quest Finder points to in {goal_zone} offered "
                                                     "nothing")
        return None

    async def finish_clearing(self, world: str, why: str) -> dict:
        if self.record.wanted_reagents and not self._reagents_revisited:
            self._reagents_revisited = True
            waiting = list(self.record.wanted_reagents.values())
            for title in waiting:
                self.record.parked_quests.pop(title, None)
            self.events.emit("world", f"{world}: {why}; trying the quests that wait for reagents once more "
                                      f"({', '.join(waiting)})")
            return await self.activate_for_world(waiting[0], "a quest waiting for its reagent, tried once more")
        paused = self.record.paused_quest
        self.record.clearing_world = self.record.paused_quest = None
        self.events.emit("world", f"{world} cleared: {why}" + (f"; back to {paused}" if paused else ""))
        if paused:
            return await self.activate_for_world(paused, "the quest paused to clear the world")
        return progressed(f"cleared {world}")

    async def activate_for_world(self, title: str, why: str) -> dict:
        activation = await activate_quest(self.client, title)
        active = (await read_quests(self.client))["active"]
        switched = activation.problem is None and active is not None and same_title(active.get("title") or "", title)
        if title != QUEST_FINDER:
            self.record.quests_activated[title] = self.record.quests_activated.get(title, 0) + 1
        self.events.emit("quest", f"made {title} the active quest ({why})" if switched else
                                  f"could not make {title} the active quest: "
                                  f"{activation.problem or 'another quest is active after Activate'}")
        return (progressed if switched else stalled)("switched the active quest", to=title)

    async def journal_zones(self) -> dict[str, str]:
        """The world the quest page shows for each quest (`questbook.journal_zones`), read again only when the journal
        changed, and logged."""
        titles = frozenset(" ".join((entry.get("title") or "").split())
                           for entry in (await read_quests(self.client))["journal"])
        if self._journal_zones is None or self._journal_zones[0] != titles:
            zones = await journal_zones(self.client)
            self._journal_zones = (titles, zones)
            self.events.emit("quest", "the quest page lists: " + "; ".join(f"{title} ({zone or '-'})"
                                                                           for title, zone in zones.items()))
        return self._journal_zones[1]

    def forget_a_mark_out_of_reach(self, problem: str) -> None:
        """Recall pressed but no zone change: the marked place can no longer be reached (a dungeon closes once the
        wizard leaves it), so the mark is forgotten rather than tried again."""
        if problem == RECALL_NOT_REACHED:
            self.events.emit("travel", f"forgetting the mark in {self.record.marked_in}: Recall cannot reach it")
            self.record.marked_in = self.record.mark_tip = None

    async def recall_into_the_world_turn(self, world: str, here: str) -> dict | None:
        """The Recall button's mark is in the world the wizard is going to: Recall Location there, about 5 mana, before
        any Spiral Door. Handing in "Bear Market" in Olde Town took the wizard to Grizzleheim's hub, a world with no
        known way to its Spiral Door, while the Recall button still named the Olde Town mark (00:31)."""
        marked_in = self.record.marked_in
        if marked_in is None or world_of(marked_in) != world or not self.travel_allowed_in(marked_in):
            return None
        mana = await attempt(self.client.stats.current_mana())
        if not isinstance(mana, int) or mana < MARK_MANA_NEEDED or await recall_tip(self.client) != self.record.mark_tip:
            return None
        started = time.monotonic()
        problem = await recall(self.client)
        if problem is not None:
            self.events.emit("travel", f"could not recall to the mark in {marked_in} from {here}: {problem}")
            self.forget_a_mark_out_of_reach(problem)
            return None
        self._teleport_pressed = (RECALL, started)
        self.record.last_place = None
        self.events.emit("travel", f"recalled from {here} to the mark in {marked_in}, to go back to {world}")
        return progressed("recalled into the world", world=world)

    async def to_the_world_turn(self, world: str, here: str) -> dict:
        """Toward another world: at the Spiral Map, choose it (`world_gate_turn`); in this world's teleporter room,
        walk to the Spiral Door ("Universe Teleport") and press X at its prompt; elsewhere, walk into a volume toward
        the teleporter room, or one door of the way there (`training.way_toward_zone`), else Go Home first."""
        if await spiral_map_open(self.client):
            return await self.world_gate_turn({"destination_zone": f"{world}/"}, here)
        if (recalled := await self.recall_into_the_world_turn(world, here)) is not None:
            return recalled
        planner = await self.planner()
        room = WORLD_DOOR_ROOMS.get(world_of(here))
        if here == room:
            door = next((placed for placed in planner.placed_objects if placed.template == WORLD_DOOR), None)
            if door is None:
                raise StopRun(f"no Spiral Door found in {room} to go to {world}; left for the operator")
            self.say_once("world", f"walking to the Spiral Door in {room} to go to {world}")
            return await self.walk_to_door_turn(f"walk to the Spiral Door for {world}", XYZ(door.x, door.y, door.z), 0.0)
        volume = next((volume for volume, _ in planner.teleports if leads_to_the_world_door(volume.name)), None)
        if volume is not None:
            self.say_once("world", f"walking into {volume.name} toward the Spiral Door, to go to {world}")
            return await self.walk_to_door_turn(f"walk toward the Spiral Door for {world}",
                                                XYZ(volume.x, volume.y, volume.z), volume.radius)
        if room is not None:
            way = way_toward_zone(here, room, [volume.name for volume, _ in planner.teleports])
            door = None if way is None else self.door_on_the_way(way, planner)
            if door is not None:
                self.say_once("world", f"walking toward {room} by way of {way.name}, to go to {world}")
                return await self.walk_to_door_turn(f"walk toward {room} for {world}", *door)
        hub = self.record.hubs.get(world_of(here)) or HUBS.get(world_of(here))
        if self.travel_allowed_in(here) and hub and here != hub:
            started = time.monotonic()
            problem = await go_to_the_commons(self.client)
            if problem is None:
                self._teleport_pressed = (GO_HOME, started)
                self.record.last_place = None
                self.events.emit("travel", f"went home to {hub}, on the way to the Spiral Door for {world}")
                return progressed("went home toward the Spiral Door", world=world)
        raise StopRun(f"no way to the Spiral Door is known from {here} to go to {world}; left for the operator")

    async def switch_quest_turn(self, *, side_quests_only: bool = False) -> dict | None:
        """Make another quest the active one through the quest book (`questbook.activate_quest`), when the offer
        policy takes side quests: the next side quest, the one ready to hand in first, each at most
        MAX_ACTIVATIONS_PER_QUEST times a run; and with no active quest and no side quest left, the main quest.
        None when there is nothing to switch to."""
        if not getattr(self.offer_policy, "side_quests", False):
            return None
        quests = await read_quests(self.client)
        journal, active_title = quests["journal"], (quests["active"] or {}).get("title")
        active_title = " ".join(active_title.split()) if active_title else None
        titled = [entry for entry in journal if entry.get("title") and " ".join(entry["title"].split()) != active_title
                  and entry["title"] != QUEST_FINDER
                  and not unsupported_reason(entry["title"])
                  and self.record.quests_activated.get(" ".join(entry["title"].split()), 0) < MAX_ACTIVATIONS_PER_QUEST]
        side_quests = [entry for entry in titled if entry["mainline"] is not True]
        main_quests = [] if side_quests_only else [entry for entry in titled if entry["mainline"] is True]
        candidates = side_quests or main_quests
        if not candidates:
            return None
        choice = next((entry for entry in candidates if entry["ready_to_turn_in"]), candidates[0])
        title = " ".join(choice["title"].split())
        self.record.quests_activated[title] = self.record.quests_activated.get(title, 0) + 1
        activation = await activate_quest(self.client, title)
        problem = activation.problem
        if activation.area:
            self._quest_areas[title] = activation.area
        active = (await read_quests(self.client))["active"]
        switched = problem is None and active is not None and " ".join((active.get("title") or "").split()) == title
        self.events.emit("quest", f"made {title} the active quest through the quest book" if switched else
                                  f"could not make {title} the active quest: "
                                  f"{problem or 'another quest is active after Activate'}")
        if switched:
            return progressed("switched the active quest", to=title)
        return stalled("could not switch the active quest", quest=title, problem=problem)

    async def active_quest(self) -> dict | None:
        """The active quest. A side quest stops the run unless the offer policy takes side quests."""
        active = (await read_quests(self.client))["active"]
        if active is not None and active["mainline"] is not True and not getattr(self.offer_policy, "side_quests", False):
            raise StopRun(f"the active quest {active['name_key']} is not a main quest")
        return active

    async def bounty_turn(self, arrow, goal: dict) -> dict:
        """Walk toward the arrow around other enemies, then walk into a target enemy near the arrow. An arrow at a
        door with no target in reach leads through it: in the Witch's house, the bounty's arrow pointed at the exit,
        the wizard "arrived" at it each turn, and the run stopped for turns without progress."""
        enemies = await nearby_enemies(self.client)
        targets = quest_targets(enemies, arrow)
        in_reach = [target for target in targets if target["distance"] <= TARGET_REACH]
        if in_reach:
            result = await approach(self.client, in_reach[0])
            did = f"approached {in_reach[0]['name']}"
            return progressed(did) if result["ok"] else stalled(did, reason=result.get("reason"))
        door = volume_at([volume for volume, _ in (await self.planner()).teleports], xy(arrow))
        if door is not None and flat_distance(await self.client.body.position(), arrow) <= ARROW_ARRIVE_RADIUS:
            self.events.emit("door", f"the bounty's arrow points at {door.name}, with no target in reach; going through")
            return await self.zone_door_turn(XYZ(door.x, door.y, door.z))

        async def target_in_reach():
            here = quest_targets(await nearby_enemies(self.client), arrow)
            return "target in reach" if any(target["distance"] <= TARGET_REACH for target in here) else None

        return await self.travel_turn("travel toward bounty targets", arrow, arrive_radius=ARROW_ARRIVE_RADIUS,
                                      also=target_in_reach, avoid=bystanders(enemies, targets), ignore=targets,
                                      seen=summary(enemies))

    async def refill_turn(self, stat: str, state: dict) -> dict | None:
        """Too little health or mana for a fight the quest asks for (`progress.short_for_a_fight`), or mana being
        topped up. Among enemies a wisp is fetched only within WISP_REACH: with 1 mana in Firecat Alley, a trip to
        a mana wisp 3,885 units away walked into a Fire Elf. In a zone where no enemy has been met, mana comes first
        when both are short: health comes back
        there while the wizard waits for mana, and fetching health first, of which the Commons has no wisps, then
        searching for mana and stopping at the first mana wisp seen, went round in circles until the run stopped.
        Fetch the nearest safe wisp of that kind in sight, however far. Otherwise, in a zone where no enemy has been
        met, `safe_zone_refill_turn`. In an interior, and for mana in a street, walk out through the
        zone's exit volume: General Akilles' tower has no wisps, and in Cyclops Lane fetching mana wisps through
        nine to thirteen enemies lost mana, since the fights it led into cost 5 to 10 each and a wisp gives 3 to 6.
        The exit leads back toward the hub: from Cyclops Lane, to Olde Town. For health in a street, explore it:
        wisps are spawned, not placed, and load only nearby. Potions are never bought."""
        if in_dungeon(state["zone"], self.record.entered_with_x):
            if self.travel_allowed_in(state["zone"]) and (trip := await self.dungeon_trip_turn(stat, state)) is not None:
                return trip
            return await self.dungeon_refill_turn(stat, state)
        indoors = INTERIOR_WORD in state["zone"]
        safe_zone = not indoors and state["zone"] not in self.record.zones_with_enemies
        if safe_zone and stat == "health" and not mana_for_a_fight(mana_fraction(state)):
            stat = "mana"
        if stat == "mana" and safe_zone:
            self.top_up_in(state["zone"])
        turn = await self.wisp_turn(stat, state, reach=refill_reach(safe_zone))
        if turn is not None:
            return turn
        planner = await self.planner()
        if await nearby_enemies(self.client):
            self.saw_enemies(state["zone"])
        if safe_zone:
            return await self.safe_zone_refill_turn(stat, state, planner)
        too_small_to_search = len(planner.exploration_points) <= FEW_PLACES_TO_LOOK
        if (stat == "mana" or too_small_to_search) and not indoors and self.use_travel_buttons:
            turn = await self.commons_trip_turn(stat, state)
            if turn is not None:
                return turn
        if indoors or stat == "mana":
            turn = await self.leave_for_wisps_turn(stat, state, planner)
            if turn is not None:
                return turn
        if indoors:
            return stalled(f"too little {stat} for the fight, and no {stat} wisp here to fetch")
        return await self.explore_for_wisps_turn(stat, state, planner, reach=refill_reach(safe_zone))

    async def dungeon_refill_turn(self, stat: str, state: dict) -> dict | None:
        """Inside a tower or dungeon the wizard never leaves to refill: a walk out gives up its progress (the
        operator: "I don't think you can leave a tower without losing progress"; the Golem Tower's floors were full
        again after each trip out, and the game refuses Mark Location there). So: a wisp of the kind in reach, else
        standing still between fights, once: on a Golem Tower floor 90 seconds of standing gave back nothing (health
        795 to 795, mana 80 to 80; in the Commons health comes back at about 2.4 a second), so after one wait that
        gains nothing the fight goes on with the heals in hand, and no dungeon is waited in again this run. Health
        potions are drunk before this (`potion_turn`)."""
        turn = await self.wisp_turn(stat, state, reach=refill_reach(False))
        if turn is not None:
            return turn
        if self._dungeons_give_nothing_back:
            return None
        self.say_once("refill", f"{state[stat]} of {state['max_' + stat]} {stat} in {state['zone']}, a dungeon: "
                                "refilling here, not leaving")
        waited = await self.wait_for_mana_turn(state)
        if waited["progress"]:
            return waited
        self._dungeons_give_nothing_back = True
        self.say_once("refill", f"nothing came back while waiting in {state['zone']}; dungeons are not waited in "
                                "again this run, and the fight goes on")
        return None

    def saw_enemies(self, zone) -> None:
        """Remember that `zone` has enemies, for this run and, through the knowledge file, later ones."""
        if isinstance(zone, str) and zone not in self.record.zones_with_enemies:
            self.record.zones_with_enemies.append(zone)

    async def safe_zone_refill_turn(self, stat: str, state: dict, planner: RoutePlanner) -> dict | None:
        """In a zone where no enemy has been met. Health alone is not waited for (the operator: resting "is not time
        efficient"), so None and the wizard walks on, except while recharging after a defeat (`progress.
        still_to_recharge`; the operator: "seek out blue and red wisps in safe areas to recharge after death"): the
        zone is searched once for health wisps, then the wizard stands while health comes back, about 2.4 a second.
        Mana is waited for: the operator allowed waiting in Olde Town for it, or looking for wisps; but not while
        recharging after a defeat, which goes on with mana over the travel reserve once no blue wisp is left here or
        in the hub (`home_for_wisps_turn`): standing gave about 2 mana a minute. The zone is
        searched once for mana wisps, safe here, then the wizard stands still while mana comes back
        (`wait_for_mana_turn`) until `progress.topped_up`; health comes back meanwhile.
        Once the zone and the hub are searched, the search starts over rather than standing (`keep_looking_turn`):
        wisps come back, and health and mana come back while walking too."""
        if stat == "health" and mana_for_a_fight(mana_fraction(state)):
            if not self.record.recharging:
                return None
            turn = await self.explore_for_wisps_turn("health", state, planner, reach=refill_reach(True), again=False)
            if turn is None:
                turn = await self.home_for_wisps_turn("health", state)
            return turn if turn is not None else await self.keep_looking_turn("health", state, planner)
        self.top_up_in(state["zone"])
        turn = await self.explore_for_wisps_turn("mana", state, planner, reach=refill_reach(True), again=False)
        if turn is None:
            turn = await self.home_for_wisps_turn("mana", state)
        if turn is None and self.record.recharging and spare_mana(state["mana"]):
            self.record.recharging, self._topping_up_in = False, None
            self.events.emit("mana", f"no blue wisp left to find in {state['zone']} or the hub; going on with "
                                     f"{state['mana']} mana, over the {TRAVEL_MANA_RESERVE} kept for fights and "
                                     "Recall, rather than standing for mana (about 2 a minute)")
            return None
        return turn if turn is not None else await self.keep_looking_turn("mana", state, planner)

    async def keep_looking_turn(self, stat: str, state: dict, planner: RoutePlanner) -> dict:
        """The safe zone was searched for wisps and none is left in sight: search it again from the start, since used-up
        wisps come back, and health and mana come back while walking as while standing. Standing only when no part of
        the zone is left to walk to. The operator, 2026-10-28: "Standing to regenerate is fine, but it should continue
        to hunt for wisps in known safe areas since that is faster than just waiting around plus you regen health as you
        are looking." Used-up wisps come back. A walk that reached its point but was too short to count as progress
        goes on to the next point, up to SEARCH_WALKS_BEFORE_STANDING walks: a 232 walk in the Commons was followed
        by 90 s standing at 429 of 1164 health (14:32)."""
        for _ in range(SEARCH_WALKS_BEFORE_STANDING):
            turn = await self.explore_for_wisps_turn(stat, state, planner, reach=refill_reach(True), again=True)
            if turn["progress"] or not reached_its_point(turn):
                break
        if turn["progress"]:
            return turn
        return await self.wait_for_mana_turn(state, waiting_for=stat)

    async def home_for_wisps_turn(self, stat: str, state: dict) -> dict | None:
        """This safe zone was searched and holds no wisp of the kind needed: Go Home, free, to search the world's hub
        (`travelplan.worth_going_home_for_wisps`), once from each zone. None when not worth it or not possible, so
        the wizard stands instead."""
        zone = state["zone"]
        hub = self.record.hubs.get(world_of(zone)) or HUBS.get(world_of(zone))
        if not self.travel_allowed_in(zone) or not worth_going_home_for_wisps(zone, hub, self._went_home_for_wisps):
            return None
        self._went_home_for_wisps.add(zone)
        started = time.monotonic()
        problem = await go_to_the_commons(self.client)
        if problem is not None:
            self.events.emit("travel", f"could not go home for {stat} wisps: {problem}; standing instead")
            return None
        self._teleport_pressed = (GO_HOME, started)
        self.events.emit("travel", f"no {stat} wisp left in {zone}; went home to {hub} to look for them there")
        self.record.last_place = None
        return progressed(f"went home for {stat} wisps", stat=stat)

    def top_up_in(self, zone: str) -> None:
        """From now on, refill mana in `zone` until `progress.topped_up`, not just until a fight is allowed. Set as
        soon as a mana refill begins in a zone without enemies: set only once its search began, a first wisp in Olde
        Town brought mana from 11 to 14, over the 12 a fight needs, and the wizard went back to Cyclops Lane."""
        if self._topping_up_in != zone:
            self._topping_up_in = zone
            self.record.explored.pop(f"{zone}|{MANA_WISP}s", None)

    async def wait_for_mana_turn(self, state: dict, waiting_for: str = "mana") -> dict:
        """Stand still for up to MANA_WAIT_SECONDS, so the loop keeps checking for battles, popups and the STOP file
        between waits. Mana comes back in a zone without enemies, about 2 a minute (0 to 30 within 17 minutes in the
        Commons); health about 2.4 a second. In Cyclops Lane neither came back."""
        deadline = time.monotonic() + MANA_WAIT_SECONDS
        now = state
        while time.monotonic() < deadline and not self.settings.stop_requested():
            await asyncio.sleep(MANA_WAIT_POLL_SECONDS)
            now = await snapshot(self.client)
            if battle_showing(now) or not free_to_move(now) or now["zone"] != state["zone"]:
                break
        self.events.emit("mana", f"waited in {state['zone']} for {waiting_for}: {state['mana']} -> {now['mana']} of "
                                 f"{now['max_mana']}, health {state['health']} -> {now['health']}")
        gained = any(isinstance(now[stat], int) and isinstance(state[stat], int) and now[stat] > state[stat]
                     for stat in ("mana", "health"))
        return (progressed if gained else stalled)(f"waited for {waiting_for}", before=state["mana"], after=now["mana"])

    def travel_allowed_in(self, zone: str) -> bool:
        """The travel buttons may be pressed here (`training.travel_buttons_allowed`)."""
        return travel_buttons_allowed(zone, self.record.entered_with_x, self.record.leaving_resets,
                                      use_travel_buttons=self.use_travel_buttons, leave_dungeons=self.leave_dungeons)

    async def dungeon_trip_turn(self, stat: str, state: dict) -> dict | None:
        """In a dungeon, not a tower: a wisp in reach, else mark the spot, Go Home, refill and Recall back
        (`commons_trip_turn`), leaving only once the mark is set, so the way back is sure. The enemies near the
        mark are counted, to see on the way back whether the dungeon held (`check_the_dungeon_held`)."""
        if (turn := await self.wisp_turn(stat, state, reach=refill_reach(False))) is not None:
            return turn
        enemies = len(await nearby_enemies(self.client))
        turn = await self.commons_trip_turn(stat, state, must_come_back=True)
        if turn is not None:
            self._left_dungeon = (state["zone"], enemies)
            self.events.emit("dungeon", f"left {state['zone']} by Go Home to refill {stat}, {enemies} enemies near "
                                        "the mark; Recall brings the wizard back")
        return turn

    async def check_the_dungeon_held(self, state: dict) -> None:
        """Back from a refill trip out of a dungeon: if Recall did not land in it, or more enemies stand near the mark
        than when the wizard left, the dungeon reset; it is kept in the knowledge file as one that resets when left,
        and refilled in place from then on."""
        zone, enemies_before = self._left_dungeon
        self._left_dungeon = None
        if state["zone"] != zone:
            reset, detail = True, f"Recall brought the wizard to {state['zone']}, not back in"
        else:
            enemies_now = len(await nearby_enemies(self.client))
            reset = enemies_now > enemies_before + 1
            detail = f"{enemies_before} enemies near the mark when it left, {enemies_now} now"
        if reset and zone not in self.record.leaving_resets:
            self.record.leaving_resets.append(zone)
        self.events.emit("dungeon", f"{zone} {'reset' if reset else 'held'} after a refill trip ({detail})"
                                    + ("; refilling in place there from now on" if reset else ""))

    async def commons_trip_turn(self, stat: str, state: dict, mark: bool = True,
                                must_come_back: bool = False) -> dict | None:
        """Short of mana in a street with no wisp to fetch, or of health in a zone too small to look for wisps in
        (a Golem Tower floor has one place to look): mark the spot (Mark Location costs about 5 mana, so only with
        MARK_MANA_NEEDED), then Go to The Commons, the world's hub, where mana and health come back (free; a walk
        back through the exits met enemies, and in Cyclops Lane fetching wisps cost more mana than it gave).
        `back_from_the_commons_turn` returns to the mark. None when the tools cannot be used now, so the wizard
        walks."""
        zone = state["zone"]
        if mark and self._marked_in is None and isinstance(state["mana"], int) and state["mana"] >= MARK_MANA_NEEDED:
            if await self.kept_mark_in(zone):
                self._marked_in = zone
                self.events.emit("travel", f"keeping the mark already set in {zone}, nearer the goal than here, for "
                                           f"the way back")
            else:
                await self.mark_before_the_trip(zone, stat)
        if must_come_back and self._marked_in != zone:
            return None
        return await self.go_home_for(stat, state)

    def forget_the_mark_in(self, zone: str) -> None:
        """No Recall back to `zone`'s mark: the wizard walks in, and marks again on arriving in the goal's zone."""
        if self.record.marked_in == zone:
            self.record.marked_in, self.record.mark_tip = None, None
            self._mark_position = None

    async def distance_to_the_goal_here(self, zone: str) -> float | None:
        """How far the active quest's arrow is, when it points into this zone; None otherwise."""
        quest = self.record.quest or {}
        arrow = quest.get("arrow")
        if not arrow or quest.get("goal_zone") != zone:
            return None
        return flat_distance(await self.client.body.position(), XYZ(arrow["x"], arrow["y"], 0.0))

    async def kept_mark_in(self, zone: str) -> bool:
        """The Recall button still names the mark recorded for `zone`, set this run nearer the goal's arrow than the
        wizard is now, so a trip from here Recalls to it rather than marking over it. Otherwise a mark here keeps the
        ground won: on Colossus Boulevard the quest object lay about 6,600 past the fights, each fight a step nearer,
        and a mark where a battle had just ended brought the wizard back there, into the next fight (14:45)."""
        arrow = (self.record.quest or {}).get("arrow")
        if self.record.marked_in != zone or not self.record.mark_tip or self._mark_position is None or not arrow:
            return False
        goal = XYZ(arrow["x"], arrow["y"], 0.0)
        if flat_distance(self._mark_position, goal) >= flat_distance(await self.client.body.position(), goal):
            return False
        return await has_mark(self.client) and await recall_tip(self.client) == self.record.mark_tip

    async def mark_before_the_trip(self, zone: str, stat: str) -> None:
        problem = await mark_here(self.client)
        since = ("" if self._battle_ended_at is None
                 else f", {time.monotonic() - self._battle_ended_at:.0f} s after the last battle ended")
        self.events.emit("travel", f"marked the spot in {zone} before leaving for {stat}{since}" if problem is None
                                   else f"could not mark the spot in {zone}{since}: {problem}")
        self._marked_in = zone if problem is None else None
        if problem is None:
            self.record.marked_in, self.record.mark_tip = zone, await recall_tip(self.client)
            self._mark_position = await self.client.body.position()
            self.record.mark_purpose, self.record.mark_quest = FOR_A_REFILL, None
            self.record.mark_door_for = None

    async def go_home_for(self, stat: str, state: dict) -> dict | None:
        """Go to The Commons to refill `stat`; None when the button could not be used."""
        zone = state["zone"]
        started = time.monotonic()
        problem = await go_to_the_commons(self.client)
        if problem is not None:
            self.events.emit("travel", f"could not go to the Commons for mana: {problem}")
            return None
        self._teleport_pressed = (GO_HOME, started)
        self._trip_stat, self._trip_started = stat, time.monotonic()
        self.events.emit("travel", f"went to the Commons from {zone} with {state['mana']} mana and {state['health']} "
                                   f"health, to refill {stat} there")
        self.record.last_place = None
        return progressed("went to the Commons for a refill", stat=stat)

    def learn_the_way(self, left: str | None, arrived: str) -> None:
        """A zone change: when it was walked (not a travel button, not waking after a defeat), the two zones are
        linked for the travel plan, and the time spent crossing the zone left is learned, when the wizard went
        through it to another zone than it came from (a door bounce taught 8 s a zone); after Go Home or Recall,
        its time from the press to the arrival is learned, and after Go Home, where the world's hub is."""
        now = time.monotonic()
        if self._teleport_pressed is not None:
            way, pressed = self._teleport_pressed
            if now - pressed <= TELEPORT_LOAD_LIMIT_SECONDS:
                self.learn_cost("go_home_seconds" if way == GO_HOME else "recall_seconds", now - pressed)
            if way == GO_HOME and world_of(arrived):
                self.record.hubs[world_of(arrived)] = arrived
        walked = self._teleport_pressed is None and now - self._defeated_at > DEFEAT_ARRIVAL_SECONDS
        if walked and isinstance(left, str) and world_of(left) == world_of(arrived):
            link_zones(self.record.zone_links, left, arrived)
            spent = None if self._zone_entered_at is None else now - self._zone_entered_at
            crossed = self._entered_walking and arrived != self._entered_from
            if crossed and spent is not None and ZONE_SAMPLE_SECONDS[0] <= spent <= ZONE_SAMPLE_SECONDS[1]:
                self.learn_cost("zone_seconds", spent)
        self._teleport_pressed = None
        self._zone_entered_at, self._entered_walking, self._entered_from = now, walked, left

    def learn_walk_speed(self, turn: dict, seconds: float) -> None:
        moved = (turn.get("trip") or {}).get("moved") if isinstance(turn.get("trip"), dict) else None
        if isinstance(moved, (int, float)) and moved >= WALK_SAMPLE_MOVED and seconds > 0:
            self.learn_cost("walk_speed", moved / seconds)

    def learn_cost(self, name: str, measured: float) -> None:
        self.travel_costs.learn(name, measured)
        self.record.travel_costs = self.travel_costs.as_dict()

    async def mark_the_way_back(self, state: dict, goal: dict) -> None:
        """A goal was just finished here and the next is in another zone (`travelplan.worth_a_way_back_mark`): Mark
        Location, so the quest's way back here, often to the one who gave it, is a Recall instead of a walk. The
        operator: "this could help a lot with but not limited to back tracking". The mark is kept for the rest of
        the quest: the goal's zone is not marked over it."""
        here, goal_zone = state["zone"], goal.get("destination_zone")
        quest_name = (self.record.quest or {}).get("name")
        current = (quest_name, goal.get("id"))
        finished_zone = self._last_goal_zone if self._last_goal not in (None, current) else None
        self._last_goal, self._last_goal_zone = current, goal_zone
        hub = self.record.hubs.get(world_of(here)) or HUBS.get(world_of(here))
        if here in self._unmarkable or not worth_a_way_back_mark(here, finished_zone, goal_zone, hub,
                                                                  self.record.zone_links, self.record.marked_in,
                                                                  state["mana"]):
            return
        problem = await mark_here(self.client)
        if problem is not None:
            self._unmarkable.add(here)
            self.events.emit("travel", f"could not mark the way back in {here}: {problem}")
            return
        self.record.marked_in, self.record.mark_tip = here, await recall_tip(self.client)
        self._mark_position = await self.client.body.position()
        self.record.mark_purpose, self.record.mark_quest = WAY_BACK, quest_name
        self.record.mark_door_for = None
        self.events.emit("travel", f"marked the way back in {here} before leaving for {goal_zone} "
                                   f"({state['mana']} mana before)")

    async def travel_plan_turn(self, state: dict, goal: dict, arrow) -> dict | None:
        """For a goal in another zone: walk, Go Home or Recall, whichever `travelplan.choose_travel` expects to get
        there first, with both estimates in one logged line (once a goal when walking). A goal gets at most
        MAX_TELEPORTS_PER_GOAL teleports, and after a refused press the wizard walks for a minute."""
        here, goal_zone = state["zone"], goal.get("destination_zone")
        if not goal_zone or goal_zone == here or time.monotonic() < self._no_teleport_until:
            return None
        key = ((self.record.quest or {}).get("name"), goal.get("id"))
        if self._teleports_for.get(key, 0) >= MAX_TELEPORTS_PER_GOAL:
            return None
        door_distance = flat_distance(await self.client.body.position(), arrow) if arrow is not None else 0.0
        marked = self.record.marked_in
        if marked is not None and (not self.travel_allowed_in(marked)
                                   or await recall_tip(self.client) != self.record.mark_tip):
            marked = None
        choice = choose_travel(here=here, goal_zone=goal_zone, door_distance=door_distance,
                               links=self.record.zone_links,
                               hub=self.record.hubs.get(world_of(here)) or HUBS.get(world_of(here)), marked_in=marked,
                               mana=state["mana"], costs=self.travel_costs,
                               go_home_ready=await go_home_ready(self.client),
                               recall_ready=marked is not None and await recall_ready(self.client))
        line = f"plan {choice.describe(here, goal_zone)}"
        if choice.way == WALK:
            if self._travel_planned_for != (here, *key):
                self._travel_planned_for = (here, *key)
                self.events.emit("travel", line)
            return None
        self.events.emit("travel", line)
        started = time.monotonic()
        problem = await (go_to_the_commons(self.client) if choice.way == GO_HOME else recall(self.client))
        if problem is not None:
            self._no_teleport_until = time.monotonic() + 60.0
            self.events.emit("travel", f"could not {choice.way}: {problem}; walking instead")
            return None
        self._teleport_pressed = (choice.way, started)
        self._teleports_for[key] = self._teleports_for.get(key, 0) + 1
        self.record.last_place = None
        return progressed(f"took {choice.way} toward the goal", estimates=choice.estimates)

    async def mark_the_goal_zone(self, state: dict, goal: dict) -> None:
        """Arrived in the zone the goal is in, where enemies have been met (`progress.worth_marking`): Mark Location,
        so a defeat here, which wakes the wizard in the world's hub, is followed by Recall Location back
        (`recall_toward_the_goal_turn`) instead of a walk through the same enemies. A zone that refuses a mark is
        not asked again in this run."""
        zone = state["zone"]
        if self.record.mark_purpose == WAY_BACK and self.record.mark_quest == (self.record.quest or {}).get("name"):
            return
        if not worth_marking(zone, goal.get("destination_zone"), self.record.marked_in, state["mana"],
                             enemies_here=zone in self.record.zones_with_enemies, refused=zone in self._unmarkable):
            return
        problem = await mark_here(self.client)
        if problem is not None:
            self._unmarkable.add(zone)
            self.events.emit("travel", f"could not mark the spot in {zone}: {problem}")
            return
        self.record.marked_in, self.record.mark_tip = zone, await recall_tip(self.client)
        self._mark_position = await self.client.body.position()
        self.record.mark_purpose, self.record.mark_quest = AFTER_A_DEFEAT, None
        self.record.mark_door_for = None
        self.events.emit("travel", f"marked the spot in {zone}, the goal's zone, to recall to after a defeat "
                                   f"({state['mana']} mana before)")

    async def recall_toward_the_goal_turn(self, state: dict, goal: dict) -> dict | None:
        """The Recall button holds a mark in the zone the goal is in and the wizard is elsewhere
        (`progress.worth_recalling`), say in the hub it woke in after a defeat and recharged in: Recall Location
        instead of the walk back. A mark the button no longer names (marked over, or gone) is forgotten; after a
        failed Recall (cooling down), the wizard walks for a minute before trying again."""
        marked_in = self.record.marked_in
        if (time.monotonic() < self._no_recall_until or marked_in is None or not self.travel_allowed_in(marked_in)
                or not worth_recalling(state["zone"], goal.get("destination_zone"), marked_in, state["mana"],
                                       self.record.mark_door_for)):
            return None
        if await recall_tip(self.client) != self.record.mark_tip:
            self.events.emit("travel", f"the Recall button no longer names the mark in {marked_in}; forgetting it")
            self.record.marked_in = self.record.mark_tip = None
            return None
        started = time.monotonic()
        problem = await recall(self.client)
        if problem is not None:
            self._no_recall_until = time.monotonic() + 60.0
            self.events.emit("travel", f"could not recall to the mark in {marked_in}: {problem}; walking instead")
            self.forget_a_mark_out_of_reach(problem)
            return None
        self._teleport_pressed = (RECALL, started)
        self.events.emit("travel", f"recalled from {state['zone']} to the mark in {marked_in}, the goal's zone, with "
                                   f"{state['mana']} mana")
        self.record.last_place = None
        return progressed("recalled toward the goal", zone=marked_in)

    async def back_from_the_commons_turn(self, state: dict) -> dict | None:
        """After a trip to the Commons: refill there (mana wisps, then the walking wisp search, as in any zone without
        enemies; health comes back while walking), and Recall Location once `progress.ready_to_recall`. Ready to go
        back ends the refill after a heavy fight: left set, it sent the wizard to the Commons again after the next
        fight, which cost 244 of 1164 and left 889 (16:07).
        None when no spot is marked or the wizard is where it was marked."""
        if self._marked_in is None or state["zone"] == self._marked_in:
            self._marked_in = None
            return None
        if self.ready_to_go_back(state):
            self.record.refill_after_heavy_fight = False
            return await self.recall_turn(state)
        if not ready_to_recall(mana_fraction(state), None):
            if (fetched := await self.wisp_turn("mana", state, reach=refill_reach(True))) is not None:
                return fetched
            return await self.safe_zone_refill_turn("mana", state, await self.planner())
        return await self.keep_looking_turn("health", state, await self.planner())

    def ready_to_go_back(self, state: dict) -> bool:
        """`progress.ready_to_recall`, or, for a trip made for health, health ready and the mana the way back uses
        (Recall and the TRAVEL_MANA_RESERVE kept for fights); or, after RECALL_WAIT_CAP_SECONDS in the Commons, health
        ready and that mana. After a heavy fight's trip the wizard chased seven used-up mana wisps in the Commons at
        70 of 96 mana and full health, short of the 80% a mana trip waits for (14:16 to 14:18)."""
        if ready_to_recall(mana_fraction(state), health_fraction(state)):
            return True
        if not ready_to_recall(None, health_fraction(state)):
            return False
        enough = isinstance(state["mana"], int) and state["mana"] >= RECALL_MANA_NEEDED + TRAVEL_MANA_RESERVE
        waited = time.monotonic() - self._trip_started >= RECALL_WAIT_CAP_SECONDS
        return enough and (self._trip_stat == "health" or waited)

    async def recall_turn(self, state: dict) -> dict | None:
        """Recall Location to the spot marked before leaving. Recall costs about 5 mana. None when nothing is
        marked or the wizard is where it was."""
        marked_in = self._marked_in
        if marked_in is None:
            return None
        if state["zone"] == marked_in or not await has_mark(self.client):
            self._marked_in = None
            return None
        started = time.monotonic()
        problem = await recall(self.client)
        self._marked_in = None
        if problem is not None:
            self.events.emit("travel", f"could not recall to {marked_in}: {problem}; the quest walk goes on")
            return stalled("could not recall", problem=problem)
        self._teleport_pressed = (RECALL, started)
        self.events.emit("travel", f"recalled to the spot marked in {marked_in}, with {state['mana']} mana")
        self.record.last_place = None
        return progressed("recalled to the marked spot", zone=marked_in)

    async def leave_for_wisps_turn(self, stat: str, state: dict, planner: RoutePlanner) -> dict | None:
        return await self.exit_turn(planner, stat, f"{state[stat]} of {state['max_' + stat]} {stat} and no {stat} "
                                                   f"wisp in sight", f"walk to the exit for {stat}")

    async def leave_for_safety_turn(self, state: dict) -> dict | None:
        """While a run finishes (`finish_safely`), walk out of a zone where enemies were met through its nearest exit,
        which leads back toward the hub, rather than playing on among them. None when no enemy was met here or the
        zone has no exit."""
        if state["zone"] not in self.record.zones_with_enemies:
            return None
        return await self.exit_turn(await self.planner(), "run", "finishing among enemies", "walk to the exit to stop")

    async def exit_turn(self, planner: RoutePlanner, kind: str, why: str, did: str) -> dict | None:
        """Walk to the middle of the zone's nearest exit volume, and through it once inside its radius. None when the
        zone has none. Cyclops Lane's exit is 336 units across: a walk that stopped at its edge counted as arrived,
        and with the door step kept for within WAYPOINT_ARRIVE_RADIUS of the middle, the wizard stood at the edge
        until the run stopped for turns without progress."""
        exits = [volume for volume, _ in planner.teleports if EXIT_WORD in volume.name.lower()]
        if not exits:
            return None
        me = await self.client.body.position()
        door = min(exits, key=lambda volume: flat_distance(me, volume.point))
        self.events.emit(kind, f"{why}; leaving through {door.name}")
        if flat_distance(me, door.point) <= max(WAYPOINT_ARRIVE_RADIUS, door.radius):
            return await self.zone_door_turn(XYZ(door.x, door.y, door.z))
        return await self.travel_turn(did, XYZ(door.x, door.y, door.z), arrive_radius=WAYPOINT_ARRIVE_RADIUS,
                                      avoid=await nearby_enemies(self.client))

    async def explore_for_wisps_turn(self, stat: str, state: dict, planner: RoutePlanner, *, reach: float,
                                     again: bool = True) -> dict | None:
        """Walk to the nearest part of the zone not explored for this kind of wisp yet, stopping as soon as an
        untried one loads within `reach`, the distance the refill fetches from (`targets.refill_reach`). Once every
        part has been seen, start over, since used-up wisps come back; or, with `again` false, None. Parts reached
        only through a door not known to stay in the zone are skipped (`area_to_search`). A part a players' fight or
        a crowd of enemies keeps the walk from counts as seen: in Colossus Boulevard one players' fight held the
        search at its point for wait after wait (12:45)."""
        kind = HEALTH_WISP if stat == "health" else MANA_WISP
        explored = self.record.explored.setdefault(f"{state['zone']}|{kind}s", [])
        me = await self.client.body.position()
        area = self.area_to_search(planner, state["zone"], me, explored)
        if area is None and not again:
            return None
        if area is None:
            explored.clear()
            area = self.area_to_search(planner, state["zone"], me, explored)
        if area is None:
            return stalled(f"too little {stat} for the fight, and no part of this zone to look for {kind}s in")
        (x, y), _ = area
        self.events.emit(stat, f"{state[stat]} of {state['max_' + stat]} {stat}, no {kind} in sight; looking at "
                               f"({x:.0f}, {y:.0f})")

        async def wisp_in_sight():
            enemies, circles = await surroundings(self.client)
            found = safe_wisps(await wisps(self.client, kind), me=await self.client.body.position(),
                               enemies=enemies, duel_circles=circles, tried=self.recently_tried_wisps(),
                               reach=reach)
            return f"{kind} in sight" if found else None

        turn = await self.travel_turn(f"explore for {kind}s", XYZ(x, y, 0.0), arrive_radius=WAYPOINT_ARRIVE_RADIUS * 3,
                                      also=wisp_in_sight, avoid=await nearby_enemies(self.client))
        if turn.get("trip", {}).get("reason") in (None, f"{kind} in sight", "every route method failed",
                                                  DUEL_BLOCKS_THE_WAY, ENEMIES_IN_THE_WAY):
            explored.append((round(x), round(y)))
        if turn.get("trip", {}).get("reason") == "every route method failed":
            self.note_a_dead_search_point(state["zone"], (round(x), round(y)))
        return turn

    def note_a_dead_search_point(self, zone: str, point: tuple[int, int]) -> None:
        """A search point whose walk failed every route method SEARCH_POINT_FAILURES_TO_DROP times is left out of the
        zone's wisp searches from then on, in this run and later ones: in the Commons the walk to (-3339, -2516) got
        stuck for about 50 s on each of three refills (15:35, 16:02, 16:14)."""
        key = (zone, point)
        self._search_point_failures[key] = self._search_point_failures.get(key, 0) + 1
        dead = self.record.dead_search_points.setdefault(zone, [])
        if self._search_point_failures[key] >= SEARCH_POINT_FAILURES_TO_DROP and point not in dead:
            dead.append(point)
            self.events.emit("knowledge", f"dropped the search point ({point[0]}, {point[1]}) in {zone}: its walk "
                                          f"failed {SEARCH_POINT_FAILURES_TO_DROP} times")

    def area_to_search(self, planner: RoutePlanner, zone: str, me, explored: list):
        """`targets.area_in_zone`: a part of the zone reached without a teleport volume not known to stay in it."""
        outcomes, failed = self.record.teleport_outcomes.get(zone, {}), self.record.failed_gaps.get(zone, [])

        def leaves_the_zone(point) -> bool:
            way = planner.way_across(me, XYZ(point[0], point[1], 0.0), outcomes, failed)
            return isinstance(way, TeleportVolume) and not isinstance(outcomes.get(way.name), int)

        dead = [tuple(point) for point in self.record.dead_search_points.get(zone, [])]
        seen = [*explored, *dead]
        area = area_in_zone(planner.exploration_points, me=(me.x, me.y), explored=seen, leaves_the_zone=leaves_the_zone)
        explored.extend(seen[len(explored) + len(dead):])
        return area

    async def persona_turn(self, arrow, goal: dict) -> dict:
        """Walk to the arrow's NPC and talk. A talk that leaves the goal open reached the wrong NPC: it is not
        progress, and the next try walks right up to the arrow instead of trusting the interact prompt."""
        if await near_npc(self.client, arrow):
            earlier_failures = self.record.talks_leaving_goal_open.get(str(goal.get("id")), 0)
            record = {}
            result = await talk(self.client, arrow, record, self.offer_policy, trust_prompt=earlier_failures == 0)
            self.record.dialog_log.append(record)
            self.note_dialog(record, result)
            if result == OFFER_LEFT_FOR_OPERATOR:
                raise StopRun(result)
            if result != DIALOG_FINISHED:
                return stalled("talk", result=result)
            if await self.goal_still_open(goal):
                self.record.talks_leaving_goal_open[str(goal.get("id"))] = earlier_failures + 1
                self.events.emit("talk", "the talk left the goal open, so it reached another NPC; "
                                         "next try walks right up to the quest arrow")
                return stalled("talk", result="the goal is still open")
            return progressed("talk", result=result)
        return await self.travel_turn("travel to quest NPC", arrow, arrive_radius=NPC_ARRIVE_DISTANCE / 2,
                                      also=self.arrival_check(arrow), avoid=await nearby_enemies(self.client))

    async def recharge_first_turn(self, state: dict) -> dict | None:
        """For a goal handled before the usual refills (a scavenge goal): recharge after a defeat or below
        HEALTH_TO_TRAVEL_FRACTION, and refill mana below the travel line, as any other goal would (outside a tower or a
        dungeon refilled in place). Searching Cyclops Lane for Mist Wood, the wizard went on at 409 of 1133 among its
        Cyclops (08:51)."""
        if in_dungeon(state["zone"], self.record.entered_with_x) and not self.travel_allowed_in(state["zone"]):
            return None
        if not health_to_travel(health_fraction(state)):
            self.record.recharging = True
        refill = still_to_recharge(health_fraction(state), mana_fraction(state)) if self.record.recharging else None
        self.record.recharging = refill is not None
        if refill is None and not mana_to_travel(mana_fraction(state)):
            refill = "mana"
        return None if refill is None else await self.refill_turn(refill, state)

    async def scavenge_turn(self, goal: dict, state: dict) -> dict:
        """A scavenge goal: get a reagent ("Mist Wood", the goal's item) wherever it grows; its goal shows no arrow.
        Walk to the nearest one loaded (`targets.is_reagent`) and use it with X, as a quest object; with none in
        sight, go first to a zone it is known or said to grow in, then search this zone, then the next open zone of
        the world not yet searched for it. Cyclops Lane, not on Mist Wood's list, was searched point by point for ten
        minutes among its Cyclops, each fight sending the wizard back to the same point (08:43 to 08:56)."""
        reagent = await self.reagent_name(goal)
        if reagent == PHOTO_ITEM:
            return await self.photo_turn(goal, state)
        if (await game_language().text(goal.get("name_key")) or "").strip().lower() == PHOTO_OF:
            return await self.photo_of_turn(reagent, goal, state)
        if is_essence(reagent) and self.edit_deck:
            return await self.essence_turn(reagent, state)
        if is_essence(reagent):
            return await self.park_the_active_quest(f"{reagent} is collected with an Extract spell cast on an enemy in "
                                                    "battle, which the bot does not do yet")
        zone = state["zone"]
        seen = sorted({found["name"].rsplit("_", 1)[0] for found in await objects_named(self.client, looks_like_a_reagent)})
        if seen:
            self.say_once("reagents", f"reagents seen in {zone}: {', '.join(seen)}")
        recent = {gathered for gathered, at in self._gathered if time.monotonic() - at < GATHERED_FORGET_SECONDS}
        found = [found for found in await objects_named(self.client, lambda name: is_reagent(name, reagent))
                 if found["id"] not in recent]
        me = await self.client.body.position()
        if found:
            self.record.reagent_searched.pop(reagent, None)
            if found_in(self.record.reagent_zones, reagent, zone):
                self.events.emit("gather", f"{reagent} grows in {zone}: kept as the first zone to look in for it")
            target = min(found, key=lambda found: flat_distance(me, found["position"]))
            if flat_distance(me, target["position"]) <= OBJECT_USE_DISTANCE:
                return await self.gather_turn(reagent, target)
            return await self.travel_turn(f"walk to {reagent}", target["position"], arrive_radius=OBJECT_USE_DISTANCE / 2,
                                          avoid=await nearby_enemies(self.client))
        planner = await self.planner()
        known = self.record.reagent_zones.get(reagent, [])
        searched = self.record.reagent_searched.setdefault(reagent, [])
        if self.record.clearing_world and len(searched) >= REAGENT_ZONES_PER_TRY:
            return await self.park_for_the_reagent(reagent, searched)
        if known and zone not in known and any(other not in searched for other in known):
            return await self.next_zone_for_reagent_turn(reagent, zone, planner)
        explored = self.record.explored.setdefault(f"{zone}|{reagent}", [])
        if (area := self.area_to_search(planner, zone, me, explored)) is not None:
            (x, y), _ = area

            async def reagent_in_sight():
                return f"{reagent} in sight" if await objects_named(self.client, lambda name: is_reagent(name, reagent)) else None

            self.say_once("gather", f"no {reagent} in sight in {zone}; looking at ({x:.0f}, {y:.0f})")
            turn = await self.travel_turn(f"look for {reagent}", XYZ(x, y, 0.0), arrive_radius=WAYPOINT_ARRIVE_RADIUS * 3,
                                          also=reagent_in_sight, avoid=await nearby_enemies(self.client))
            if turn.get("trip", {}).get("reason") in (None, f"{reagent} in sight", "every route method failed",
                                                      DUEL_BLOCKS_THE_WAY, ENEMIES_IN_THE_WAY):
                explored.append((round(x), round(y)))
            return turn
        return await self.next_zone_for_reagent_turn(reagent, zone, planner)

    async def photo_turn(self, goal: dict, state: dict) -> dict:
        """A scavenge goal for "Photomancy": a photo taken in the goal's zone ("Say Cheese!": "Practice Photomancy" in
        Golem Court; Annie: "Just press 'Z' and take a Photo right here"). Walk there, door by door; there, where it is
        safe, take a photo (`photomancy.take_photo`), and see whether the goal closed. PHOTO_TRIES photos a run."""
        zone, target = state["zone"], goal.get("destination_zone") or state["zone"]
        if zone != target:
            planner = await self.planner()
            way = way_toward_zone(zone, target, [volume.name for volume, _ in planner.teleports])
            door = None if way is None else self.door_on_the_way(way, planner)
            if door is None:
                return await self.park_the_active_quest(f"no way is known to {target}, where its photo is to be taken")
            self.say_once("photo", f"the goal asks for a photo in {target}: going there")
            return await self.walk_to_door_turn(f"walk toward {target} for a photo", *door)
        if self._photos_taken >= PHOTO_TRIES:
            return await self.park_the_active_quest(f"{PHOTO_TRIES} photos in {zone} left the goal open")
        if not await self.safe_here():
            return stalled("waiting for a safe moment for a photo")
        self._photos_taken += 1
        result = await take_photo(self.client)
        self.events.emit("photo", f"{result} in {zone}")
        if result == BOX_SHOWN:
            raise StopRun("a message box showed after the photo; left for the operator")
        if result == TOOK and not await self.goal_still_open(goal):
            return progressed("took a photo for the quest")
        return stalled("photo", result=result)

    async def photo_of_turn(self, subject: str, goal: dict, state: dict) -> dict:
        """A "Take Photo of" goal ("Ready, Aim, Shoot!": Mr. Lincoln in Ravenwood, Hilda Brewer in the Commons,
        Sergeant Muldoon in Olde Town): walk to the goal's zone, find the subject among the loaded entities by the name
        the game shows, walk within PHOTO_DISTANCE, face it, and take the photo while the Viewfinder names it in its
        frame (`photomancy.take_photo`). With the subject not in sight, the zone is searched for it."""
        zone, target = state["zone"], goal.get("destination_zone") or state["zone"]
        planner = await self.planner()
        if zone != target:
            way = way_toward_zone(zone, target, [volume.name for volume, _ in planner.teleports])
            door = None if way is None else self.door_on_the_way(way, planner)
            if door is None:
                return await self.park_the_active_quest(f"no way is known to {target}, where {subject} is to be "
                                                        "photographed")
            self.say_once("photo", f"a photo of {subject} in {target}: going there")
            return await self.walk_to_door_turn(f"walk toward {target} for a photo of {subject}", *door)
        where = await self.named_entity(subject)
        me = await self.client.body.position()
        if where is None:
            explored = self.record.explored.setdefault(f"{zone}|photo {subject}", [])
            area = self.area_to_search(planner, zone, me, explored)
            if area is None:
                return await self.park_the_active_quest(f"{subject} was not found in {zone} for the photo")
            (x, y), _ = area

            async def subject_in_sight():
                return f"{subject} in sight" if await self.named_entity(subject) is not None else None

            self.say_once("photo", f"{subject} not in sight in {zone}; looking at ({x:.0f}, {y:.0f})")
            turn = await self.travel_turn(f"look for {subject}", XYZ(x, y, 0.0), arrive_radius=WAYPOINT_ARRIVE_RADIUS * 3,
                                          also=subject_in_sight, avoid=await nearby_enemies(self.client))
            if turn.get("trip", {}).get("reason") in (None, f"{subject} in sight", "every route method failed",
                                                      DUEL_BLOCKS_THE_WAY, ENEMIES_IN_THE_WAY):
                explored.append((round(x), round(y)))
            return turn
        if flat_distance(me, where) > PHOTO_DISTANCE:
            return await self.travel_turn(f"walk toward {subject} for a photo", where, arrive_radius=PHOTO_DISTANCE / 2,
                                          avoid=await nearby_enemies(self.client))
        if self._photos_taken >= PHOTO_SUBJECT_TRIES:
            return await self.park_the_active_quest(f"{PHOTO_SUBJECT_TRIES} tries at a photo of {subject} left the "
                                                    "goal open")
        if not await self.safe_here() and not await self.no_enemy_within(DECK_EDIT_CLEARANCE):
            return stalled(f"waiting for a safe moment for a photo of {subject}")
        self._photos_taken += 1
        await face(self.client, where)
        result = await take_photo(self.client, subject)
        self.events.emit("photo", f"{result} ({subject}, {flat_distance(me, where):.0f} away) in {zone}")
        if result == BOX_SHOWN:
            raise StopRun("a message box showed after the photo; left for the operator")
        if result == NOT_IN_FRAME:
            return await self.travel_turn(f"step closer to {subject}", where, arrive_radius=PHOTO_DISTANCE / 4)
        if result == TOOK and not await self.goal_still_open(goal):
            self._photos_taken = 0
            return progressed(f"took a photo of {subject}")
        return stalled("photo", result=result)

    async def named_entity(self, name: str):
        """The position of the nearest loaded entity the game shows by `name` (an NPC's display name), or None."""
        me = await self.client.body.position()
        found = []
        for entity in await or_default(self.client.get_base_entity_list(), []):
            try:
                code = await display_code(entity)
                if code and (await self.text_of_code(code)).strip().lower() == name.strip().lower():
                    found.append(await entity.location())
            except Exception:
                continue
        return min(found, key=lambda where: flat_distance(me, where), default=None)

    async def text_of_code(self, code: str) -> str:
        if code not in self._enemy_names:
            self._enemy_names[code] = await game_language().text(code) or ""
        return self._enemy_names[code]

    def essence_enemies(self) -> set[str]:
        """The enemies whose essence an open quest goal needs, for the combat policy (`policy.extract_essence`)."""
        return {essence_enemy(item) for item in self.record.essence_quests.values()}

    async def forget_a_finished_essence(self, quest: dict, goals: list[dict]) -> None:
        """The active quest needed an essence and no open goal of it does now: the Extract spell can leave the deck."""
        title = " ".join((quest.get("title") or "").split())
        if title not in self.record.essence_quests:
            return
        items = [await game_language().text(goal["item_code"]) or "" for goal in goals
                 if goal.get("type") == "scavenge" and goal.get("item_code")]
        if not any(is_essence(item) for item in items):
            item = self.record.essence_quests.pop(title)
            self.events.emit("deck", f"{title} needs no {item} any more; the deck is planned again without it")

    async def essence_turn(self, essence: str, state: dict) -> dict:
        """A scavenge goal for an essence ("Lost Soul Essence"), taken in battle. With `--edit-deck` the quest is kept as
        one needing it (`Knowledge.essence_quests`), so an Extract spell goes into the deck (`deck_turn`) and the combat
        policy enchants a damage spell with it and hits the enemy the essence is named for (`policy.extract_essence`).
        The wizard goes to a zone that enemy was fought in (`Knowledge.enemy_zones`), door by door, and walks into one
        (`combat.approach`); with none in sight it searches the zone. Gilda Burke: "Start with the Lost Souls on
        Unicorn Way. Extract one Lost Soul Animus"."""
        title = " ".join(((self.record.quest or {}).get("title") or "").split())
        enemy, zone = essence_enemy(essence), state["zone"]
        if title and self.record.essence_quests.get(title) != essence:
            self.record.essence_quests[title] = essence
            self.events.emit("deck", f"{title} needs {essence}, taken from a {enemy} in battle with an Extract spell; "
                                     "the deck is planned again with it")
            return progressed("noted a quest that needs an essence", quest=title)
        if not await self.deck_holds_an_extract():
            if self._deck_checked is not None and self._deck_checked[1] == tuple(sorted(self.record.essence_quests)):
                return await self.park_the_active_quest(f"{essence} needs an Extract spell in the deck, and the deck "
                                                        "edit did not put one in")
            self.say_once("deck", f"{essence} needs an Extract spell in the deck; the deck is edited at the first safe "
                                  "place on the way")
        zones = self.record.enemy_zones.get(enemy, [])
        planner = await self.planner()
        if zone not in zones:
            for other in sorted(zones, key=lambda other: zone_hops(self.record.zone_links, zone, other) or 99):
                way = way_toward_zone(zone, other, [volume.name for volume, _ in planner.teleports])
                door = None if way is None else self.door_on_the_way(way, planner)
                if door is not None:
                    self.say_once("gather", f"{essence}: going to {other}, where {enemy}s were fought")
                    return await self.walk_to_door_turn(f"walk toward {other} for a {enemy}", *door)
            return await self.park_the_active_quest(f"no way is known to a zone where a {enemy} was fought, for "
                                                    f"{essence}")
        enemies = await nearby_enemies(self.client)
        targets = [found for found in enemies if not found["in_a_duel"] and await self.enemy_name(found) == enemy]
        in_reach = [target for target in targets if target["distance"] <= TARGET_REACH]
        if in_reach:
            result = await approach(self.client, in_reach[0])
            did = f"approached a {enemy} for {essence}"
            return progressed(did) if result["ok"] else stalled(did, reason=result.get("reason"))
        if targets:
            return await self.travel_turn(f"walk toward a {enemy}", targets[0]["position"],
                                          arrive_radius=TARGET_REACH / 2, avoid=bystanders(enemies, targets),
                                          ignore=targets)
        me = await self.client.body.position()
        explored = self.record.explored.setdefault(f"{zone}|{enemy}", [])
        area = self.area_to_search(planner, zone, me, explored)
        if area is None:
            explored.clear()
            area = self.area_to_search(planner, zone, me, explored)
        if area is None:
            return stalled(f"no part of {zone} to look for a {enemy} in")
        (x, y), _ = area

        async def enemy_in_sight():
            for found in await nearby_enemies(self.client):
                if not found["in_a_duel"] and await self.enemy_name(found) == enemy:
                    return f"{enemy} in sight"
            return None

        self.say_once("gather", f"no {enemy} in sight in {zone}; looking at ({x:.0f}, {y:.0f})")
        turn = await self.travel_turn(f"look for a {enemy}", XYZ(x, y, 0.0), arrive_radius=WAYPOINT_ARRIVE_RADIUS * 3,
                                      also=enemy_in_sight, avoid=enemies)
        if turn.get("trip", {}).get("reason") in (None, f"{enemy} in sight", "every route method failed",
                                                  DUEL_BLOCKS_THE_WAY, ENEMIES_IN_THE_WAY):
            explored.append((round(x), round(y)))
        return turn

    async def enemy_name(self, enemy: dict) -> str:
        """An enemy's name as the game shows it ("Lost Soul"), from its display code, kept once read."""
        code = enemy.get("display_code")
        if not code:
            return ""
        if code not in self._enemy_names:
            self._enemy_names[code] = await game_language().text(code) or ""
        return self._enemy_names[code]

    def spell_catalog(self) -> SpellCatalog:
        if self._spell_catalog is None:
            self._spell_catalog = SpellCatalog(game_language())
        return self._spell_catalog

    async def deck_holds_an_extract(self) -> bool:
        deck = await or_default(deck_spells(self.client), {})
        for template_id in deck:
            if role_of((await self.spell_catalog().describe(template_id)).effects) == EXTRACT:
                return True
        return False

    async def deck_turn(self, state: dict) -> dict | None:
        """With `--edit-deck` (the operator, 2026-10-28, 13:45 UTC: "Yes, bot can edit decks."): when the spells known
        or the quests needing an essence have changed, and only where it is safe (`safe_here`; never in a dungeon or
        tower), open the Deck page and make the deck what `decks.wanted_deck` wants, a card at a time, each click
        checked (`deckpage`) and each card logged with its reason and the deck's size before and after
        (`decks.DeckLog`), then close the book. The deck's capacity comes from the game: until it is known for this
        deck, the first card wanted is put in, and the add the page refuses gives it (`learn_capacity`). None when
        there is nothing to do here."""
        key = (tuple(sorted(self.record.known_spells)), tuple(sorted(self.record.essence_quests)))
        if key == self._deck_checked or time.monotonic() < self._deck_retry_at:
            return None
        if in_dungeon(state["zone"], self.record.entered_with_x):
            return None
        if self.record.recharging or not health_to_travel(health_fraction(state)):
            return None
        if not await self.safe_here() and not await self.no_enemy_within(DECK_EDIT_CLEARANCE):
            return None
        self._deck_checked = key
        essence_needed = bool(self.record.essence_quests)
        try:
            await open_deck_page(self.client)
            view = before = await read_deck_page(self.client)
            capacity = self.record.deck_capacity.get(view.name)
            if capacity is None:
                view, capacity = await self.learn_capacity(view, essence_needed, state)
            spells, names = await self.deck_spells_of(view)
            ids = {name: template_id for template_id, name in names.items()}
            for change in plan_changes(spells, wanted_deck(spells, capacity, essence_needed=essence_needed)):
                view = await self.carry_out(change, ids[change.name], view, state)
        except (DeckEditStopped, LookupError) as stopped:
            self._deck_checked, self._deck_retry_at = None, time.monotonic() + DECK_RETRY_SECONDS
            self.events.emit("deck", f"the deck edit stopped: {stopped}; trying again in {DECK_RETRY_SECONDS:.0f} s")
            return stalled("deck edit stopped", reason=str(stopped))
        finally:
            await close_book(self.client)
        _, names = await self.deck_spells_of(view)
        if view.cards == before.cards:
            self.events.emit("deck", f"{view.name}, {view.size} cards, is as wanted: {self.deck_text(view, names)}")
            return None
        self.events.emit("deck", f"{view.name}: {before.size} cards before ({self.deck_text(before, names)}), "
                                 f"{view.size} after ({self.deck_text(view, names)})")
        return progressed("edited the deck", before=before.size, after=view.size)

    async def learn_capacity(self, view, essence_needed: bool, state: dict):
        """Put in, one at a time, the first card wanted that is missing, until the Deck page refuses one: the deck
        holds as many cards as it has then, kept for this deck (`Knowledge.deck_capacity`). When nothing more is
        wanted, the capacity stays unknown and the plan has room for everything."""
        while True:
            spells, names = await self.deck_spells_of(view)
            wanted = wanted_deck(spells, NO_CAPACITY_KNOWN, essence_needed=essence_needed)
            missing = first_missing(spells, wanted)
            if missing is None:
                return view, NO_CAPACITY_KNOWN
            template_id = next(template_id for template_id, name in names.items() if name == missing)
            if await add_copy(self.client, template_id) == REFUSED:
                self.record.deck_capacity[view.name] = view.size
                self.events.emit("deck", f"{view.name} holds {view.size} cards: the Deck page refused {missing} at "
                                         f"{view.size}")
                return view, view.size
            after = await read_deck_page(self.client)
            reason = next(want.reason for want in wanted if want.name == missing)
            self.note_deck_change(DeckChange(ADD, missing, 1, f"{reason} (put in while the deck's capacity was not "
                                                              "known)"), view, after, state)
            view = after

    async def carry_out(self, change: DeckChange, template_id: int, view, state: dict):
        if change.action == KEEP:
            self.note_deck_change(change, view, view, state)
            return view
        if change.action == REMOVE:
            await take_out_copy(self.client, template_id)
        elif await add_copy(self.client, template_id) == REFUSED:
            self.record.deck_capacity[view.name] = view.size
            raise DeckEditStopped(f"the Deck page refused {change.name} at {view.size} cards; {view.name} holds "
                                  f"{view.size}, kept for the next plan")
        after = await read_deck_page(self.client)
        self.note_deck_change(change, view, after, state)
        return after

    def note_deck_change(self, change: DeckChange, before, after, state: dict) -> None:
        self.deck_log.add(change, deck_before=before.size, deck_after=after.size, level=state["level"], zone=state["zone"])
        self.events.emit("deck", f"{change_text(change)} ({before.size} -> {after.size} cards)")

    async def deck_spells_of(self, view) -> tuple[list, dict[int, str]]:
        """The Deck page's spells as `decks.DeckSpell`s, named and described from the game's files, and their names by
        template ID."""
        spells, names = [], {}
        for entry in view.spells:
            spell = await self.spell_catalog().describe(entry.template_id)
            names[entry.template_id] = spell.name or f"spell {entry.template_id}"
            spells.append(deck_spell(names[entry.template_id], view.copies_of(entry.template_id), entry.limit,
                                     spell.effects, spell.pips))
        return spells, names

    @staticmethod
    def deck_text(view, names: dict[int, str]) -> str:
        counts = {}
        for card in view.cards:
            counts[names.get(card, f"spell {card}")] = counts.get(names.get(card, f"spell {card}"), 0) + 1
        return ", ".join(f"{name} x{count}" for name, count in counts.items())

    async def park_for_the_reagent(self, reagent: str, searched: list[str]) -> dict:
        """While clearing a world, a scavenge quest whose reagent was not found in REAGENT_ZONES_PER_TRY zones is
        parked until the next level, and its reagent kept as wanted: the Quest Finder's other givers go on, a wanted
        reagent seen on the way is a detour (`reagent_detour_turn`), and the quest is tried once more at the end of the
        world's clearing. Mist Wood was not found in Cyclops Lane, Unicorn Way or the Commons in 40 minutes."""
        self.record.reagent_searched.pop(reagent, None)
        turn = await self.park_the_active_quest(f"no {reagent} found in {', '.join(searched)}; gathering {reagent} when "
                                                "one is seen on the way, and trying again at the end of the world's quests")
        self.record.wanted_reagents[reagent] = turn["quest"]
        return turn

    async def park_the_active_quest(self, why: str, title: str | None = None) -> dict:
        """While clearing a world, the active quest is parked until the next level (`progress.parked`) and the world's
        other quests go on; otherwise the run stops for the operator. `title` when the turn has not yet noted the
        active quest (`record.quest`)."""
        title = " ".join((title or (self.record.quest or {}).get("title") or "").split())
        level = (await snapshot(self.client))["level"]
        if not self.record.clearing_world or not title or not isinstance(level, int):
            raise StopRun(f"{why}; left for the operator")
        self.record.parked_quests[title] = level
        self.events.emit("quest", f"parking {title} until the wizard is past level {level}: {why}")
        return progressed("parked a quest", quest=title)

    async def reagent_detour_turn(self, state: dict) -> dict | None:
        """A reagent a parked quest wants is in sight, near, with no enemy near it (`targets.worth_a_detour`): gather it,
        and make that quest one to do again. Not in a tower or dungeon, nor while recharging."""
        if not self.record.wanted_reagents or in_dungeon(state["zone"], self.record.entered_with_x) or self.record.recharging:
            return None
        wanted = {reagent: title for reagent, title in self.record.wanted_reagents.items()
                  if " ".join(title.split()) not in self.record.held_quests}
        recent = {gathered for gathered, at in self._gathered if time.monotonic() - at < GATHERED_FORGET_SECONDS}
        me = await self.client.body.position()
        enemies = await nearby_enemies(self.client)
        for reagent, title in list(wanted.items()):
            found = [found for found in await objects_named(self.client, lambda name: is_reagent(name, reagent))
                     if found["id"] not in recent]
            if not found:
                continue
            target = min(found, key=lambda found: flat_distance(me, found["position"]))
            distance = flat_distance(me, target["position"])
            if not worth_a_detour(distance, [flat_distance(enemy["position"], target["position"]) for enemy in enemies]):
                continue
            if distance > OBJECT_USE_DISTANCE:
                self.say_once("gather", f"{reagent} in sight in {state['zone']}, {distance:.0f} away: a detour for {title}")
                return await self.travel_turn(f"walk to {reagent}", target["position"], arrive_radius=OBJECT_USE_DISTANCE / 2,
                                              avoid=enemies)
            turn = await self.gather_turn(reagent, target)
            if turn["progress"]:
                found_in(self.record.reagent_zones, reagent, state["zone"])
                self.record.parked_quests.pop(title, None)
                self.record.wanted_reagents.pop(reagent, None)
                self.events.emit("gather", f"gathered {reagent} for {title}; it is a quest to do again")
            return turn
        return None

    async def reagent_name(self, goal: dict) -> str:
        code = goal.get("item_code")
        name = await game_language().text(code) if code else None
        if not name:
            raise StopRun(f"the scavenge goal names no item the game's text can name ({code}); left for the operator")
        return name

    async def gather_turn(self, reagent: str, target: dict) -> dict:
        """Use the reagent with X (`dialog.use_object`), then see whether it is gone: gathered."""
        record = {}
        result = await use_object(self.client, target["position"], record, self.offer_policy)
        await asyncio.sleep(GATHER_SETTLE_SECONDS)
        self._gathered.append((target["id"], time.monotonic()))
        still_there = any(found["id"] == target["id"]
                          for found in await objects_named(self.client, lambda name: is_reagent(name, reagent)))
        where = target["position"]
        self.events.emit("gather", f"{reagent} at ({where.x:.0f}, {where.y:.0f}): {result}; "
                                   f"{'still there' if still_there else 'gathered'}")
        return (stalled if still_there else progressed)(f"gather {reagent}", result=result)

    async def next_zone_for_reagent_turn(self, reagent: str, zone: str, planner: RoutePlanner) -> dict:
        """This zone was searched for the reagent: walk one door toward the nearest open zone of the world (not an
        interior, tower or dungeon) not yet searched for it: those it is known or said to grow in first
        (`targets.zones_to_search_for`), then the nearest by the zones walked between (`travelplan.zone_hops`)."""
        searched = self.record.reagent_searched.setdefault(reagent, [])
        if zone not in searched:
            searched.append(zone)
        if self.record.clearing_world and len(searched) >= REAGENT_ZONES_PER_TRY:
            return await self.park_for_the_reagent(reagent, searched)
        candidates = [other for other in self.record.zone_links
                      if world_of(other) == world_of(zone) and other not in searched and INTERIOR_WORD not in other
                      and not in_dungeon(other, self.record.entered_with_x)]
        reachable = [(hops, other) for other in candidates
                     if (hops := zone_hops(self.record.zone_links, zone, other)) is not None]
        for other in zones_to_search_for(self.record.reagent_zones, reagent, reachable):
            way = way_toward_zone(zone, other, [volume.name for volume, _ in planner.teleports])
            door = None if way is None else self.door_on_the_way(way, planner)
            if door is not None:
                self.say_once("gather", f"no {reagent} left to find in {zone}; going on to {other}")
                return await self.walk_to_door_turn(f"walk toward {other} for {reagent}", *door)
        if self.record.clearing_world:
            return await self.park_for_the_reagent(reagent, searched)
        raise StopRun(f"no {reagent} found in {', '.join(sorted(searched))}, and no way to another open zone of "
                      f"{world_of(zone)} is known; left for the operator")

    async def usage_turn(self, arrow, goal: dict) -> dict:
        """Walk to the quest object and use it. Progress only if an open goal was completed."""
        if await near_npc(self.client, arrow):
            goals_before = await self.open_goal_count()
            record = {}
            result = await use_object(self.client, arrow, record, self.offer_policy)
            if self._object_in_use is not None and close_enough(record.get("nudges", [])):
                self.record.visited_objects.append(self._object_in_use.key)
            self.record.dialog_log.append(record)
            if result == OFFER_LEFT_FOR_OPERATOR:
                raise StopRun(result)
            goals_after = await self.open_goal_count()
            completed = goals_before is not None and goals_after is not None and goals_after < goals_before
            return (progressed if completed else stalled)("use quest object", result=result, goals_left=goals_after)
        return await self.travel_turn("travel to quest object", arrow, arrive_radius=NPC_ARRIVE_DISTANCE / 2,
                                      also=self.arrival_check(arrow), avoid=await nearby_enemies(self.client))

    async def waypoint_turn(self, arrow, goal: dict) -> dict:
        """Walk to the arrow of a goal in another zone, or of an "Explore" goal that names none (walk to the spot, and
        only if the goal is still open when the wizard stands there, treat it as a door). A waypoint still open once
        the wizard stands at its arrow is a door: walk in. Towers and dungeons open with X wherever their interact
        prompt shows, which can be well short of the arrow, so within PROMPT_DOOR_REACH of it the prompt is answered with X, and the walk stops as
        soon as it shows. Sapphyra's Tower's door stands in a fenced courtyard the wizard cannot walk into; its
        prompt showed at the fence all the while the run stood there, until it stopped for turns without
        progress (the operator: "the prompt to press X has been open since you got stuck"). The way in was the
        tower's entrance semicircle ("Teleport Semi Circle 4 Player Generic"), outside the fence: when one is loaded
        within PROMPT_DOOR_REACH of the arrow, the wizard walks to it, then steps in and presses X."""
        here = await self.client.body.position()
        exploring = not leads_to_another_zone(goal, await self.client.zone_name())
        if exploring and flat_distance(here, arrow) > WAYPOINT_ARRIVE_RADIUS:
            return await self.travel_turn("explore toward the waypoint", arrow, arrive_radius=WAYPOINT_ARRIVE_RADIUS,
                                          avoid=await nearby_enemies(self.client))
        if await self.door_prompt_near(arrow):
            return await self.enter_with_x_turn()
        if flat_distance(here, arrow) <= WAYPOINT_ARRIVE_RADIUS:
            return await self.zone_door_turn(arrow)

        async def prompt_shows():
            return INTERACT_PROMPT if await self.door_prompt_near(arrow) else None

        entrance = await or_default(dungeon_entrance_near(self.client, arrow, PROMPT_DOOR_REACH), None)
        if entrance is not None and flat_distance(here, entrance) <= ENTRANCE_ARRIVE_RADIUS:
            return await self.zone_door_turn(entrance)
        if entrance is not None:
            self.events.emit("door", f"the way into {goal.get('destination_zone')} is an entrance semicircle at "
                                     f"({entrance.x:.0f}, {entrance.y:.0f}), {flat_distance(entrance, arrow):.0f} from the "
                                     "arrow; walking to it")
            return await self.travel_turn("walk to a tower or dungeon entrance", entrance,
                                          arrive_radius=ENTRANCE_ARRIVE_RADIUS, also=prompt_shows,
                                          avoid=await nearby_enemies(self.client))

        return await self.travel_turn("travel to waypoint", arrow, arrive_radius=WAYPOINT_ARRIVE_RADIUS,
                                      also=prompt_shows, avoid=await nearby_enemies(self.client))

    async def door_prompt_near(self, arrow) -> bool:
        """The interact prompt shows within PROMPT_DOOR_REACH of a door's arrow, it does not read "to Talk", and no
        friendly NPC is within NPC_PROMPT_RANGE, whose prompt it would be: in the Shopping District an NPC's prompt
        was taken for a door's, X did nothing, and 15 seconds went. In Ravenwood, Mr. Lincoln, who the entity list
        does not hold as an NPC, had a prompt reading "to Talk"; X opened his Training Point Buyback box, which took
        every click and stopped the run."""
        here = await self.client.body.position()
        if flat_distance(here, arrow) > PROMPT_DOOR_REACH or await attempt(self.client.is_in_npc_range()) is not True:
            return False
        zone = await self.client.zone_name()
        if any(where == zone and flat_distance(here, spot) <= NOT_A_DOOR_RADIUS for where, spot in self._not_doors):
            return False
        if prompt_is_not_a_doors(await or_default(interact_prompt_text(self.client), "")):
            return False
        npc = await or_default(nearest_npc(self.client), None)
        return npc is None or flat_distance(here, npc) > NPC_PROMPT_RANGE

    async def mark_at_the_door(self, zone: str) -> None:
        """At the door of a tower or dungeon (one entered with X), in the open zone outside it: Mark Location, with
        mana to spare, so a defeat inside, or any way back to the quest's goal inside, is a Recall to the door
        (`recall_toward_the_goal_turn`, `progress.worth_recalling`) instead of the walk from the hub: after the
        defeat at the Cyclops Lane dungeon's boss the way back was four zones on foot (01:27). The mark is for the
        active goal's zone; not pressed when one is already set here for it."""
        goal_zone = (self.record.quest or {}).get("goal_zone")
        if not self.travel_allowed_in(zone) or zone in self._unmarkable or goal_zone in (None, "", zone):
            return
        if self.record.marked_in == zone and self.record.mark_door_for == goal_zone:
            return
        if not spare_mana(await attempt(self.client.stats.current_mana())):
            return
        problem = await mark_here(self.client)
        if problem is not None:
            self._unmarkable.add(zone)
            self.events.emit("travel", f"could not mark the door in {zone}: {problem}")
            return
        self.record.marked_in, self.record.mark_tip = zone, await recall_tip(self.client)
        self._mark_position = await self.client.body.position()
        self.record.mark_purpose, self.record.mark_quest = AFTER_A_DEFEAT, None
        self.record.mark_door_for = goal_zone
        self.events.emit("travel", f"marked the door in {zone} before entering {goal_zone}, to recall to after a "
                                   "defeat or on the way back")

    async def enter_with_x_turn(self) -> dict:
        """Press X at a door's interact prompt and give the zone change a few seconds to start. When a dialog opens
        instead, the prompt was a person's: prompts within NOT_A_DOOR_RADIUS of that spot are not taken for a door
        again this run. By Olde Town's gate to Triton Lane, an NPC out of NPC_PROMPT_RANGE gave a side quest, and
        then the wizard pressed X at him again after every dialog until the run was stopped."""
        zone = await self.client.zone_name()
        here = await self.client.body.position()
        action = prompt_action(await or_default(interact_prompt_text(self.client), ""))
        await self.mark_at_the_door(zone)
        await tap(self.client, Keycode.X, TALK_KEY_SECONDS)
        self.events.emit("door", f"the interact prompt showed near a door into another zone (\"to {action}\"); "
                                 "pressed X to enter")
        deadline = time.monotonic() + DOOR_WAIT_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if await self.zone_changing(zone):
                self._entering_with_x_from = zone
                return progressed("entered with X at the interact prompt")
            if await dialog_open(self.client):
                self._not_doors.append((zone, xy(here)))
                self.events.emit("door", f"X at the interact prompt opened a dialog, not a door; prompts within "
                                         f"{NOT_A_DOOR_RADIUS:.0f} units of ({here.x:.0f}, {here.y:.0f}) are not taken "
                                         "for a door again")
                return progressed("pressed X at the interact prompt: a dialog opened")
            await asyncio.sleep(DOOR_POLL_SECONDS)
        return stalled("pressed X at the interact prompt, but the zone did not change")

    async def gap_turn(self, step: GapStep, zone: str, planner: RoutePlanner) -> dict:
        """Walk to the edge of the wizard's walkable piece where the goal's comes nearest (`RoutePlanner.gap_step`),
        then straight across. A step that does not land in the goal's piece is not tried again this run, and
        teleporters are looked for instead."""
        here = await self.client.body.position()
        gap = flat_distance(step.start, step.end)
        if flat_distance(here, step.start) > GAP_EDGE_RADIUS:
            self.events.emit("walk", f"the goal is in walkable piece {step.pieces[1]}, {gap:.0f} units across a gap "
                                     f"from piece {step.pieces[0]}; walking to its edge")
            return await self.travel_turn("walk to the edge of a gap", XYZ(*step.start, here.z),
                                          arrive_radius=GAP_EDGE_RADIUS, avoid=await nearby_enemies(self.client))
        turn = await face(self.client, XYZ(*step.end, here.z))
        if not turn["ok"]:
            return stalled("could not face across the gap", reason=turn["reason"])
        await tap(self.client, Keycode.W, (flat_distance(here, step.end) + GAP_OVERSHOOT) / WALK_UNITS_PER_SECOND)
        now = await self.client.body.position()
        landed = planner.piece_of((now.x, now.y))
        if landed == step.pieces[1]:
            self.events.emit("walk", f"stepped {gap:.0f} units across a gap into walkable piece {landed}")
            return progressed("stepped across a gap", gap=round(gap), piece=landed)
        self.record.failed_gaps.setdefault(zone, []).append(step.pieces)
        self.events.emit("walk", f"a step across a {gap:.0f}-unit gap toward piece {step.pieces[1]} ended in piece "
                                 f"{landed}; not trying it again")
        return stalled("stepped toward another walkable piece, but did not reach it", landed=landed)

    async def zone_door_turn(self, door) -> dict:
        """Walk into the door, then give the zone change a few seconds to start. Towers and dungeons open only
        with X: when the interact prompt shows at the door, press X once. No key goes to the game once the change
        has begun, since keys sent then are played again in the new zone (`doors`); the walk here may already have
        begun it."""
        zone = await self.client.zone_name()
        changing = partial(self.zone_changing, zone)
        if await change_begins(changing, CHANGE_START_SECONDS):
            self.events.emit("door", "the walk to the door had begun the zone change; pressed nothing more")
            return progressed("walked through a zone door", began_while_walking=True)
        turn = await face(self.client, door)
        if not turn["ok"]:
            if turn["reason"] == LOADING:
                return progressed("walked through a zone door", began_while_facing=True)
            return stalled("could not face the zone door", reason=turn["reason"])
        if await push_through(partial(tap, self.client, Keycode.W), changing):
            return progressed("walked through a zone door")
        pressed_x = False
        deadline = time.monotonic() + DOOR_WAIT_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if await changing():
                return progressed("walked through a zone door", pressed_x=pressed_x)
            if not pressed_x and await attempt(self.client.is_in_npc_range()) is True:
                await tap(self.client, Keycode.X, TALK_KEY_SECONDS)
                pressed_x = True
                self.events.emit("door", "the interact prompt showed at the door; pressed X to enter")
            await asyncio.sleep(DOOR_POLL_SECONDS)
        return stalled("walked into a zone door, but the zone did not change", pressed_x=pressed_x)

    async def zone_changing(self, zone) -> bool:
        return await attempt(self.client.is_loading()) is True or await attempt(self.client.zone_name()) != zone

    def arrival_check(self, arrow):
        async def arrived():
            return "arrived" if await near_npc(self.client, arrow) else None
        return arrived

    async def goal_still_open(self, goal: dict) -> bool:
        quest = await self.active_quest()
        return quest is not None and any(open_goal["id"] == goal.get("id") for open_goal in open_goals(quest))

    def mark_streets(self, planner: RoutePlanner, zone: str) -> None:
        """The patrol paths routes keep off (`planner.streets`): all of them but those earlier runs watched for
        VIEWS_TO_JUDGE samples without seeing an enemy on (`patrols.unwalked_paths`). The quest's target search
        keeps every path, since a quest's own enemies may appear only once it is under way."""
        if not planner.patrols:
            return
        unwalked = unwalked_paths(self.record.path_sightings.get(zone, {}), self.record.path_views.get(zone, {}))
        planner.streets = planner.patrols.without(unwalked)
        if ignored := unwalked & set(planner.patrols.paths):
            self.events.emit("knowledge", f"{len(ignored)} of {len(planner.patrols.paths)} patrol paths in {zone} "
                                          f"were watched {VIEWS_TO_JUDGE} times or more with no enemy on them; "
                                          "routes count them as sidewalk")

    def note_sightings(self, zone, enemies: list[dict], me, now: float) -> None:
        """Every PATH_SAMPLE_SECONDS while walking, count the patrol paths in view and those with an enemy on them
        (`patrols.note_sightings`), so later runs can tell the streets enemies walk from paths none does."""
        planner = self._planners.get(zone)
        if planner is None or not planner.patrols or now - self._sighted_at < PATH_SAMPLE_SECONDS:
            return
        self._sighted_at = now
        note_sightings(planner.patrols, self.record.path_sightings.setdefault(zone, {}),
                       self.record.path_views.setdefault(zone, {}), xy(me),
                       [xy(enemy["position"]) for enemy in enemies])

    async def open_goal_count(self) -> int | None:
        quest = await self.active_quest()
        return None if quest is None else len(open_goals(quest))

    async def planner(self) -> RoutePlanner:
        zone = await self.client.zone_name()
        if zone not in self._planners:
            self._planners[zone] = await load_planner(zone, self.settings.deimos_root)
            self._planners[zone].nav_first = zone in self.record.nav_first_zones
            self.mark_streets(self._planners[zone], zone)
            self.record.planner_status[zone] = self._planners[zone].status
        return self._planners[zone]

    async def travel_turn(self, did: str, destination, *, arrive_radius: float, also=None, avoid=(), ignore=(),
                          **details) -> dict:
        start = await self.client.body.position()
        zone = await self.client.zone_name()
        planner = await self.planner()
        way = planner.way_across(start, destination, self.record.teleport_outcomes.get(zone, {}),
                                 self.record.failed_gaps.get(zone, []))
        if isinstance(way, GapStep):
            return await self.gap_turn(way, zone, planner)
        if way is not None:
            return await self.teleport_turn(way, zone, planner)
        _, duel_circles = await surroundings(self.client)
        hazards, around = self.hazards_for(planner, zone, start, destination, arrive_radius, avoid=avoid,
                                           duel_circles=duel_circles)
        trip = await travel(self.client, planner, destination, arrive_radius=arrive_radius,
                            watch=self.watcher(also=also, ignore=ignore,
                                               reroute=self.rerouter(planner, hazards, destination)),
                            hazards=hazards)
        moved = flat_distance(start, await self.client.body.position())
        if trip.get("reason") == LOADING:
            self.note_hidden_door(zone, planner, destination, start)
        if nav_did_better(trip["attempts"]) and zone not in self.record.nav_first_zones:
            self.record.nav_first_zones.append(zone)
            planner.nav_first = True
            self.events.emit("walk", f"the collision walk data got stuck in {zone} where the nav graph walked on; "
                                     "routes there try the nav graph first from now on")
        blocking_duel = await self.duel_blocking_the_way(planner, hazards, destination, trip, moved)
        if blocking_duel is not None:
            trip["reason"] = DUEL_BLOCKS_THE_WAY
            self.record.duel_waits_in_a_row += 1
            self.events.emit("walk", f"{did}: another player's fight at ({blocking_duel[0]:.0f}, "
                                     f"{blocking_duel[1]:.0f}) is all that leaves no route; waiting for it to end "
                                     f"({self.record.duel_waits_in_a_row} of {self.record.limits.max_duel_waits_in_a_row})")
            await self.wait_for_duels_to_change(hazards.duel_circles)
        elif trip["reason"] == "every route method failed" and around and moved < BARELY_MOVED_DISTANCE:
            trip["reason"] = ENEMIES_IN_THE_WAY
            self.record.immobile_threat_stops_in_a_row += 1
            self.events.emit("walk", f"{did}: {len(around)} enemies leave no route that keeps away from where "
                                     f"they are going; waiting {ENEMIES_IN_THE_WAY_WAIT_SECONDS:.0f} s for them to move")
            await asyncio.sleep(ENEMIES_IN_THE_WAY_WAIT_SECONDS)
        elif trip["reason"] in PATH_THREATS and moved < BARELY_MOVED_DISTANCE:
            self.record.immobile_threat_stops_in_a_row += 1
            await asyncio.sleep(ENEMY_PASS_WAIT_SECONDS)
        else:
            self.record.immobile_threat_stops_in_a_row = 0
        if blocking_duel is None:
            self.record.duel_waits_in_a_row = 0
        trip_summary = {"result": trip["result"], "reason": trip["reason"], "moved": round(moved),
                        "methods": [(tried["method"], tried.get("result"), tried.get("reason"),
                                     tried.get("sidesteps"), tried.get("seconds")) for tried in trip["attempts"]]}
        new_obstacles = remember_obstacles(self.record, zone, trip["blocked_at"])
        methods = ", ".join(f"{tried['method']}: {tried.get('result')}{failure_text(tried)}{reroute_text(tried)}"
                            for tried in trip["attempts"])
        threat = (self.approaches.closest(time.monotonic(), NEAREST_ENEMIES_NOTED) or None
                  if trip["reason"] == "battle" else None)
        self.events.emit("walk", f"{did}: moved {moved:.0f}, {trip['result']}"
                                 f"{' (' + trip['reason'] + ')' if trip['reason'] else ''}; {methods}"
                                 f"{f'; {new_obstacles} new obstacles' if new_obstacles else ''}"
                                 f"{threat_text(threat)}", nearest_threat=threat)
        return travel_outcome(did, trip["reason"], moved, self.record, new_obstacles=new_obstacles,
                              trip=trip_summary, **details)

    async def duel_blocking_the_way(self, planner: RoutePlanner, hazards: Hazards, destination, trip: dict,
                                    moved: float) -> Point | None:
        """The duel circle nearest the wizard when the wizard barely moved and either every route method failed while a
        route exists without the circles, or the walk ended at once on "a duel is near the path ahead": another
        player's fight is on the way, not enemies. In the Pyramid's Hall the bounty targets stood by someone's
        fight, and each walk toward them ended where it began, every 2 to 3 seconds."""
        if moved >= BARELY_MOVED_DISTANCE or not hazards.duel_circles:
            return None
        here = await self.client.body.position()
        if trip["reason"] == DUEL_NEAR_PATH:
            return min(hazards.duel_circles, key=lambda circle: flat_distance(here, circle))
        if trip["reason"] != "every route method failed":
            return None
        if not planner.blocked_only_by_duels(here, destination, hazards):
            return None
        return min(hazards.duel_circles, key=lambda circle: flat_distance(here, circle))

    async def wait_for_duels_to_change(self, circles) -> None:
        """Stand still for up to DUEL_WAIT_SECONDS, ending early when the duel circles loaded are no longer the ones
        that blocked the way: a fight ended, or another began somewhere else."""
        blocking = {(round(circle[0]), round(circle[1])) for circle in circles}
        deadline = time.monotonic() + DUEL_WAIT_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            await asyncio.sleep(DUEL_WAIT_POLL_SECONDS)
            _, now = await or_default(surroundings(self.client), ([], []))
            if {(round(circle.x), round(circle.y)) for circle in now} != blocking:
                return

    async def teleport_turn(self, volume: TeleportVolume, zone: str, planner: RoutePlanner) -> dict:
        """Walk into a teleport volume, wait for the jump, and remember where it led: another piece of this
        zone, another zone, or nowhere. A volume that left the zone or did nothing is not tried again."""
        self.events.emit("teleporter", f"the target is in another walkable area of {zone}; walking into "
                                       f"{volume.name} at ({volume.x:.0f}, {volume.y:.0f})")
        before = await self.client.body.position()
        _, duel_circles = await surroundings(self.client)
        hazards, _ = self.hazards_for(planner, zone, before, volume.point, volume.radius / 3,
                                      avoid=await nearby_enemies(self.client), duel_circles=duel_circles)
        trip = await travel(self.client, planner, volume.point, arrive_radius=volume.radius / 3,
                            watch=self.watcher(also=self.jump_check(),
                                               reroute=self.rerouter(planner, hazards, volume.point)),
                            hazards=hazards)
        reached = trip["result"] == "arrived" or trip["reason"] in (TELEPORTED, "loading")
        if not reached:
            moved = flat_distance(before, await self.client.body.position())
            self.events.emit("teleporter", f"did not reach {volume.name}: {trip['result']} ({trip['reason']}); "
                                           "not judged, will be tried again")
            return travel_outcome("walk to a teleporter", trip["reason"], moved, self.record,
                                  trip={"result": trip["result"], "reason": trip["reason"], "moved": round(moved),
                                        "trails": [tried.get("trail") for tried in trip["attempts"]]})
        outcome = await self.teleport_outcome(zone, planner, already_jumped=trip["reason"] == TELEPORTED)
        self.record.teleport_outcomes.setdefault(zone, {})[volume.name] = outcome
        where = await self.client.body.position()
        self.events.emit("teleporter", f"{volume.name}: {describe_outcome(outcome)}, now at "
                                       f"({where.x:.0f}, {where.y:.0f})")
        return (stalled if outcome == NO_EFFECT else progressed)("walked into a teleporter", volume=volume.name,
                                                                  outcome=outcome)

    def jump_check(self):
        """For the walking watcher: report a teleport when the position jumps between two ticks."""
        last = [None]

        async def jumped():
            here = await self.client.body.position()
            moved_far = last[0] is not None and flat_distance(last[0], here) > JUMP_DISTANCE
            last[0] = here
            return TELEPORTED if moved_far else None
        return jumped

    async def teleport_outcome(self, zone: str, planner: RoutePlanner, *, already_jumped: bool):
        """Where a teleport volume led: LEFT_ZONE, the walkable piece of this zone the wizard landed in, or
        NO_EFFECT. A jump counts as staying in the zone only after TELEPORT_CONFIRM_SECONDS with no loading and no
        zone change: entering the Bazaar from Olde Town moved the wizard before the loading began, and its new
        position, in the Bazaar's own coordinates, read as Olde Town's walkable piece 4, which later runs kept."""
        start = await self.client.body.position()
        jumped_at = time.monotonic() if already_jumped else None
        deadline = time.monotonic() + TELEPORT_WAIT_SECONDS
        while time.monotonic() < deadline:
            if await attempt(self.client.is_loading()) is True or await attempt(self.client.zone_name()) != zone:
                return LEFT_ZONE
            now = time.monotonic()
            if jumped_at is None and flat_distance(start, await self.client.body.position()) > JUMP_DISTANCE:
                jumped_at = now
            if jumped_at is not None and now - jumped_at >= TELEPORT_CONFIRM_SECONDS:
                return await self.piece_here(planner)
            await asyncio.sleep(TELEPORT_POLL_SECONDS)
        return NO_EFFECT if jumped_at is None else await self.piece_here(planner)

    async def piece_here(self, planner: RoutePlanner) -> int | None:
        here = await self.client.body.position()
        return planner.piece_of((here.x, here.y))

    def note_hidden_door(self, zone: str, planner: RoutePlanner, destination, walked_from) -> None:
        """A walk for a place in this zone changed the zone: it went through a door the zone's data does not list.
        It is kept as such a door just past where the wizard last stood (`routes.hidden_door_centre`,
        `routes.add_hidden_door`), routed around from then on, unless the walk was for a door there or a known
        teleport volume is there."""
        walking_at, self._walking_at = self._walking_at, None
        if walking_at is None or walking_at[0] != zone or not isinstance(walking_at[1], dict):
            return
        point = XYZ(walking_at[1]["x"], walking_at[1]["y"], 0.0)
        if flat_distance(point, destination) <= 2 * HIDDEN_DOOR_RADIUS:
            return
        if any(flat_distance(point, XYZ(volume.x, volume.y, 0.0)) <= volume.radius + HIDDEN_DOOR_RADIUS
               for volume, _ in planner.teleports):
            return
        centre = hidden_door_centre(xy(walked_from), (point.x, point.y))
        if add_hidden_door(self.record.hidden_doors, zone, centre):
            self.events.emit("walk", f"walked through a door {zone}'s data does not list, last standing at "
                                     f"({point.x:.0f}, {point.y:.0f}); routes keep out of ({centre[0]:.0f}, "
                                     f"{centre[1]:.0f}) from now on")

    def hazards_for(self, planner: RoutePlanner, zone: str, start, destination, arrive_radius: float, *,
                    avoid, duel_circles) -> tuple[Hazards, list[dict]]:
        """Everything a walk from `start` to `destination` keeps away from, and the enemies it routes around
        where they will be (none in the grace after a battle)."""
        now = time.monotonic()
        self.motion.observe(avoid, now)
        around = [] if self.in_grace_after_battle() else enemies_to_route_around(avoid, me=start, destination=destination)
        hazards = Hazards.of(enemies=[enemy["position"] for enemy in avoid], duel_circles=duel_circles,
                             obstacles=self.record.obstacles.get(zone, []), patrols=planner.streets,
                             keep_out=planner.teleports_to_keep_out_of(start, destination, arrive_radius)
                             + hidden_doors_to_keep_out_of(self.record.hidden_doors.get(zone, []), start, destination,
                                                           arrive_radius),
                             tracks=[self.motion.track(enemy, now) for enemy in around], start=start)
        return hazards, around

    def rerouter(self, planner: RoutePlanner, hazards: Hazards, destination):
        """Plans the way ahead again around where enemies are going, from where the wizard is, while it walks."""
        def reroute(path_ahead, threats: list[dict], now: float):
            around = enemies_to_route_around(threats, me=path_ahead[0], destination=destination)
            live = replace(hazards, enemies=tuple(xy(enemy["position"]) for enemy in threats),
                           tracks=tuple(self.motion.track(enemy, now) for enemy in around),
                           start=xy(path_ahead[0]))
            return planner.reroute(path_ahead, live)
        return reroute

    def watcher(self, *, also=None, ignore=(), reroute=None):
        """Runs on every walking tick: stop for the STOP file, a battle, loading, a dialog or `also()`; step
        away from a close enemy; and when an enemy's course will come near the next stretch of the path, plan
        the way ahead again without stopping (`reroute`). Only when that finds no way, or did not help, the trip
        ends and the next turn plans again. A duel near the path always ends the trip."""
        route = PlannedRoute()
        last_reroute = [0.0]

        async def watch(path_ahead):
            if self.settings.stop_requested():
                return "stop requested"
            state = await snapshot(self.client)
            if battle_showing(state):
                return "battle"
            if state["loading"] is True:
                return "loading"
            self._walking_at = (state["zone"], state["position"])
            if state["in_dialog"] is True or await dialog_open(self.client):
                return "dialog"
            if not free_to_move(state):
                return "not free to move"
            if also is not None and (reason := await also()):
                return reason
            enemies, duel_circles = await surroundings(self.client)
            now = time.monotonic()
            self.motion.observe(enemies, now)
            threats = [] if self.in_grace_after_battle() else others(enemies, ignore)
            self.approaches.record(enemies, now)
            self.note_sightings(state["zone"], enemies, path_ahead[0], now)
            if close := too_close(threats):
                await self.step_away_from(close, "while walking", ignore=ignore)
                return "stepped away from an enemy"
            stretch = path_within(path_ahead, WATCHED_PATH_LENGTH)
            if any(distance_to_path(circle, stretch) < duel_clearance(path_ahead[0], circle)
                   for circle in duel_circles):
                return DUEL_NEAR_PATH
            if route.is_new(path_ahead):
                route.remember_clearances({enemy["id"]: closest_approach(self.motion.track(enemy, now), path_ahead)
                                           for enemy in threats}, path_ahead)
            if any(route.threatens(enemy["id"], closest_approach(self.motion.track(enemy, now), stretch))
                   for enemy in threats):
                if reroute is not None and now - last_reroute[0] >= MIN_SECONDS_BETWEEN_REROUTES:
                    last_reroute[0] = now
                    if legs := reroute(path_ahead, threats, now):
                        return Reroute(legs)
                return ENEMY_NEAR_PATH
            return None

        return watch

    def in_grace_after_battle(self) -> bool:
        return in_grace_after_battle(self._battle_ended_at, now=time.monotonic())

    async def step_away_from(self, close: list[dict], when: str, ignore=()) -> None:
        """Every enemy that comes close is stepped away from: enemies are always avoided, unless the quest needs
        the fight, and the quest's own targets are in `ignore`. Enemies that keep blocking the way are waited out."""
        self._dodges.append(time.monotonic())
        key = await step_away(self.client, close)
        self.record.step_aways.append(summary(close))
        nearest = close[0]
        self.events.emit("step away", f"{when}: {enemy_names(close)}, nearest {nearest['distance']:.0f} away; "
                                      f"{'backed off with S' if key == 'S' else 'walked on with W'}")
        if keeps_blocking(self._dodges, now=time.monotonic()):
            await self.let_enemies_pass(ignore)

    async def let_enemies_pass(self, ignore=()) -> None:
        """Enemies that keep coming back patrol the way ahead. Stand back for LET_PASS_SECONDS and let them walk
        on, stepping away again if one comes close, then plan again. The run's step-away limit stops a wait that
        never ends, for the operator."""
        self.events.emit("step away", f"enemies keep blocking the way; waiting up to {LET_PASS_SECONDS:.0f} s for "
                                      "them to walk on")
        deadline = time.monotonic() + LET_PASS_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if battle_showing(await snapshot(self.client)):
                return
            if close := too_close(others(await nearby_enemies(self.client), ignore)):
                await step_away(self.client, close)
                self.record.step_aways.append(summary(close))
            await asyncio.sleep(LET_PASS_POLL_SECONDS)

    async def record_end_state(self) -> None:
        try:
            self.record.end = await snapshot(self.client)
            quests = await read_quests(self.client)
            self.record.quest_end = {"active": quests["active"],
                                     "journal": [(entry["name_key"], entry["mainline"]) for entry in quests["journal"]]}
        except Exception as exc:
            self.record.end = f"<unavailable: {type(exc).__name__}>"


def plain_xy(state: dict) -> tuple | None:
    """A reading's position as rounded (x, y), or None."""
    position = state.get("position")
    return (round(position["x"]), round(position["y"])) if isinstance(position, dict) else None


def failure_text(attempt: dict) -> str:
    """" (turn failed: facing did not converge)" after a route method that failed for a reason, else "". Several
    fights with bystanders began right after a "nav: failed", and the event did not say why."""
    return f" ({attempt['reason']})" if attempt.get("result") == "failed" and attempt.get("reason") else ""


def reroute_text(attempt: dict) -> str:
    return f" after {attempt['reroutes']} reroutes" if attempt.get("reroutes") else ""


async def play(settings: Settings, limits: Limits, *, combat_policy: CombatPolicy | None = None,
               offer_policy: OfferPolicy | None = None, loop_class: type[QuestLoop] = QuestLoop,
               use_potions: bool = False, wear_gear: bool = False, use_travel_buttons: bool = False,
               clear_world: str | None = None, leave_dungeons: bool = False, edit_deck: bool = False):
    """Attach to the game, play, remove the hooks, and always save the report, even when interrupted.
    Returns the report and the path it was saved to. `clear_world` starts clearing that world of its quests
    (`QuestLoop.clear_world_turn`); a clearing begun by an earlier run goes on without it."""
    record = RunRecord(limits=limits)
    knowledge = Knowledge.load(settings.knowledge_file)
    knowledge.give_to(record)
    if clear_world and record.clearing_world != clear_world:
        record.clearing_world = clear_world
    events = EventLog.in_folder(settings.runtime_folder)
    events.emit("knowledge", f"from earlier runs: {knowledge.summary()}")
    record.events_file = str(events.path)
    settings.clear_stop()
    attachment = None
    try:
        async with attached() as attachment:
            record.hooks = attachment.hooks
            loop = loop_class(attachment.client, settings, record,
                              combat_policy=combat_policy or SpellTypePolicy(),
                              offer_policy=offer_policy or MainQuestsOnly(), events=events,
                              use_potions=use_potions, wear_gear=wear_gear, use_travel_buttons=use_travel_buttons,
                              leave_dungeons=leave_dungeons, edit_deck=edit_deck)
            await loop.play()
    except NoClient as exc:
        record.stopped = str(exc)
    finally:
        if attachment is not None:
            record.hooks_removed = attachment.hooks_removed
        knowledge.learn_from(record)
        knowledge.save(settings.knowledge_file)
        path = save_report("quest-loop", record.as_report(), settings.runtime_folder)
    return record.as_report(), path
