"""NPC dialogs: walk up, press X, and page through with Space, as Deimos's auto-dialogue does.

Window paths come from Deimos's src/paths.py (GPL-3.0). A page with a DECLINE button is a quest offer:
its other button, ACCEPT, is the one Space presses, so Space is never sent there and the `OfferPolicy`
decides instead. Finishing a quest opens a follow-up dialog a few seconds later that gives the next
main quest, so a conversation waits for follow-ups.

Reports keep page counts and lengths, not page text: NPCs address the wizard by name.
"""

from __future__ import annotations

import asyncio
import time

from wizwalker import Keycode

from .entities import nearest_npc
from .geometry import flat_distance
from .keys import tap
from .motion import WALK_UNITS_PER_SECOND
from .movement import face_and_step
from .policy import ACCEPT, DECLINE, GO_BACK, OfferPolicy
from .state import attempt
from .targets import close_enough
from .screen import TALK, USE, prompt_fits
from .ui import click, click_window, interact_prompt_text, showing, text_of, window_at

ADVANCE_BUTTON = ["WorldView", "wndDialogMain", "btnRight"]
DECLINE_BUTTON = ["WorldView", "wndDialogMain", "btnLeft"]
BACK_BUTTON = ["WorldView", "wndDialogMain", "btnBack"]
PAGE_TEXT = ["WorldView", "wndDialogMain", "txtArea", "txtMessage"]
SERVICES_MENU = ["WorldView", "NPCServicesWin"]
SERVICES_OPTIONS = ["WorldView", "NPCServicesWin", "ControlSprite", "optionsLayout"]
SERVICES_OPTION_BUTTON = "OptionButton"
SERVICES_EXIT = ["WorldView", "NPCServicesWin", "wndDialogMain", "Exit"]
DIALOG_FINISHED = "dialog finished"
NPC_OUT_OF_REACH = "could not get close enough to the quest NPC to talk"
OFFER_LEFT_FOR_OPERATOR = "a quest offer the offer policy would not handle; left for the operator"
TALK_KEY_SECONDS = 0.1
DIALOG_OPEN_TIMEOUT_SECONDS = 6.0
DIALOG_POLL_SECONDS = 0.3
SECONDS_PER_PAGE = 1.0
MAX_PAGES = 40
MAX_FOLLOW_UPS = 3
FOLLOW_UP_WAIT_SECONDS = 10.0
NPC_ARRIVE_DISTANCE = 200.0
TALK_DISTANCE = 80.0
OBJECT_USE_DISTANCE = 250.0
USE_SETTLE_SECONDS = 3.0
MAX_NUDGES = 5
NUDGE_STOP_DISTANCE = 30.0
NUDGE_LONGEST_SECONDS = 0.15
NUDGE_SETTLE_SECONDS = 0.5
PROMPT_TRUST_DISTANCE = 600.0
SAME_NPC_DISTANCE = 150.0


async def dialog_open(client) -> bool:
    return await showing(client, ADVANCE_BUTTON)


async def services_open(client) -> bool:
    """An NPC with several quests or services opens a menu of options (NPCServicesWin) instead of a dialog."""
    return await showing(client, SERVICES_MENU)


async def service_options(client) -> list[tuple[str, object]]:
    """The menu's options as (label, button). Quest options are labelled with the quest's title. A label that cannot
    be read is empty: a school professor's spell-training option is one, and reading it crashed the loop."""
    options = []
    layout = await window_at(client.root_window, SERVICES_OPTIONS)
    if layout is None:
        return options
    for option in await layout.children():
        if not await option.is_visible():
            continue
        for part in await option.children():
            if await part.name() == SERVICES_OPTION_BUTTON and await part.is_visible():
                label = await attempt(part.maybe_text())
                options.append(((label if isinstance(label, str) and not label.startswith("<unavailable") else "").strip(), part))
    return options


async def choose_service(client, button) -> None:
    await click_window(client, button)


async def leave_services(client) -> None:
    await click(client, SERVICES_EXIT)


