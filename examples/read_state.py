"""Watch the game for a while without touching it: state, quest arrow and nearby enemies, once a second.

A safe first script. It sends no keys and writes no game values; the reading hooks are removed when it
ends, however it ends.

    python examples/read_state.py 30
"""

from __future__ import annotations

import asyncio
import sys

from wizardtraining.entities import surroundings
from wizardtraining.quests import read_quest_arrow
from wizardtraining.session import attached
from wizardtraining.state import attempt, snapshot
from wizardtraining.targets import summary

DEFAULT_SECONDS = 20


async def watch(seconds: int) -> None:
    async with attached() as attachment:
        client = attachment.client
        print("hooks:", attachment.hooks)
        for _ in range(seconds):
            state = await snapshot(client)
            enemies, circles = await surroundings(client)
            print(state["zone"], state["position"], "health", state["health"],
                  "arrow", await attempt(read_quest_arrow(client, wait_seconds=0.5)),
                  "enemies", summary(enemies, limit=3), "duels", len(circles))
            await asyncio.sleep(1)
    print("hooks removed:", attachment.hooks_removed)


if __name__ == "__main__":
    asyncio.run(watch(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SECONDS))
