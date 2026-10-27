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
from .movement import WALK_UNITS_PER_SECOND, face_and_step
from .policy import ACCEPT, DECLINE, GO_BACK, OfferPolicy
from .state import attempt
from .ui import click, showing, text_of

ADVANCE_BUTTON = ["WorldView", "wndDialogMain", "btnRight"]
DECLINE_BUTTON = ["WorldView", "wndDialogMain", "btnLeft"]
BACK_BUTTON = ["WorldView", "wndDialogMain", "btnBack"]
PAGE_TEXT = ["WorldView", "wndDialogMain", "txtArea", "txtMessage"]
DIALOG_FINISHED = "dialog finished"
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


async def walk_up_to(client, position, within: float = TALK_DISTANCE) -> list[dict]:
    """Face the NPC or object and creep closer until X would reach this one and not another nearby."""
    nudges = []
    for _ in range(MAX_NUDGES):
        distance = flat_distance(await client.body.position(), position)
        prompt_showing = await attempt(client.is_in_npc_range())
        prompt_for_this_one = await prompt_is_for(client, position)
        nudges.append({"distance": round(distance, 1), "in_range": prompt_showing, "within": within,
                       "prompt_for_this_one": prompt_for_this_one})
        if close_enough(nudges):
            break
        step_seconds = min(NUDGE_LONGEST_SECONDS, (distance - NUDGE_STOP_DISTANCE) / WALK_UNITS_PER_SECOND)
        await face_and_step(client, position, step_seconds)
        await asyncio.sleep(NUDGE_SETTLE_SECONDS)
    return nudges


def close_enough(nudges: list[dict]) -> bool:
    if not nudges:
        return False
    last = nudges[-1]
    return last["prompt_for_this_one"] or (last["distance"] <= last["within"] and last["in_range"] is True)


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
    texts = []
    while True:
        result = await read_pages(client, record, texts, offers)
        if result != DIALOG_FINISHED or record["follow_ups"] >= MAX_FOLLOW_UPS:
            return result
        if not await wait_for_dialog(client, FOLLOW_UP_WAIT_SECONDS, poll=0.5):
            return result
        record["follow_ups"] += 1


async def talk(client, npc_position, record: dict, offers: OfferPolicy) -> str:
    if not await dialog_open(client):
        record["nudges"] = nudges = await walk_up_to(client, npc_position)
        if not close_enough(nudges):
            return "could not get close enough to the quest NPC to talk"
        await tap(client, Keycode.X, TALK_KEY_SECONDS)
        if not await wait_for_dialog(client, DIALOG_OPEN_TIMEOUT_SECONDS):
            return "X pressed but no dialog appeared"
    return await read_conversation(client, record, offers)


async def use_object(client, position, record: dict, offers: OfferPolicy) -> str:
    record["nudges"] = nudges = await walk_up_to(client, position, within=OBJECT_USE_DISTANCE)
    if not close_enough(nudges):
        return "could not get close enough to the quest object to use it"
    await tap(client, Keycode.X, TALK_KEY_SECONDS)
    if await wait_for_dialog(client, USE_SETTLE_SECONDS):
        return await read_conversation(client, record, offers)
    return "used"
