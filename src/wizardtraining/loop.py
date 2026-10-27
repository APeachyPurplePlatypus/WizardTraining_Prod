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

from wizwalker import XYZ, Keycode

from .combat import approach, fight
from .config import Settings
from .dialog import (DIALOG_FINISHED, FOLLOW_UP_WAIT_SECONDS, NPC_ARRIVE_DISTANCE, OFFER_LEFT_FOR_OPERATOR,
                     choose_service, close_enough, dialog_open, leave_services, near_npc, read_conversation, service_options,
                     services_open, talk, use_object, wait_for_dialog)
from .entities import HEALTH_WISP, MANA_WISP, nearby_enemies, step_away, surroundings, wisps
from .events import EventLog, describe_battle, describe_changes, describe_round, enemy_names, health_text
from .geometry import distance_to_path, flat_distance, path_within
from .keys import tap
from .movement import KeysIgnored, face, travel
from .navigation import load_planner
from .policy import LEAVE_MENU, CombatPolicy, MainQuestsOnly, OfferPolicy, SpellTypePolicy
from .progress import (DUEL_NEAR_PATH, ENEMY_NEAR_PATH, PATH_THREATS, Limits, PlannedRoute, RunRecord, StopRun,
                       check_limits, needs_rest, progressed, remember_obstacles, should_drink_potion, stalled,
                       travel_outcome, wanted_wisp)
from .quests import arrow_shows_no_target, open_goals, read_quest_arrow, read_quests
from .reports import plain, save_report
from .routes import DUEL_CIRCLE_NO_GO, Hazards, RoutePlanner
from .session import NoClient, attached, hooks_ready
from .state import attempt, battle_showing, free_to_move, health_fraction, mana_fraction, snapshot
from .placed import gate_toward, objects_for_goal
from .targets import bystanders, next_area_to_explore, others, quest_targets, safe_wisps, summary, too_close
from .teleports import LEFT_ZONE, NO_EFFECT, TeleportVolume, describe_outcome
from .ui import POTION_BUTTON, click, close_known_popup, visible_children

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
POTION_SETTLE_SECONDS = 3.0
WISP_ARRIVE_RADIUS = 40.0
WISP_SETTLE_SECONDS = 1.5
TELEPORT_WAIT_SECONDS = 8.0
TELEPORT_POLL_SECONDS = 0.25
JUMP_DISTANCE = 500.0
TELEPORTED = "teleported"
KEYS_IGNORED = ("the game ignored a turn key while free to move; a popup (such as the Endorse Wizard window) "
                "may be holding the keyboard; left for the operator")

log = logging.getLogger(__name__)


