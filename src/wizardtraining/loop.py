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
from .dialog import (DIALOG_FINISHED, FOLLOW_UP_WAIT_SECONDS, NPC_ARRIVE_DISTANCE, OFFER_LEFT_FOR_OPERATOR,
                     TALK_KEY_SECONDS, choose_service, close_enough, dialog_open, leave_services, near_npc, read_conversation, service_options,
                     services_open, talk, use_object, wait_for_dialog)
from .doors import CHANGE_START_SECONDS, change_begins, push_through
from .entities import (HEALTH_WISP, MANA_WISP, dungeon_entrance_near, nearby_enemies, nearest_npc, step_away,
                       surroundings, wisps)
from .equipment import count_items, equip, read_items, read_wizard
from .events import (EventLog, describe_battle, describe_changes, describe_round, dialog_text, enemy_names, health_text,
                     threat_text)
from .gear import describe_stats, upgrades
from .gametravel import go_to_the_commons, has_mark, mark_here, recall
from .geometry import Point, distance_to_path, flat_distance, path_within, xy
from .keys import tap
from .knowledge import Knowledge
from .motion import WALK_UNITS_PER_SECOND, ApproachLog, MotionTracker, closest_approach
from .movement import LOADING, KeysIgnored, Reroute, face, travel
from .navigation import load_planner
from .policy import LEAVE_MENU, CombatPolicy, MainQuestsOnly, OfferPolicy, SpellTypePolicy
from .progress import (DUEL_BLOCKS_THE_WAY, DUEL_NEAR_PATH, ENEMIES_IN_THE_WAY, ENEMY_NEAR_PATH, LimitReached, Limits, PATH_THREATS,
                       PlannedRoute, RunRecord, StopRun, check_limits, leaves_world, mana_for_a_fight, mana_to_travel,
                       nav_did_better, progressed, ready_to_recall, remember_obstacles, safe_to_stand, short_for_a_fight,
                       should_drink_potion, stalled, topped_up, travel_outcome, wanted_wisp,
                       WISP_ANY_DIRECTION_BELOW_FRACTION, world_of)
from .questbook import activate_quest
from .quests import arrow_shows_no_target, game_language, open_goals, read_quest_arrow, read_quests
from .reports import plain, save_report
from .patrols import VIEWS_TO_JUDGE, note_sightings, unwalked_paths
from .routes import GapStep, Hazards, RoutePlanner, duel_clearance
from .sidequests import unsupported_reason
from .screen import or_default, prompt_action, prompt_offers_talk
from .spellbook import SpellCatalog, deck_spells, learned_spell_ids
from .spells import KNOWN_AT_FIRST_CHECK, LEARNED, SpellLog, learned_text, newly_learned, spell_entry
from .session import NoClient, attached, hooks_ready
from .state import attempt, battle_showing, free_to_move, health_fraction, mana_fraction, snapshot
from .placed import gate_toward, objects_for_goal
from .targets import (bystanders, enemies_to_route_around, in_grace_after_battle, keeps_blocking,
                      leads_to_another_zone, named_enemies_not_in_a_duel, next_area_to_explore, others, quest_targets,
                      refill_reach, safe_wisps,
                      summary, too_close, WISP_REACH)
from .teleports import LEFT_ZONE, NO_EFFECT, TeleportVolume, describe_outcome, volume_at
from .trainer import OPENED_DIALOG, OPENED_MENU, close_training, learn_free_spells, open_training, open_with_professor
from .training import (GATE, SCHOOLS, TRAINER, School, in_dungeon, spells_to_learn, way_to_school, way_toward_zone,
                       zone_for_area)
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
MARK_MANA_NEEDED = 8
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