async def wait_for_dialog(client, timeout: float, poll: float = DIALOG_POLL_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while not await dialog_open(client):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(poll)
    return True


async def near_npc(client, npc_position) -> bool:
    if flat_distance(await client.body.position(), npc_position) <= NPC_ARRIVE_DISTANCE:
        return True
    return await prompt_is_for(client, npc_position)


async def prompt_is_for(client, npc_position) -> bool:
    """The interact prompt shows, and the friendly NPC nearest the wizard is the one at `npc_position`.
    This lets the wizard talk across a counter it cannot walk around."""
    if flat_distance(await client.body.position(), npc_position) > PROMPT_TRUST_DISTANCE:
        return False
    if await attempt(client.is_in_npc_range()) is not True:
        return False
    nearest = await nearest_npc(client)
    return nearest is not None and flat_distance(nearest, npc_position) <= SAME_NPC_DISTANCE


async def walk_up_to(client, position, within: float = TALK_DISTANCE, *, trust_prompt: bool = True,
                     wants: str | None = None) -> list[dict]:
    """Face the NPC or object and creep closer until X would reach this one and not another nearby. A prompt that is
    not for what X is pressed for (`wants`: a talk or a quest object's use) counts as no prompt
    (`screen.prompt_fits`)."""
    nudges = []
    for _ in range(MAX_NUDGES):
        distance = flat_distance(await client.body.position(), position)
        prompt_showing = prompt_fits(await attempt(client.is_in_npc_range()), await interact_prompt_text(client),
                                     wants=wants)
        prompt_for_this_one = trust_prompt and prompt_showing and await prompt_is_for(client, position)
        nudges.append({"distance": round(distance, 1), "in_range": prompt_showing, "within": within,
                       "prompt_for_this_one": prompt_for_this_one})
        if close_enough(nudges):
            break
        step_seconds = min(NUDGE_LONGEST_SECONDS, (distance - NUDGE_STOP_DISTANCE) / WALK_UNITS_PER_SECOND)
        await face_and_step(client, position, step_seconds)
        await asyncio.sleep(NUDGE_SETTLE_SECONDS)
    return nudges


async def read_pages(client, record: dict, texts: list[str], offers: OfferPolicy) -> str:
    """Space through the pages. On an offer page, do what the offer policy decides."""
    went_back = False
    for _ in range(MAX_PAGES):
        if not await dialog_open(client):
            return DIALOG_FINISHED
        text = await text_of(client, PAGE_TEXT)
        texts.append(text)
        page = {"characters": len(text)}
        record["pages"].append(page)
        if not await showing(client, DECLINE_BUTTON):
            await tap(client, Keycode.SPACEBAR, TALK_KEY_SECONDS)
        else:
            can_go_back = not went_back and await showing(client, BACK_BUTTON)
            page["offer"] = decision = offers.decide(texts, can_go_back=can_go_back)
            if decision == ACCEPT:
                await click(client, ADVANCE_BUTTON)
            elif decision == DECLINE:
                await click(client, DECLINE_BUTTON)
            elif decision == GO_BACK and can_go_back:
                await click(client, BACK_BUTTON)
                went_back = True
            else:
                return OFFER_LEFT_FOR_OPERATOR
        await asyncio.sleep(SECONDS_PER_PAGE)
    return "page limit reached; left for the operator"


async def read_conversation(client, record: dict, offers: OfferPolicy) -> str:
    """Read the open dialog, then any follow-up dialogs that open within FOLLOW_UP_WAIT_SECONDS."""
    record.setdefault("pages", [])
    record["follow_ups"] = 0
    texts = record.setdefault("texts", [])
    while True:
        result = await read_pages(client, record, texts, offers)
        if result != DIALOG_FINISHED or record["follow_ups"] >= MAX_FOLLOW_UPS:
            return result
        if not await wait_for_dialog(client, FOLLOW_UP_WAIT_SECONDS, poll=0.5):
            return result
        record["follow_ups"] += 1


async def talk(client, npc_position, record: dict, offers: OfferPolicy, *, trust_prompt: bool = True) -> str:
    """Walk up to the NPC, open its dialog with X and read it. With `trust_prompt`, an interact prompt for the
    friendly NPC nearest the arrow is enough (it lets the wizard talk across a counter); without it, the
    wizard walks right up to the arrow first, for when a trusted prompt turned out to be someone else's."""
    if not await dialog_open(client):
        record["nudges"] = nudges = await walk_up_to(client, npc_position, trust_prompt=trust_prompt, wants=TALK)
        if not close_enough(nudges):
            return NPC_OUT_OF_REACH
        await tap(client, Keycode.X, TALK_KEY_SECONDS)
        if not await wait_for_dialog(client, DIALOG_OPEN_TIMEOUT_SECONDS):
            return "X pressed but no dialog appeared"
    return await read_conversation(client, record, offers)


async def use_object(client, position, record: dict, offers: OfferPolicy) -> str:
    record["nudges"] = nudges = await walk_up_to(client, position, within=OBJECT_USE_DISTANCE, wants=USE)
    if not close_enough(nudges):
        return "could not get close enough to the quest object to use it"
    await tap(client, Keycode.X, TALK_KEY_SECONDS)
    if await wait_for_dialog(client, USE_SETTLE_SECONDS):
        return await read_conversation(client, record, offers)
    return "used"
