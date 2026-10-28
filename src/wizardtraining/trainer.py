"""A school professor's spell training: open it from the professor's menu, learn the free spells offered, close it.

Window paths were read in the game at Lydia Greyrose (Ice) at levels 8 and 10. Talking to a professor opens a menu
of services; its spell-training option has no readable label (`dialog.service_options`). The training window
(NPCTrainingGUI) lists options with a name, a level and a cost; a school's own spells cost "Free". Training one asks
"Are you sure you want to add this spell to your spellbook?", then shows "New Spell LEARNED", closed by clicking it.

Only "Free" spells at or below the wizard's level are learned, and none while the gold banner shows: nothing is
bought (the operator: no training with gold).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from wizwalker import Keycode

from .dialog import (SERVICES_MENU, TALK_KEY_SECONDS, close_enough, dialog_open, leave_services, service_options,
                     walk_up_to)
from .keys import tap
from .ui import MessageBox, click, click_window, message_box, showing, window_at

TRAINING = ["WorldView", "NPCTrainingGUI"]
SELECTION = [*TRAINING, "TrainingSelection"]
SPELL_LIST = [*SELECTION, "SpellList"]
TRAIN_BUTTON = [*SELECTION, "TrainButton"]
EXIT_BUTTON = [*SELECTION, "ExitButton"]
GOLD_BANNER = [*SELECTION, "GoldBanner"]
REWARD = [*TRAINING, "wndSpellReward"]
REWARD_BUTTON = [*REWARD, "btnBackground"]
CONFIRM_BUTTON = ["MessageBoxModalWindow", "messageBoxBG", "messageBoxLayout", "AdjustmentWindow", "Layout",
                  "centerButton"]
CONFIRM_WORDS = "add this spell to your spellbook"
FREE = "Free"
MAX_SPELLS_PER_VISIT = 10
OPEN_TIMEOUT_SECONDS = 6.0
POLL_SECONDS = 0.3
SELECT_SECONDS = 1.0
CONFIRM_SECONDS = 2.0
LEARNED_SECONDS = 2.5
CLOSE_SECONDS = 1.5
OPENED_MENU, OPENED_DIALOG, OPENED_NOTHING = "menu", "dialog", "nothing"


@dataclass(frozen=True)
class Offer:
    window: object
    name: str
    level: int | None
    cost: str


def plain_text(text) -> str:
    return re.sub(r"<[^>]*>", "", text or "").strip()


async def child_named(window, name: str):
    for each in await window.children():
        if await each.name() == name:
            return each
    return None


async def text_in(window, *path: str) -> str:
    for name in path:
        window = await child_named(window, name) if window is not None else None
    try:
        return plain_text(await window.maybe_text()) if window is not None else ""
    except Exception:
        return ""


async def offers(client) -> list[Offer]:
    """The training window's options, in order."""
    spell_list = await window_at(client.root_window, SPELL_LIST)
    found = []
    for option in await spell_list.children() if spell_list is not None else []:
        if not (await option.name()).startswith("Option_") or not await option.is_visible():
            continue
        level = await text_in(option, "LevelBox", "Level")
        found.append(Offer(option, await text_in(option, "NameBox", "Name"), int(level) if level.isdigit() else None,
                           await text_in(option, "CostBox", "Cost")))
    return found


def free_at_level(offer: Offer, level: int) -> bool:
    return offer.cost == FREE and offer.level is not None and offer.level <= level


async def open_with_professor(client, professor) -> str:
    """Walk up to the professor and press X: whether a menu, a dialog or nothing opened."""
    if not close_enough(await walk_up_to(client, professor)):
        return OPENED_NOTHING
    await tap(client, Keycode.X, TALK_KEY_SECONDS)
    deadline = time.monotonic() + OPEN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if await showing(client, SERVICES_MENU):
            return OPENED_MENU
        if await dialog_open(client):
            return OPENED_DIALOG
        await asyncio.sleep(POLL_SECONDS)
    return OPENED_NOTHING


async def open_training(client) -> bool:
    """Choose the menu's unlabelled option, the spell training, and wait for the training window."""
    unlabelled = [button for label, button in await service_options(client) if not label]
    if not unlabelled:
        return False
    await click_window(client, unlabelled[0])
    deadline = time.monotonic() + OPEN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if await showing(client, SPELL_LIST):
            return True
        await asyncio.sleep(POLL_SECONDS)
    return False


async def learn_free_spells(client, level: int) -> tuple[list[str], list[str]]:
    """Learn each free spell offered at or below `level`, first offer first, while the gold banner is hidden.
    The names learned, and the offers left (as "Name (level n, cost)")."""
    learned = []
    for _ in range(MAX_SPELLS_PER_VISIT):
        if await showing(client, GOLD_BANNER):
            break
        offer = next((offer for offer in await offers(client) if free_at_level(offer, level)), None)
        if offer is None:
            break
        await click_window(client, await child_named(offer.window, "Image") or offer.window)
        await asyncio.sleep(SELECT_SECONDS)
        await click(client, TRAIN_BUTTON)
        await asyncio.sleep(CONFIRM_SECONDS)
        box: MessageBox | None = await message_box(client)
        if box is None or CONFIRM_WORDS not in box.caption.lower():
            break
        await click(client, CONFIRM_BUTTON)
        await asyncio.sleep(LEARNED_SECONDS)
        if await showing(client, REWARD):
            await click(client, REWARD_BUTTON)
            await asyncio.sleep(CLOSE_SECONDS)
        learned.append(offer.name)
    left = [f"{offer.name} (level {offer.level}, {offer.cost})" for offer in await offers(client)]
    return learned, left


async def close_training(client) -> None:
    if await showing(client, TRAINING):
        await click(client, EXIT_BUTTON)
        await asyncio.sleep(CLOSE_SECONDS)
    if await showing(client, SERVICES_MENU):
        await leave_services(client)
        await asyncio.sleep(CLOSE_SECONDS)
