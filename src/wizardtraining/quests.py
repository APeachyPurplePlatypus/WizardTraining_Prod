"""The quest journal, the active quest's goals, and the quest arrow.

`QuestData.mainline()` tells main quests from side quests. Quest and goal names are language codes
(such as "QuestTitle_..."); `game_language()` turns them into the titles the game shows, which is what
an NPC's services menu lists. A quest's main-quest flag can be read only once it is in the journal:
the quest definitions live on the game's servers, not in the installed files. Goal types handled so far: bounty and bountycollect
(defeat enemies), persona (talk to an NPC), waypoint (reach a place, sometimes a door) and usage
(use an object). The quest arrow points at the current goal: the NPC for persona, the target enemies
for bounty. While no quest is active, the active id reads 0 and the arrow cannot be read.
"""

from __future__ import annotations

import asyncio

from wizwalker import Wad

from .language import LanguageFiles
from .state import attempt

QUEST_ARROW_WAIT_SECONDS = 3.0
QUEST_ARROW_POLL_SECONDS = 0.25


_game_language: LanguageFiles | None = None


def game_language() -> LanguageFiles:
    """The installed game's English language files, read from Root.wad as needed."""
    global _game_language
    if _game_language is None:
        root = Wad.from_game_data("Root")
        _game_language = LanguageFiles(root.get_file)
    return _game_language


async def read_quests(client) -> dict:
    """The journal, and the active quest with its goals (None when no quest is active)."""
    active_id = await attempt(client.quest_id())
    manager = await client.quest_manager()
    journal, active = [], None
    for quest_id, quest in (await manager.quest_data()).items():
        entry = {
            "id": quest_id,
            "name_key": await attempt(quest.name_lang_key()),
            "mainline": await attempt(quest.mainline()),
            "level": await attempt(quest.quest_level()),
            "ready_to_turn_in": await attempt(quest.ready_to_turn_in()),
        }
        entry["title"] = await _title(entry["name_key"])
        journal.append(entry)
        if quest_id == active_id:
            active = entry
            entry["goals"] = [
                {
                    "id": goal_id,
                    "name_key": await attempt(goal.name_lang_key()),
                    "type": await attempt(goal.goal_type()),
                    "destination_zone": await attempt(goal.goal_destination_zone()),
                    "done": await attempt(goal.goal_status()),
                }
                for goal_id, goal in (await quest.goal_data()).items()
            ]
    return {"active": active, "journal": journal}


async def _title(name_key) -> str | None:
    if not isinstance(name_key, str):
        return None
    try:
        return await game_language().text(name_key)
    except Exception:
        return None


def arrow_shows_no_target(arrow) -> bool:
    """The arrow reads (0, 0, 0) when it has no target: with no quest active, and for some goals such as
    collecting an item from the street. Walking to the map's origin then helps nobody."""
    return all(abs(value) < 1.0 for value in (arrow.x, arrow.y, arrow.z))


def open_goals(quest: dict) -> list[dict]:
    return [goal for goal in quest["goals"] if goal["done"] is False]


async def read_quest_arrow(client, wait_seconds: float = QUEST_ARROW_WAIT_SECONDS):
    """The quest arrow's target. Its hook writes nothing until the arrow updates, so wait briefly."""
    give_up_at = asyncio.get_running_loop().time() + wait_seconds
    while True:
        try:
            return await client.quest_position.position()
        except Exception:
            if asyncio.get_running_loop().time() > give_up_at:
                raise
            await asyncio.sleep(QUEST_ARROW_POLL_SECONDS)