class QuestLoop:
    def __init__(self, client, settings: Settings, record: RunRecord, *,
                 combat_policy: CombatPolicy, offer_policy: OfferPolicy, events: EventLog | None = None,
                 use_potions: bool = False, wear_gear: bool = False, use_travel_buttons: bool = False):
        self.client = client
        self.use_potions = use_potions
        self.wear_gear = wear_gear
        self.use_travel_buttons = use_travel_buttons
        self._marked_in: str | None = None
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
                check_limits(self.record, seconds_left=deadline - time.monotonic(),
                             stop_requested=self.settings.stop_requested())
                if isinstance(state["level"], int) and state["level"] >= self.limits.target_level:
                    raise LimitReached(f"reached level {state['level']}")
            except LimitReached as reached:
                await self.finish_safely(reached, state)
            turn = await self.checked_turn(state)
            quest = self.record.quest or {}
            turn.update(level=state["level"], health=state["health"], zone=state["zone"], position=plain_xy(state),
                        goal=(quest.get("goal"), quest.get("goal_zone")), arrow=plain_xy({"position": quest.get("arrow")}))
            self.record.record_turn(turn)
            self.record.note_place(state["zone"], (quest.get("name"), quest.get("goal_id")))
            await self.check_spells(state)
            log.info("turn %d: %s (progress=%s, level=%s, health=%s, zone=%s, goal=%s %s)", len(self.record.turns),
                     turn["did"], turn["progress"], state["level"], health_text(state), state["zone"], quest.get("goal"),
                     quest.get("goal_zone") or "")
            self.note_changes(state)

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
        self._last_state, self._last_quest = state, dict(self.record.quest or {})

    async def checked_turn(self, state: dict) -> dict:
        """A turn, after answering known popups. An open message box the framework does not answer takes every
        click, so the run stops for the operator with the box's title (never its text, which can name a player):
        an unanswered friend request kept every card the wizard played out of its battles for over half an hour."""
        if answered := await answer_known_popup(self.client):
            self.events.emit("popup", answered)
            return progressed(answered)
        if (box := await message_box(self.client)) is not None:
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
            self.record.loading_waits_in_a_row += 1
            await asyncio.sleep(LOADING_WAIT_SECONDS)
            if self.record.loading_waits_in_a_row > self.limits.max_loading_waits_in_a_row:
                return stalled("waited for loading")
            return progressed("waited for loading")
        self.record.loading_waits_in_a_row = 0
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
        battle = await fight(self.client, self.combat_policy,
                             on_round=lambda entry: self.events.emit("round", describe_round(entry)))
        self.record.battle_log.append(battle)
        self._battle_ended_at = time.monotonic()
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
        wanted = wanted_wisp(fraction, mana_fraction(state))
        if wanted is not None:
            turn = await self.wisp_turn(wanted, state, heading=await self.wisp_heading(wanted, state))
            if turn is not None:
                return turn
        quest = await self.active_quest()
        if quest is None:
            if await wait_for_dialog(self.client, FOLLOW_UP_WAIT_SECONDS, poll=0.5):
                return await self.dialog_turn()
            if (switched := await self.switch_quest_turn()) is not None:
                return switched
            raise StopRun("no active main quest and no dialog offering one")
        if (reason := unsupported_reason(quest.get("title"))) is not None:
            self.say_once("quest", f"skipping {quest['title']}: {reason}")
            if (switched := await self.switch_quest_turn()) is not None:
                return switched
        goals = open_goals(quest)
        goal = goals[0] if goals else {"type": "persona", "destination_zone": ""}
        arrow = await read_quest_arrow(self.client)
        if arrow_shows_no_target(arrow):
            if (travelled := await self.go_to_quest_area_turn(quest, goals)) is not None:
                return travelled
            arrow, goal = await self.goal_with_a_target(goals, goal)
            if arrow is None and goal["type"] in ("bounty", "bountycollect") and goal.get("target_code"):
                return await self.explore_turn(goal, goals)
            if arrow is None:
                raise StopRun(f"the quest arrow shows no target for the {goal['type']} goal of "
                              f"{quest.get('title') or quest['name_key']}, and neither its tags {goal.get('tags')} "
                              f"nor its enemy {goal.get('target_code')} could be found; left for the operator")
        self.record.quest = {"name": quest["name_key"], "title": quest.get("title"), "goal": goal["type"],
                             "goal_id": goal.get("id"), "main": quest["mainline"] is True,
                             "goal_zone": goal["destination_zone"], "arrow": plain(arrow)}
        here = await self.client.zone_name()
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
        refill = short_for_a_fight(health_fraction(state), mana_fraction(state)) if goal["type"] in FIGHT_GOALS else None
        if refill is None and (self._topping_up_in == state["zone"] or not mana_to_travel(mana_fraction(state))):
            refill = "mana"
        if refill is not None:
            turn = await self.refill_turn(refill, state)
            if turn is not None:
                return turn
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

    async def switch_quest_turn(self, *, side_quests_only: bool = False) -> dict | None:
        """Make another quest the active one through the quest book (`questbook.activate_quest`), when the offer
        policy takes side quests: the next side quest, the one ready to hand in first, each at most
        MAX_ACTIVATIONS_PER_QUEST times a run; and with no active quest and no side quest left, the main quest.
        None when there is nothing to switch to."""
        if not getattr(self.offer_policy, "side_quests", False):
            return None
        quests = await read_quests(self.client)
        journal, active_title = quests["journal"], (quests["active"] or {}).get("title")
        titled = [entry for entry in journal if entry.get("title") and entry["title"] != active_title
                  and not unsupported_reason(entry["title"])
                  and self.record.quests_activated.get(entry["title"], 0) < MAX_ACTIVATIONS_PER_QUEST]
        side_quests = [entry for entry in titled if entry["mainline"] is not True]
        main_quests = [] if side_quests_only else [entry for entry in titled if entry["mainline"] is True]
        candidates = side_quests or main_quests
        if not candidates:
            return None
        choice = next((entry for entry in candidates if entry["ready_to_turn_in"]), candidates[0])
        title = choice["title"]
        self.record.quests_activated[title] = self.record.quests_activated.get(title, 0) + 1
        activation = await activate_quest(self.client, title)
        problem = activation.problem
        if activation.area:
            self._quest_areas[title] = activation.area
        active = (await read_quests(self.client))["active"]
        switched = problem is None and active is not None and active.get("title") == title
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

    def saw_enemies(self, zone) -> None:
        """Remember that `zone` has enemies, for this run and, through the knowledge file, later ones."""
        if isinstance(zone, str) and zone not in self.record.zones_with_enemies:
            self.record.zones_with_enemies.append(zone)

    async def safe_zone_refill_turn(self, stat: str, state: dict, planner: RoutePlanner) -> dict | None:
        """In a zone where no enemy has been met. Health alone is not waited for (the operator: resting "is not time
        efficient"), so None and the wizard walks on. Mana is: the operator allowed waiting in Olde Town for it, or
        looking for wisps. The zone is searched once for mana wisps, safe here, then the wizard stands still while
        mana comes back (`wait_for_mana_turn`) until `progress.topped_up`; health comes back meanwhile."""
        if stat == "health" and mana_for_a_fight(mana_fraction(state)):
            return None
        self.top_up_in(state["zone"])
        turn = await self.explore_for_wisps_turn("mana", state, planner, reach=refill_reach(True), again=False)
        return turn if turn is not None else await self.wait_for_mana_turn(state)

    def top_up_in(self, zone: str) -> None:
        """From now on, refill mana in `zone` until `progress.topped_up`, not just until a fight is allowed. Set as
        soon as a mana refill begins in a zone without enemies: set only once its search began, a first wisp in Olde
        Town brought mana from 11 to 14, over the 12 a fight needs, and the wizard went back to Cyclops Lane."""
        if self._topping_up_in != zone:
            self._topping_up_in = zone
            self.record.explored.pop(f"{zone}|{MANA_WISP}s", None)

    async def wait_for_mana_turn(self, state: dict) -> dict:
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
        self.events.emit("mana", f"waited in {state['zone']} for mana: {state['mana']} -> {now['mana']} of "
                                 f"{now['max_mana']}, health {state['health']} -> {now['health']}")
        gained = any(isinstance(now[stat], int) and isinstance(state[stat], int) and now[stat] > state[stat]
                     for stat in ("mana", "health"))
        return (progressed if gained else stalled)("waited for mana", before=state["mana"], after=now["mana"])

    async def commons_trip_turn(self, stat: str, state: dict) -> dict | None:
        """Short of mana in a street with no wisp to fetch, or of health in a zone too small to look for wisps in
        (a Golem Tower floor has one place to look): mark the spot (Mark Location costs about 5 mana, so only with
        MARK_MANA_NEEDED), then Go to The Commons, the world's hub, where mana and health come back (free; a walk
        back through the exits met enemies, and in Cyclops Lane fetching wisps cost more mana than it gave).
        `back_from_the_commons_turn` returns to the mark. None when the tools cannot be used now, so the wizard
        walks."""
        zone = state["zone"]
        if self._marked_in is None and isinstance(state["mana"], int) and state["mana"] >= MARK_MANA_NEEDED:
            problem = await mark_here(self.client)
            self.events.emit("travel", f"marked the spot in {zone} before leaving for mana" if problem is None else
                                       f"could not mark the spot in {zone}: {problem}")
            self._marked_in = zone if problem is None else None
        problem = await go_to_the_commons(self.client)
        if problem is not None:
            self.events.emit("travel", f"could not go to the Commons for mana: {problem}")
            return None
        self.events.emit("travel", f"went to the Commons from {zone} with {state['mana']} mana and {state['health']} "
                                   f"health, to refill {stat} there")
        return progressed("went to the Commons for a refill", stat=stat)

    async def back_from_the_commons_turn(self, state: dict) -> dict | None:
        """After a trip to the Commons: refill there (mana wisps, then standing still, as in any zone without
        enemies; health comes back as the wizard stands), and Recall Location once `progress.ready_to_recall`.
        None when no spot is marked or the wizard is where it was marked."""
        if self._marked_in is None or state["zone"] == self._marked_in:
            self._marked_in = None
            return None
        if ready_to_recall(mana_fraction(state), health_fraction(state)):
            return await self.recall_turn(state)
        if not ready_to_recall(mana_fraction(state), None):
            return await self.safe_zone_refill_turn("mana", state, await self.planner())
        return await self.wait_for_mana_turn(state)

    async def recall_turn(self, state: dict) -> dict | None:
        """Recall Location to the spot marked before leaving. Recall costs about 5 mana. None when nothing is
        marked or the wizard is where it was."""
        marked_in = self._marked_in
        if marked_in is None:
            return None
        if state["zone"] == marked_in or not await has_mark(self.client):
            self._marked_in = None
            return None
        problem = await recall(self.client)
        self._marked_in = None
        if problem is not None:
            self.events.emit("travel", f"could not recall to {marked_in}: {problem}; the quest walk goes on")
            return stalled("could not recall", problem=problem)
        self.events.emit("travel", f"recalled to the spot marked in {marked_in}, with {state['mana']} mana")
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
        part has been seen, start over, since used-up wisps come back; or, with `again` false, None."""
        kind = HEALTH_WISP if stat == "health" else MANA_WISP
        explored = self.record.explored.setdefault(f"{state['zone']}|{kind}s", [])
        me = await self.client.body.position()
        area = next_area_to_explore(planner.exploration_points, me=(me.x, me.y), explored=explored)
        if area is None and not again:
            return None
        if area is None:
            explored.clear()
            area = next_area_to_explore(planner.exploration_points, me=(me.x, me.y))
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
        if turn.get("trip", {}).get("reason") in (None, f"{kind} in sight", "every route method failed"):
            explored.append((round(x), round(y)))
        return turn

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
        if prompt_offers_talk(await or_default(interact_prompt_text(self.client), "")):
            return False
        npc = await or_default(nearest_npc(self.client), None)
        return npc is None or flat_distance(here, npc) > NPC_PROMPT_RANGE

    async def enter_with_x_turn(self) -> dict:
        """Press X at a door's interact prompt and give the zone change a few seconds to start. When a dialog opens
        instead, the prompt was a person's: prompts within NOT_A_DOOR_RADIUS of that spot are not taken for a door
        again this run. By Olde Town's gate to Triton Lane, an NPC out of NPC_PROMPT_RANGE gave a side quest, and
        then the wizard pressed X at him again after every dialog until the run was stopped."""
        zone = await self.client.zone_name()
        here = await self.client.body.position()
        action = prompt_action(await or_default(interact_prompt_text(self.client), ""))
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
        """The duel circle nearest the wizard when every route method failed, the wizard barely moved, and a route
        exists without the circles: another player's fight is on the only way, not enemies."""
        if trip["reason"] != "every route method failed" or moved >= BARELY_MOVED_DISTANCE:
            return None
        here = await self.client.body.position()
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

    def hazards_for(self, planner: RoutePlanner, zone: str, start, destination, arrive_radius: float, *,
                    avoid, duel_circles) -> tuple[Hazards, list[dict]]:
        """Everything a walk from `start` to `destination` keeps away from, and the enemies it routes around
        where they will be (none in the grace after a battle)."""
        now = time.monotonic()
        self.motion.observe(avoid, now)
        around = [] if self.in_grace_after_battle() else enemies_to_route_around(avoid, me=start, destination=destination)
        hazards = Hazards.of(enemies=[enemy["position"] for enemy in avoid], duel_circles=duel_circles,
                             obstacles=self.record.obstacles.get(zone, []), patrols=planner.streets,
                             keep_out=planner.teleports_to_keep_out_of(start, destination, arrive_radius),
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
               use_potions: bool = False, wear_gear: bool = False, use_travel_buttons: bool = False):
    """Attach to the game, play, remove the hooks, and always save the report, even when interrupted.
    Returns the report and the path it was saved to."""
    record = RunRecord(limits=limits)
    knowledge = Knowledge.load(settings.knowledge_file)
    knowledge.give_to(record)
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
                              use_potions=use_potions, wear_gear=wear_gear, use_travel_buttons=use_travel_buttons)
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
