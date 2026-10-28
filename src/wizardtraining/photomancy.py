"""A photo for a quest goal: Z opens Photomancy's Viewfinder, its "Take Picture" button takes the photo, and its own
close button closes it; nothing else is clicked (docs/safety.md; the operator, 2026-10-28, 14:55 UTC: "Approve
photo"). Window paths read in the game (11:06, the robe shop): the Viewfinder is WorldView/SelfieCameraWindow."""

from __future__ import annotations

import asyncio
import time

from wizwalker import Keycode

from .keys import tap
from .ui import click, enable_clicks, message_box, showing

VIEWFINDER = ["WorldView", "SelfieCameraWindow"]
SHUTTER = [*VIEWFINDER, "MainWindow", "TakePictureButton"]
CLOSE_VIEWFINDER = [*VIEWFINDER, "MainWindow", "CloseSelfieCameraWindow"]
PHOTO_ITEM = "Photomancy"
OPEN_TIMEOUT_SECONDS = 5.0
POLL_SECONDS = 0.3
SHUTTER_SECONDS = 3.0
CLOSE_SECONDS = 1.5
TOOK, NOT_OPENED, BOX_SHOWN = "took a photo", "the Viewfinder did not open", "a message box showed after the photo"


async def shows_within(client, path: list[str], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await showing(client, path):
            return True
        await asyncio.sleep(POLL_SECONDS)
    return False


async def close_viewfinder(client) -> None:
    if await showing(client, CLOSE_VIEWFINDER):
        await click(client, CLOSE_VIEWFINDER)
        await asyncio.sleep(CLOSE_SECONDS)


async def take_photo(client) -> str:
    """Open the Viewfinder, take a photo, close it. A message box after the shutter is left for the operator."""
    await enable_clicks(client)
    if not await showing(client, VIEWFINDER):
        await tap(client, Keycode.Z, 0.1, for_photo=True)
    if not await shows_within(client, SHUTTER, OPEN_TIMEOUT_SECONDS):
        return NOT_OPENED
    await click(client, SHUTTER)
    await asyncio.sleep(SHUTTER_SECONDS)
    if await message_box(client) is not None:
        return BOX_SHOWN
    await close_viewfinder(client)
    return TOOK
