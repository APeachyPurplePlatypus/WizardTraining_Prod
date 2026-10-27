"""A read-only look at the running game: state, quests, the quest arrow and nearby enemies.

It installs the reading hooks, reads once and removes them. It sends no keys and writes no game values.
The hooks are still patches to the game's code, so it is read-only for the game state, not the process.
"""

from __future__ import annotations

import datetime

from .config import Settings
from .entities import surroundings
from .quests import read_quest_arrow, read_quests
from .reports import save_report
from .session import NoClient, attached
from .state import attempt, snapshot
from .targets import summary


async def probe(settings: Settings):
    report = {"source": "wizwalker", "simulated": False,
              "read_at": datetime.datetime.now().isoformat(timespec="seconds")}
    attachment = None
    try:
        async with attached() as attachment:
            client = attachment.client
            report["hooks"] = attachment.hooks
            report["state"] = await snapshot(client)
            report["in_npc_range"] = await attempt(client.is_in_npc_range())
            report["quest_arrow"] = await attempt(read_quest_arrow(client))
            report["quests"] = await _read_or_note(read_quests(client))
            report["nearby_enemies"] = await _read_or_note(_nearby_enemies(client))
    except NoClient as exc:
        report["error"] = str(exc)
    finally:
        if attachment is not None:
            report["hooks_removed"] = attachment.hooks_removed
        path = save_report("probe", report, settings.runtime_folder)
    return report, path


async def _nearby_enemies(client):
    enemies, circles = await surroundings(client)
    return {"enemies": summary(enemies, limit=10), "duel_circles": len(circles)}


async def _read_or_note(coro):
    try:
        return await coro
    except Exception as exc:
        return f"<unavailable: {type(exc).__name__}>"
