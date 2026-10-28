"""Walking into a zone door without sending a key once the zone change has begun. No game access: the turn
passes in how to tap W and how to tell that the change has begun, so it is tested offline.

Keys sent while a zone change starts are played again in the new zone, on the old heading. The walk to Olde
Town's gate into Triton Avenue stops within 150 units of the gate, and its last steps sometimes ended inside the
gate's volume and began the change. The door turn then faced the gate, which tapped A and D for seconds while the
facing did not answer, and pushed W for 0.8 s. In Triton Avenue those keys ran the wizard about 400 units on, back
into the gate to Olde Town; the game sent it there as soon as the 3.3 s arrival grace ended. Four crossings in a
row bounced that way (2026-10-27). In trials, one fixed 0.8 s push carried the wizard about 500 units after it
arrived; short taps with a check between them left it where the game put it in 13 of 14 crossings that began
outside the gate.

The change shows within a fraction of a second: the game puts up its transition window as the server answers.
"""

from __future__ import annotations

import asyncio
import time

CHANGE_START_SECONDS = 0.6
DOOR_TAP_SECONDS = 0.1
DOOR_PUSH_SECONDS = 0.8
CHECK_AFTER_TAP_SECONDS = 0.15
CHANGE_POLL_SECONDS = 0.05


async def change_begins(change_begun, seconds: float, *, clock=time.monotonic, sleep=asyncio.sleep) -> bool:
    """Whether `change_begun()` turns true within `seconds`, asking every CHANGE_POLL_SECONDS."""
    deadline = clock() + seconds
    while not await change_begun():
        if clock() >= deadline:
            return False
        await sleep(CHANGE_POLL_SECONDS)
    return True


async def push_through(tap_w, change_begun, *, clock=time.monotonic, sleep=asyncio.sleep) -> bool:
    """Tap W for DOOR_TAP_SECONDS at a time, DOOR_PUSH_SECONDS in all, and stop the moment the zone change begins,
    so at most one short tap can be played again in the new zone. Whether the change began."""
    for _ in range(round(DOOR_PUSH_SECONDS / DOOR_TAP_SECONDS)):
        await tap_w(DOOR_TAP_SECONDS)
        if await change_begins(change_begun, CHECK_AFTER_TAP_SECONDS, clock=clock, sleep=sleep):
            return True
    return False
