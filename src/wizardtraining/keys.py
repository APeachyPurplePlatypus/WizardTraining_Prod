"""The keys the framework may send, and a key held down while walking.

Keys go to the game window as window messages, so the window does not need focus. Only ALLOWED_KEYS
are sent; anything else raises RefusedKey. Notable keys refused, from the game's default bindings:
Q opens the quest book (which hides the NPC interact prompt), End and Home travel to the hub or home,
Escape opens the main menu, Ctrl+S the Crown Shop, and Ctrl+T hides the quest helper. Q and E do not
strafe. Space advances dialogs; outside one it only jumps.

Z opens Photomancy's Viewfinder, and is sent only for a quest goal that asks for a photo (`for_photo`; the
operator, 2026-10-28, 14:55 UTC: "Approve photo").
"""

from __future__ import annotations

import asyncio
import ctypes

ALLOWED_KEYS = frozenset({"W", "A", "S", "D", "X", "SPACEBAR"})
PHOTO_KEYS = frozenset({"Z"})
KEY_REPEAT_SECONDS = 0.05
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101


class RefusedKey(ValueError):
    pass


def check_allowed(key, *, for_photo: bool = False) -> None:
    if key.name not in ALLOWED_KEYS and not (for_photo and key.name in PHOTO_KEYS):
        raise RefusedKey(f"{key.name} is not one of the keys this framework sends")


async def tap(client, key, seconds: float, *, for_photo: bool = False) -> None:
    """Hold `key` for `seconds`. WizWalker sends the key-up even if this is cancelled. Z only `for_photo`."""
    check_allowed(key, for_photo=for_photo)
    await client.send_key(key, seconds)


class HeldKey:
    """Hold a key until released, repeating key-down like a held physical key. Always releases on exit."""

    def __init__(self, client, key):
        check_allowed(key)
        self._window, self._key, self._task = client.window_handle, key, None

    async def _repeat_down(self) -> None:
        while True:
            ctypes.windll.user32.SendMessageW(self._window, WM_KEYDOWN, self._key.value, 0)
            await asyncio.sleep(KEY_REPEAT_SECONDS)

    def press(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._repeat_down())

    async def release(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        ctypes.windll.user32.SendMessageW(self._window, WM_KEYUP, self._key.value, 0)

    async def __aenter__(self) -> "HeldKey":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.release()