class QuestLoop:
    def __init__(self, client, settings: Settings, record: RunRecord, *,
                 combat_policy: CombatPolicy, offer_policy: OfferPolicy, events: EventLog | None = None,
                 use_potions: bool = False):
        self.client = client
        self.use_potions = use_potions
        self._potion_failed = False
        self._object_in_use = None
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
            log.info("turn %d: %s (progress=%s, level=%s, health=%s, zone=%s, goal=%s %s)", len(self.record.turns),
                     turn["did"], turn["progress"], state["level"], health_text(state), state["zone"], quest.get("goal"),
                     quest.get("goal_zone") or "")
            self.note_changes(state)

    def note_changes(self, state: dict) -> None:
        for kind, text in describe_changes(self._last_state, state, self._last_quest, self.record.quest):
            self.events.emit(kind, text)
        if self._last_state is not None and state["zone"] != self._last_state["zone"] and isinstance(state["position"], dict):
            self.record.arrivals[state["zone"]] = {"from": self._last_state["zone"],
                                                   "position": (state["position"]["x"], state["position"]["y"])}
        self._last_state, self._last_quest = state, dict(self.record.quest or {})

    async def checked_turn(self, state: dict) -> dict:
        if closed := await close_known_popup(self.client):
            self.events.emit("popup", f"closed the {closed} window without choosing anything")
            return progressed(f"closed the {closed} window")
        try:
            return await self.play_turn(state)
        except KeysIgnored:
            if closed := await close_known_popup(self.client):
                self.events.emit("popup", f"closed the {closed} window, which was holding the keyboard")
                return progressed(f"closed the {closed} window")
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
        before = await snapshot(self.client)
        started = time.monotonic()
        self.events.emit("battle", f"battle {self.record.battles} started in {before['zone']}, health {health_text(before)}")
        battle = await fight(self.client, self.combat_policy,
                             on_round=lambda entry: self.events.emit("round", describe_round(entry)))
        self.record.battle_log.append(battle)
        after = await snapshot(self.client)
        fraction = health_fraction(after)
        defeated = after["zone"] != before["zone"] or (fraction is not None and fraction <= DEFEATED_HEALTH_FRACTION)
        outcome = "left for the operator" if "stopped" in battle else ("lost" if defeated else "won")
        self.events.emit("battle", describe_battle(battle, seconds=time.monotonic() - started, before=before,
                                                   after=after, outcome=outcome), outcome=outcome)
        if "stopped" in battle:
            raise StopRun(battle["stopped"])
        battle["after"] = {key: after[key] for key in ("zone", "level", "health", "max_health", "mana", "gold")}
        if defeated:
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
        self.note_dialog(record, result)
        if result == OFFER_LEFT_FOR_OPERATOR:
            raise StopRun(result)
        return progressed("dialog", result=result, pages=len(record["pages"]))

    def note_dialog(self, record: dict, result: str) -> None:
        offers = [page["offer"] for page in record.get("pages", []) if "offer" in page]
        self.events.emit("dialog", f"{len(record.get('pages', []))} pages, {record.get('follow_ups', 0)} follow-ups"
                                   f"{', offers: ' + ', '.join(offers) if offers else ''}; {result}")

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

    async def wisp_turn(self, wanted: str, state: dict) -> dict | None:
        """Walk to the nearest safe health or mana wisp and touch it. None when there is no safe one in reach,
        so the turn falls back to a potion or a rest. A wisp that gives nothing is not tried again."""
        kind = HEALTH_WISP if wanted == "health" else MANA_WISP
        enemies, circles = await surroundings(self.client)
        candidates = safe_wisps(await wisps(self.client, kind), me=await self.client.body.position(), enemies=enemies,
                                duel_circles=circles, tried=self.record.tried_wisps)
        if not candidates:
            return None
        wisp = candidates[0]
        start = await self.client.body.position()
        hazards = Hazards.of(enemies=[enemy["position"] for enemy in enemies], duel_circles=circles,
                             obstacles=self.record.obstacles.get(state["zone"], []))
        trip = await travel(self.client, await self.planner(), wisp["position"], arrive_radius=WISP_ARRIVE_RADIUS,
                            watch=self.watcher(), hazards=hazards)
        await asyncio.sleep(WISP_SETTLE_SECONDS)
        after = await snapshot(self.client)
        stat = "health" if wanted == "health" else "mana"
        gained = isinstance(after[stat], int) and isinstance(state[stat], int) and after[stat] > state[stat]
        if trip["result"] == "arrived" and not gained:
            self.record.tried_wisps.append(wisp["id"])
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

    async def rest_turn(self, state: dict) -> dict:
        """Wait for health to come back, stepping away if an enemy comes close. A zone where a full rest
        gains nothing is remembered, and not rested in again."""
        deadline = time.monotonic() + REST_TURN_SECONDS
        started = time.monotonic()
        while time.monotonic() < deadline and not self.settings.stop_requested():
            if close := too_close(await nearby_enemies(self.client)):
                await self.step_away_from(close, "while resting")
                return progressed("stepped away while resting")
            now = await snapshot(self.client)
            if battle_showing(now) or not needs_rest(health_fraction(now)):
                break
            await asyncio.sleep(REST_POLL_SECONDS)
        health = await attempt(self.client.stats.current_hitpoints())
        gained = isinstance(health, int) and isinstance(state["health"], int) and health > state["health"]
        self.events.emit("rest", f"rested {time.monotonic() - started:.0f} s: health {state['health']} -> {health} "
                                 f"of {state['max_health']}")
        if not gained and time.monotonic() >= deadline:
            self.record.zones_without_regeneration.append(state["zone"])
            self.events.emit("rest", f"no health came back in {state['zone']}; it will not be rested in again")
        return (progressed if gained else stalled)("rest", health_before=state["health"], health=health)

    async def quest_turn(self, state: dict) -> dict:
        fraction = health_fraction(state)
        wanted = wanted_wisp(fraction, mana_fraction(state))
        if wanted is not None and (turn := await self.wisp_turn(wanted, state)) is not None:
            return turn
        if self.use_potions and not self._potion_failed:
            if should_drink_potion(fraction, await attempt(self.client.stats.potion_charge())):
                return await self.potion_turn(state)
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
        if arrow_shows_no_target(arrow):
            arrow = await self.target_without_arrow(goal)
            if arrow is None and goal["type"] in ("bounty", "bountycollect") and goal.get("target_code"):
                return await self.explore_turn(goal)
            if arrow is None:
                raise StopRun(f"the quest arrow shows no target for the {goal['type']} goal of "
                              f"{quest.get('title') or quest['name_key']}, and neither its tags {goal.get('tags')} "
                              f"nor its enemy {goal.get('target_code')} could be found; left for the operator")
        self.record.quest = {"name": quest["name_key"], "title": quest.get("title"), "goal": goal["type"],
                             "goal_id": goal.get("id"),
                             "goal_zone": goal["destination_zone"], "arrow": plain(arrow)}
        if goal["destination_zone"] not in ("", await self.client.zone_name()):
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
        objects = objects_for_goal(planner.placed_objects, goal.get("tags") or [], me=(me.x, me.y),
                                   visited=self.record.visited_objects)
        if objects:
            self._object_in_use = objects[0]
            self.events.emit("target", f"no quest arrow; going to placed object {objects[0].template} at "
                                       f"({objects[0].x:.0f}, {objects[0].y:.0f}), {len(objects)} not yet used")
            return XYZ(objects[0].x, objects[0].y, objects[0].z)
        code = goal.get("target_code")
        matching = [enemy for enemy in await nearby_enemies(self.client) if code and enemy.get("display_code") == code]
        if matching:
            self.events.emit("target", f"no quest arrow; going to {matching[0]['name']} ({code}), "
                                       f"{matching[0]['distance']:.0f} away, {len(matching)} in sight")
            return matching[0]["position"]
        return None

    async def explore_turn(self, goal: dict) -> dict:
        """Look for a goal's enemies when none is in sight: walk to the nearest part of the zone not explored
        yet, stopping as soon as one shows up. Stops the run once every part has been seen."""
        code = goal["target_code"]
        zone = await self.client.zone_name()
        planner = await self.planner()
        explored = self.record.explored.setdefault(f"{zone}|{code}", [])
        me = await self.client.body.position()
        area = next_area_to_explore(planner.exploration_points, me=(me.x, me.y), explored=explored)
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

    async def goal_still_open(self, goal: dict) -> bool:
        quest = await self.active_main_quest()
        return quest is not None and any(open_goal["id"] == goal.get("id") for open_goal in open_goals(quest))

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
        planner = await self.planner()
        crossing = planner.crossing(start, destination, self.record.teleport_outcomes.get(zone, {}))
        if crossing is not None:
            return await self.teleport_turn(crossing, zone, planner)
        _, duel_circles = await surroundings(self.client)
        hazards = Hazards.of(enemies=[enemy["position"] for enemy in avoid], duel_circles=duel_circles,
                             obstacles=self.record.obstacles.get(zone, []))
        trip = await travel(self.client, planner, destination, arrive_radius=arrive_radius,
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
        methods = ", ".join(f"{tried['method']}: {tried.get('result')}" for tried in trip["attempts"])
        self.events.emit("walk", f"{did}: moved {moved:.0f}, {trip['result']}"
                                 f"{' (' + trip['reason'] + ')' if trip['reason'] else ''}; {methods}"
                                 f"{f'; {new_obstacles} new obstacles' if new_obstacles else ''}")
        return travel_outcome(did, trip["reason"], moved, self.record, new_obstacles=new_obstacles,
                              trip=trip_summary, **details)

    async def teleport_turn(self, volume: TeleportVolume, zone: str, planner: RoutePlanner) -> dict:
        """Walk into a teleport volume, wait for the jump, and remember where it led: another piece of this
        zone, another zone, or nowhere. A volume that left the zone or did nothing is not tried again."""
        self.events.emit("teleporter", f"the target is in another walkable area of {zone}; walking into "
                                       f"{volume.name} at ({volume.x:.0f}, {volume.y:.0f})")
        before = await self.client.body.position()
        trip = await travel(self.client, planner, volume.point, arrive_radius=volume.radius / 3,
                            watch=self.watcher(also=self.jump_check()))
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
        if already_jumped:
            return await self.piece_here(planner)
        start = await self.client.body.position()
        deadline = time.monotonic() + TELEPORT_WAIT_SECONDS
        while time.monotonic() < deadline:
            if await attempt(self.client.is_loading()) is True or await attempt(self.client.zone_name()) != zone:
                return LEFT_ZONE
            if flat_distance(start, await self.client.body.position()) > JUMP_DISTANCE:
                return await self.piece_here(planner)
            await asyncio.sleep(TELEPORT_POLL_SECONDS)
        return NO_EFFECT

    async def piece_here(self, planner: RoutePlanner) -> int | None:
        here = await self.client.body.position()
        return planner.piece_of((here.x, here.y))

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
                await self.step_away_from(close, "while walking")
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

    async def step_away_from(self, close: list[dict], when: str) -> None:
        await step_away(self.client, close)
        self.record.step_aways.append(summary(close))
        nearest = close[0]
        self.events.emit("step away", f"{when}: {enemy_names(close)}, nearest {nearest['distance']:.0f} away")

    async def record_end_state(self) -> None:
        try:
            self.record.end = await snapshot(self.client)
            quests = await read_quests(self.client)
            self.record.quest_end = {"active": quests["active"],
                                     "journal": [(entry["name_key"], entry["mainline"]) for entry in quests["journal"]]}
        except Exception as exc:
            self.record.end = f"<unavailable: {type(exc).__name__}>"


async def play(settings: Settings, limits: Limits, *, combat_policy: CombatPolicy | None = None,
               offer_policy: OfferPolicy | None = None, loop_class: type[QuestLoop] = QuestLoop,
               use_potions: bool = False):
    """Attach to the game, play, remove the hooks, and always save the report, even when interrupted.
    Returns the report and the path it was saved to."""
    record = RunRecord(limits=limits)
    events = EventLog.in_folder(settings.runtime_folder)
    record.events_file = str(events.path)
    settings.clear_stop()
    attachment = None
    try:
        async with attached() as attachment:
            record.hooks = attachment.hooks
            loop = loop_class(attachment.client, settings, record,
                              combat_policy=combat_policy or SpellTypePolicy(),
                              offer_policy=offer_policy or MainQuestsOnly(), events=events,
                              use_potions=use_potions)
            await loop.play()
    except NoClient as exc:
        record.stopped = str(exc)
    finally:
        if attachment is not None:
            record.hooks_removed = attachment.hooks_removed
        path = save_report("quest-loop", record.as_report(), settings.runtime_folder)
    return record.as_report(), path
