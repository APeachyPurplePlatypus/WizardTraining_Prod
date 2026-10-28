"""The game's own travel buttons on the HUD: Mark Location, Go to The Commons (the world's hub) and Recall Location.

Allowed by the operator's decision of 2026-10-28 ("Teleporting only refers to using deimos, you are allow to teleport
using in game tools"; docs/safety.md). What stays forbidden is the framework moving the character itself: no write to
position, no Deimos or WizWalker teleport. These are buttons a player presses, found by the tooltips they show:
`MarkButton` "Mark Location", `GoHomeButton` "Go to The Commons", `RecallButton` "Recall Location", or "No Mark Set"
until a spot is marked. After a use, Go to The Commons and Recall show a timer (`txtGoHomeTimer`, `txtRecallTimer`)
while they cool down. `GotoDormButton` and `ResumeInstanceButton` are never clicked.
"""

from __future__ import annotations

import asyncio

from .screen import or_default
from .state import attempt
from .ui import click, showing, window_at

BUTTONS = ["WorldView", "windowHUD", "compassAndTeleporterButtons"]
MARK_BUTTON = [*BUTTONS, "MarkButton"]
HUB_BUTTON = [*BUTTONS, "GoHomeButton"]
RECALL_BUTTON = [*BUTTONS, "RecallButton"]
HUB_TIMER = [*HUB_BUTTON, "txtGoHomeTimer"]
RECALL_TIMER = [*RECALL_BUTTON, "txtRecallTimer"]
TIP_OFFSET = 520
NO_MARK_TIP = "No Mark Set"
MARK_SETTLE_SECONDS = 2.0
ZONE_CHANGE_WAIT_SECONDS = 25.0
ZONE_CHANGE_POLL_SECONDS = 0.5
RECALL_NOT_REACHED = "the zone did not change after Recall"


async def tip_of(client, path: list[str]) -> str:
    """The tooltip a button shows, read from the window's memory; "" when it cannot be read."""
    window = await window_at(client.root_window, path)
    if window is None:
        return ""
    return (await or_default(window.read_wide_string_from_offset(TIP_OFFSET), "")).strip()


async def cooling_down(client, timer_path: list[str]) -> bool:
    """The button's timer shows: it was used lately and cannot be used yet."""
    return await showing(client, timer_path)


async def recall_tip(client) -> str:
    """What the Recall button names: "No Mark Set", or the marked place."""
    return await tip_of(client, RECALL_BUTTON)


async def go_home_ready(client) -> bool:
    return not await cooling_down(client, HUB_TIMER)


async def recall_ready(client) -> bool:
    return await has_mark(client) and not await cooling_down(client, RECALL_TIMER)


async def has_mark(client) -> bool:
    tip = await tip_of(client, RECALL_BUTTON)
    return bool(tip) and tip != NO_MARK_TIP


async def mark_here(client) -> str | None:
    """Press Mark Location. None when a mark was set, else what went wrong. The game refuses in some places ("Can't
    Mark in this Area"; on a Golem Tower floor it showed no message at all), and the Recall button may still show
    an older mark, so "a mark shows" proves nothing: a mark was set when the Recall tooltip changed or mana was
    spent (Mark Location cost 5 mana in Cyclops Lane, and nothing on the tower floor, where it did nothing)."""
    tip_before, mana_before = await tip_of(client, RECALL_BUTTON), await attempt(client.stats.current_mana())
    await click(client, MARK_BUTTON)
    await asyncio.sleep(MARK_SETTLE_SECONDS)
    tip_after, mana_after = await tip_of(client, RECALL_BUTTON), await attempt(client.stats.current_mana())
    if not tip_after or tip_after == NO_MARK_TIP:
        return "the Recall button still shows no mark after Mark Location"
    paid = isinstance(mana_before, int) and isinstance(mana_after, int) and mana_after < mana_before
    if tip_after != tip_before or paid:
        return None
    return "the game refused Mark Location here: the Recall tooltip did not change and no mana was spent"


async def zone_changed(client, zone: str) -> bool:
    return await or_default(client.is_loading(), False) is True or await or_default(client.zone_name(), zone) != zone


async def wait_for_zone_change(client, zone: str) -> bool:
    deadline = asyncio.get_running_loop().time() + ZONE_CHANGE_WAIT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if await zone_changed(client, zone):
            return True
        await asyncio.sleep(ZONE_CHANGE_POLL_SECONDS)
    return False


async def go_to_the_commons(client) -> str | None:
    """Press Go to The Commons, the world's hub, and wait for the zone to change. None when it did."""
    if await cooling_down(client, HUB_TIMER):
        return "Go to The Commons is cooling down"
    zone = await client.zone_name()
    await click(client, HUB_BUTTON)
    return None if await wait_for_zone_change(client, zone) else "the zone did not change after Go to The Commons"


async def recall(client) -> str | None:
    """Press Recall Location and wait for the zone to change and the load to end. None when the wizard is in another
    zone then. A load that began is not enough: at 01:32 the game began one, then refused ("You cannot teleport to
    that location. The dungeon timer has ended and the dungeon has been reset.") and the wizard stayed in the
    Commons, while the run took the Recall for done."""
    if not await has_mark(client):
        return "no spot is marked"
    if await cooling_down(client, RECALL_TIMER):
        return "Recall is cooling down"
    zone = await client.zone_name()
    await click(client, RECALL_BUTTON)
    if not await wait_for_zone_change(client, zone):
        return RECALL_NOT_REACHED
    return None if await zone_after_loading(client) not in (None, zone) else RECALL_NOT_REACHED


async def zone_after_loading(client) -> str | None:
    """The zone once loading has ended, waiting up to ZONE_CHANGE_WAIT_SECONDS; None when it does not end."""
    deadline = asyncio.get_running_loop().time() + ZONE_CHANGE_WAIT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if await or_default(client.is_loading(), False) is not True:
            return await or_default(client.zone_name(), None)
        await asyncio.sleep(ZONE_CHANGE_POLL_SECONDS)
    return None
