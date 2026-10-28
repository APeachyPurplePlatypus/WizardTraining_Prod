"""The Spiral Map: the world gate's window, which X opens at the Spiral Door in Ravenwood's teleporter room.

It lists the worlds the wizard may go to, one button each (`optionWindow/wbtnKrokotopia`, `wbtnWizardCity`, ...: the
world's part of a zone path after "wbtn"), with "Go To World" (`teleportButton`) and "Exit" (`cancelButton`). Going
through a world gate is the natural way between worlds (AGENTS.md: "walking, doors and world gates"); only the
world's button, Go To World and Exit are clicked.
"""

from __future__ import annotations

import asyncio

from .gametravel import wait_for_zone_change
from .screen import plain_text
from .ui import click, showing, text_of

SPIRAL_MAP = ["WorldView", "", "messageBoxBG"]
CONTROLS = [*SPIRAL_MAP, "ControlSprite"]
TITLE = [*CONTROLS, "title"]
GO_BUTTON = [*CONTROLS, "teleportButton"]
EXIT_BUTTON = [*CONTROLS, "cancelButton"]
OPTIONS = [*CONTROLS, "optionWindow"]
SPIRAL_MAP_TITLE = "Spiral Map"
CHOOSE_SETTLE_SECONDS = 1.0


def world_button(world: str) -> list[str]:
    return [*OPTIONS, f"wbtn{world}"]


async def spiral_map_open(client) -> bool:
    return await showing(client, CONTROLS) and plain_text(await text_of(client, TITLE)) == SPIRAL_MAP_TITLE


async def go_to_world(client, world: str) -> str | None:
    """Choose `world` on the open Spiral Map and press Go To World; None once the zone changes."""
    if not await showing(client, world_button(world)):
        return f"{world} is not among the available worlds"
    zone = await client.zone_name()
    await click(client, world_button(world))
    await asyncio.sleep(CHOOSE_SETTLE_SECONDS)
    await click(client, GO_BUTTON)
    return None if await wait_for_zone_change(client, zone) else f"the zone did not change after Go To World ({world})"


async def leave_the_map(client) -> None:
    await click(client, EXIT_BUTTON)
    await asyncio.sleep(CHOOSE_SETTLE_SECONDS)
