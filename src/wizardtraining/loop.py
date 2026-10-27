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

from wizwalker import Keycode

from .combat import approach, fight
from .config import Settings
from .dialog import (DIALOG_FINISHED, FOLLOW_UP_WAIT_SECONDS, NPC_ARRIVE_DISTANCE, OFFER_LEFT_FOR_OPERATOR,
                     choose_service, dialog_open, leave_services, near_npc, read_conversation, service_options,
                     services_open, talk, use_object, wait_for_dialog)
from .entities import nearby_enemies, step_away, surroundings
from .geometry import distance_to_path, flat_distance, path_within
from .keys import tap
from .movement import KeysIgnored, face, travel
from .navigation import load_planner
from .policy import LEAVE_MENU, CombatPolicy, MainQuestsOnly, OfferPolicy, SpellTypePolicy
from .progress import (DUEL_NEAR_PATH, ENEMY_NEAR_PATH, PATH_THREATS, Limits, PlannedRoute, RunRecord, StopRun,
                       check_limits, needs_rest, progressed, remember_obstacles, stalled, travel_outcome)
from .quests import open_goals, read_quest_arrow, read_quests
from .reports import plain, save_report
from .routes import DUEL_CIRCLE_NO_GO, Hazards, RoutePlanner
from .session import NoClient, attached, hooks_ready
from .state import attempt, battle_showing, free_to_move, health_fraction, snapshot
from .targets import bystanders, others, quest_targets, summary, too_close
from .ui import visible_children

TARGET_REACH = 1200.0
ARROW_ARRIVE_RADIUS = 250.0
WAYPOINT_ARRIVE_RADIUS = 150.0
LOADING_WAIT_SECONDS = 3.0
DOOR_PUSH_SECONDS = 0.8
DOOR_WAIT_SECONDS = 15.0
DOOR_POLL_SECONDS = 0.5
WATCHED_PATH_LENGTH = 2000.0
BARELY_MOVED_DISTANCE = 100.0
ENEMY_PASS_WAIT_SECONDS = 1.5
DEFEATED_HEALTH_FRACTION = 0.05
LOWEST_HEALTH_FRACTION_TO_KEEP_QUESTING = 0.35
REST_POLL_SECONDS = 10.0
REST_TURN_SECONDS = 60.0
NOT_FREE_TO_MOVE_WAIT_SECONDS = 3.0
KEYS_IGNORED = ("the game ignored a turn key while free to move; a popup (such as the Endorse Wizard window) "
                "may be holding the keyboard; left for the operator")

log = logging.getLogger(__name__)


class QuestLoop:
    def __init__(self, client, settings: Settings, record: RunRecord, *,
                 combat_policy: CombatPolicy, offer_policy: OfferPolicy):
        self.client = client
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
            self.record.start = await snapshot(self.client)
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

    async def run_turns(self) -> None:
        deadline = time.monotonic() + self.limits.minutes * 60
        while True:
            check_limits(self.record, seconds_left=deadline - time.monotonic(),
                         stop_requested=self.settings.stop_requested())
            state = await snapshot(self.client)
            if isinstance(state["level"], int) and state["level"] >= self.limits.target_level:
                raise StopRun(f"reached level {state['level']}")
            turn = await self.checked_turn(state)
            turn["level"], turn["health"] = state["level"], state["health"]
            self.record.record_turn(turn)
            quest = self.record.quest or {}
            self.record.note_place(state["zone"], (quest.get("name"), quest.get("goal_id")))
            log.info("turn %d: %s (progress=%s, level=%s, zone=%s, goal=%s %s)", len(self.record.turns), turn["did"],
                     turn["progress"], state["level"], state["zone"], quest.get("goal"), quest.get("goal_zone") or "")

    async def checked_turn(self, state: dict) -> dict:
        try:
            return await self.play_turn(state)
        except KeysIgnored:
            if free_to_move(state):
                raise StopRun(KEYS_IGNORED)
            return stalled("a turn key was ignored while busy")

    async def play_turn(self, state: dict) -> dict:
        if state["loading"] is True:
            self.record.loading_waits_in_a_row += 1
            await asyncio.sleep(LOADING_WAIT_SECONDS)
            if self.record.loading_waits_in_a_row > self.limits.max_loading_waits_in_a_row:
                return stalled("waited for loading")
            return progressed("waited for loading")
        self.record.loading_waits_in_a_row = 0
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
        return await self.quest_turn(state)

    async def battle_turn(self) -> dict:
        self.record.battles += 1
        zone_before = await attempt(self.client.zone_name())
        battle = await fight(self.client, self.combat_policy)
        self.record.battle_log.append(battle)
        if "stopped" in battle:
            raise StopRun(battle["stopped"])
        after = await snapshot(self.client)
        battle["after"] = {key: after[key] for key in ("zone", "level", "health", "max_health", "mana")}
        fraction = health_fraction(after)
        if after["zone"] != zone_before or (fraction is not None and fraction <= DEFEATED_HEALTH_FRACTION):
            self.record.defeats += 1
            if self.record.defeats > self.limits.max_defeats:
                raise StopRun("defeated in battle; stopping for the operator")
        casts = sum(1 for battle_round in battle["rounds"] if battle_round["action"].startswith("cast"))
        return progressed("battle", rounds=len(battle["rounds"]), casts=casts, final_phase=battle["final_phase"],
                          after=battle["after"])

    async def dialog_turn(self) -> dict:
        record = {}
        result = await read_conversation(self.client, record, self.offer_policy)
        self.record.dialog_log.append(record)
        if result == OFFER_LEFT_FOR_OPERATOR:
            raise StopRun(result)
        return progressed("dialog", result=result, pages=len(record["pages"]))

    async def services_turn(self) -> dict:
        """Pick an option of an NPC's services menu, as the offer policy decides."""
        options = await service_options(self.client)
        labels = [label for label, _ in options]
        active = await self.active_main_quest()
        self.record.note_menu_choice((active["name_key"], tuple(goal["id"] for goal in open_goals(active)))
                                     if active else None)
        choice = self.offer_policy.choose_service(labels, active_quest=active["title"] if active else None,
                                                  business_here=active is not None and await self.business_here(active))
        if choice is None:
            raise StopRun(f"an NPC's menu offers {labels}, and none is the active quest or an approved title; "
                          "left for the operator (approve one with --approve-quest)")
        if choice == LEAVE_MENU:
            await leave_services(self.client)
            return progressed("left an NPC's menu", options=labels)
        await choose_service(self.client, options[choice][1])
        return progressed("chose from an NPC's menu", option=labels[choice])

    async def business_here(self, quest: dict) -> bool:
        """The quest is ready to turn in, or its next goal is to talk to the NPC at the arrow, here."""
        if quest["ready_to_turn_in"] is True:
            return True
        goals = open_goals(quest)
        if not goals or goals[0]["type"] != "persona":
            return False
        try:
            return await near_npc(self.client, await read_quest_arrow(self.client, wait_seconds=1.0))
        except Exception:
            return False

    async def rest_turn(self, state: dict) -> dict:
        """Wait for health to come back, stepping away if an enemy comes close. A zone where a full rest
        gains nothing is remembered, and not rested in again."""
        deadline = time.monotonic() + REST_TURN_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if close := too_close(await nearby_enemies(self.client)):
                await step_away(self.client, close)
                self.record.step_aways.append(summary(close))
                return progressed("stepped away while resting")
            now = await snapshot(self.client)
            if battle_showing(now) or not needs_rest(health_fraction(now)):
                break
            await asyncio.sleep(REST_POLL_SECONDS)
        health = await attempt(self.client.stats.current_hitpoints())
        gained = isinstance(health, int) and isinstance(state["health"], int) and health > state["health"]
        if not gained and time.monotonic() >= deadline:
            self.record.zones_without_regeneration.append(state["zone"])
        return (progressed if gained else stalled)("rest", health_before=state["health"], health=health)

    async def quest_turn(self, state: dict) -> dict:
        fraction = health_fraction(state)
        if needs_rest(fraction):
            if state["zone"] not in self.record.zones_without_regeneration:
                return await self.rest_turn(state)
            if fraction < LOWEST_HEALTH_FRACTION_TO_KEEP_QUESTING:
                raise StopRun("health is low and does not regenerate in this zone; left for the operator")
        quest = await self.active_main_quest()
        if quest is None:
            if await wait_for_dialog(self.client, FOLLOW_UP_WAIT_SECONDS, poll=0.5):
                return await self.dialog_turn()
            raise StopRun("no active main quest and no dialog offering one")
        goals = open_goals(quest)
        goal = goals[0] if goals else {"type": "persona", "destination_zone": ""}
        arrow = await read_quest_arrow(self.client)
        self.record.quest = {"name": quest["name_key"], "goal": goal["type"], "goal_id": goal.get("id"),
                             "goal_zone": goal["destination_zone"], "arrow": plain(arrow)}
        if goal["destination_zone"] not in ("", await self.client.zone_name()):
            return await self.waypoint_turn(arrow, goal)
        handler = self.goal_handlers().get(goal["type"])
        if handler is None:
            raise StopRun(f"goal type {goal['type']} is not handled yet")
        return await handler(arrow, goal)

    async def active_main_quest(self) -> dict | None:
        active = (await read_quests(self.client))["active"]
        if active is not None and active["mainline"] is not True:
            raise StopRun(f"the active quest {active['name_key']} is not a main quest")
        return active

    async def bounty_turn(self, arrow, goal: dict) -> dict:
        """Walk toward the arrow around other enemies, then walk into a target enemy near the arrow."""
        enemies = await nearby_enemies(self.client)
        targets = quest_targets(enemies, arrow)
        in_reach = [target for target in targets if target["distance"] <= TARGET_REACH]
        if in_reach:
            result = await approach(self.client, in_reach[0])
            did = f"approached {in_reach[0]['name']}"
            return progressed(did) if result["ok"] else stalled(did, reason=result.get("reason"))

        async def target_in_reach():
            here = quest_targets(await nearby_enemies(self.client), arrow)
            return "target in reach" if any(target["distance"] <= TARGET_REACH for target in here) else None

        return await self.travel_turn("travel toward bounty targets", arrow, arrive_radius=ARROW_ARRIVE_RADIUS,
                                      also=target_in_reach, avoid=bystanders(enemies, targets), ignore=targets,
                                      seen=summary(enemies))

    async def persona_turn(self, arrow, goal: dict) -> dict:
        """Walk to the arrow's NPC and talk."""
        if await near_npc(self.client, arrow):
            record = {}
            result = await talk(self.client, arrow, record, self.offer_policy)
            self.record.dialog_log.append(record)
            if result == OFFER_LEFT_FOR_OPERATOR:
                raise StopRun(result)
            return (progressed if result == DIALOG_FINISHED else stalled)("talk", result=result)
        return await self.travel_turn("travel to quest NPC", arrow, arrive_radius=NPC_ARRIVE_DISTANCE / 2,
                                      also=self.arrival_check(arrow), avoid=await nearby_enemies(self.client))

    async def usage_turn(self, arrow, goal: dict) -> dict:
        """Walk to the quest object and use it. Progress only if an open goal was completed."""
        if await near_npc(self.client, arrow):
            goals_before = await self.open_goal_count()
            record = {}
            result = await use_object(self.client, arrow, record, self.offer_policy)
            self.record.dialog_log.append(record)
            if result == OFFER_LEFT_FOR_OPERATOR:
                raise StopRun(result)
            goals_after = await self.open_goal_count()
            completed = goals_before is not None and goals_after is not None and goals_after < goals_before
            return (progressed if completed else stalled)("use quest object", result=result, goals_left=goals_after)
        return await self.travel_turn("travel to quest object", arrow, arrive_radius=NPC_ARRIVE_DISTANCE / 2,
                                      also=self.arrival_check(arrow), avoid=await nearby_enemies(self.client))

    async def waypoint_turn(self, arrow, goal: dict) -> dict:
        """Walk to the arrow. A waypoint still open once the wizard stands at its arrow is a door: walk in."""
        if flat_distance(await self.client.body.position(), arrow) <= WAYPOINT_ARRIVE_RADIUS:
            return await self.zone_door_turn(arrow)
        return await self.travel_turn("travel to waypoint", arrow, arrive_radius=WAYPOINT_ARRIVE_RADIUS,
                                      avoid=await nearby_enemies(self.client))

    async def zone_door_turn(self, door) -> dict:
        """Walk into the door, then give the zone change a few seconds to start."""
        zone = await self.client.zone_name()
        turn = await face(self.client, door)
        if not turn["ok"]:
            return stalled("could not face the zone door", reason=turn["reason"])
        await tap(self.client, Keycode.W, DOOR_PUSH_SECONDS)
        deadline = time.monotonic() + DOOR_WAIT_SECONDS
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if await attempt(self.client.is_loading()) is True or await attempt(self.client.zone_name()) != zone:
                return progressed("walked through a zone door")
            await asyncio.sleep(DOOR_POLL_SECONDS)
        return stalled("walked into a zone door, but the zone did not change")

    def arrival_check(self, arrow):
        async def arrived():
            return "arrived" if await near_npc(self.client, arrow) else None
        return arrived

    async def open_goal_count(self) -> int | None:
        quest = await self.active_main_quest()
        return None if quest is None else len(open_goals(quest))

    async def planner(self) -> RoutePlanner:
        zone = await self.client.zone_name()
        if zone not in self._planners:
            self._planners[zone] = await load_planner(zone, self.settings.deimos_root)
            self.record.planner_status[zone] = self._planners[zone].status
        return self._planners[zone]

    async def travel_turn(self, did: str, destination, *, arrive_radius: float, also=None, avoid=(), ignore=(),
                          **details) -> dict:
        start = await self.client.body.position()
        zone = await self.client.zone_name()
        _, duel_circles = await surroundings(self.client)
        hazards = Hazards.of(enemies=[enemy["position"] for enemy in avoid], duel_circles=duel_circles,
                             obstacles=self.record.obstacles.get(zone, []))
        trip = await travel(self.client, await self.planner(), destination, arrive_radius=arrive_radius,
                            watch=self.watcher(also=also, ignore=ignore), hazards=hazards)
        moved = flat_distance(start, await self.client.body.position())
        if trip["reason"] in PATH_THREATS and moved < BARELY_MOVED_DISTANCE:
            self.record.immobile_threat_stops_in_a_row += 1
            await asyncio.sleep(ENEMY_PASS_WAIT_SECONDS)
        else:
            self.record.immobile_threat_stops_in_a_row = 0
        trip_summary = {"result": trip["result"], "reason": trip["reason"], "moved": round(moved),
                        "methods": [(tried["method"], tried.get("result"), tried.get("reason"),
                                     tried.get("sidesteps"), tried.get("seconds")) for tried in trip["attempts"]]}
        new_obstacles = remember_obstacles(self.record, zone, trip["blocked_at"])
        return travel_outcome(did, trip["reason"], moved, self.record, new_obstacles=new_obstacles,
                              trip=trip_summary, **details)

    def watcher(self, *, also=None, ignore=()):
        """Runs on every walking tick: stop for the STOP file, a battle, loading, a dialog or `also()`; step
        away from a close enemy; and end the trip when an enemy or a duel is near the next stretch of the
        path, so the next turn plans around it."""
        route = PlannedRoute()

        async def watch(path_ahead):
            if self.settings.stop_requested():
                return "stop requested"
            state = await snapshot(self.client)
            if battle_showing(state):
                return "battle"
            if state["loading"] is True:
                return "loading"
            if state["in_dialog"] is True or await dialog_open(self.client):
                return "dialog"
            if not free_to_move(state):
                return "not free to move"
            if also is not None and (reason := await also()):
                return reason
            enemies, duel_circles = await surroundings(self.client)
            threats = others(enemies, ignore)
            if close := too_close(threats):
                await step_away(self.client, close)
                self.record.step_aways.append(summary(close))
                return "stepped away from an enemy"
            stretch = path_within(path_ahead, WATCHED_PATH_LENGTH)
            if any(distance_to_path(circle, stretch) < DUEL_CIRCLE_NO_GO for circle in duel_circles):
                return DUEL_NEAR_PATH
            if route.is_new(path_ahead):
                route.remember_clearances({enemy["id"]: distance_to_path(enemy["position"], path_ahead)
                                           for enemy in threats}, path_ahead)
            if any(route.threatens(enemy["id"], distance_to_path(enemy["position"], stretch)) for enemy in threats):
                return ENEMY_NEAR_PATH
            return None

        return watch

    async def record_end_state(self) -> None:
        try:
            self.record.end = await snapshot(self.client)
            quests = await read_quests(self.client)
            self.record.quest_end = {"active": quests["active"],
                                     "journal": [(entry["name_key"], entry["mainline"]) for entry in quests["journal"]]}
        except Exception as exc:
            self.record.end = f"<unavailable: {type(exc).__name__}>"


async def play(settings: Settings, limits: Limits, *, combat_policy: CombatPolicy | None = None,
               offer_policy: OfferPolicy | None = None, loop_class: type[QuestLoop] = QuestLoop):
    """Attach to the game, play, remove the hooks, and always save the report, even when interrupted.
    Returns the report and the path it was saved to."""
    record = RunRecord(limits=limits)
    settings.clear_stop()
    attachment = None
    try:
        async with attached() as attachment:
            record.hooks = attachment.hooks
            loop = loop_class(attachment.client, settings, record,
                              combat_policy=combat_policy or SpellTypePolicy(),
                              offer_policy=offer_policy or MainQuestsOnly())
            await loop.play()
    except NoClient as exc:
        record.stopped = str(exc)
    finally:
        if attachment is not None:
            record.hooks_removed = attachment.hooks_removed
        path = save_report("quest-loop", record.as_report(), settings.runtime_folder)
    return record.as_report(), path
