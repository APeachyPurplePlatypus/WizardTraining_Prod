"""Where to look for a quest goal the quest arrow does not lead to. No game access, so it is tested offline.

Some goals show no arrow: things to collect, hidden spots to visit. The game files still say where they are, in
three ways this module reads, in this order:

1. Placed objects named by the goal's tags, in the zone's gamedata.bin (`placed.objects_for_goal`): Triton
   Avenue's Cogs ("Clear as Crystal") carried the tag WC_TA_Cog, and six "WC_TA_Cog instance" objects stood there.
2. Trigger volumes, in the zone's volumes.xml, named after the quest: the game counts a visit when the wizard walks
   into one. "Find the Smiths" ("Find all the Smiths for Zeke in Wizard City") had one "<zone> Smith" volume in
   each of ten zones, and goals with no tags.
3. The zone's one ExploreObject, for an "Explore" goal (`placed.explore_spot`); the Smiths' volumes stood on them.

Enemies a goal names are found from the live entity list elsewhere (`QuestLoop.target_without_arrow`). The wizard
walks to the nearest spot not yet tried; one that does not move the goal on is not tried again, and when no source
has a spot left the quest is parked until the wizard404 API can say more.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass

from .placed import PlacedObject, explore_spot, objects_for_goal

QUEST_WORD = re.compile(r"[A-Za-z']{4,}")
COMMON_WORDS = frozenset({"find", "collect", "defeat", "gather", "talk", "speak", "visit", "with", "from", "into",
                          "your", "some", "this", "that", "them", "they", "their", "have", "what", "more", "back",
                          "wizard", "city", "quest"})


@dataclass(frozen=True)
class TriggerVolume:
    """A named trigger area in a zone's volumes.xml, by its center."""
    name: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Spot:
    """A place to walk to for a goal, how it was found (`source`) and what it is (`name`); `placed` is the placed
    object, for one found by the goal's tags."""
    name: str
    source: str
    x: float
    y: float
    z: float
    placed: PlacedObject | None = None

    @property
    def key(self) -> str:
        return f"{self.x:.0f},{self.y:.0f}"


ENTER_EVENT = re.compile(rb"Enter_[\x20-\x7e]+")


def parse_trigger_volumes(data: bytes) -> list[TriggerVolume]:
    """Each volume in a zone's volumes.xml that has an "Enter_<name>" event, by its center. The layout, as for the
    teleport volumes (`teleports.parse_teleport_volumes`): a name is stored after a byte holding twice its length,
    and the center's x, y and z are floats 8, 20 and 32 bytes after the name. Checked on Wizard City's ten "<zone>
    Smith" volumes, each on the zone's ExploreObject_WC."""
    volumes, seen = [], set()
    for event in ENTER_EVENT.finditer(data):
        start = event.start()
        if start < 1 or data[start - 1] // 2 <= len(b"Enter_"):
            continue
        name = data[start + len(b"Enter_"):start + data[start - 1] // 2]
        if not name or name in seen:
            continue
        seen.add(name)
        record = data.find(bytes([2 * len(name)]) + name)
        while record != -1 and data[max(0, record - 5):record + 1].endswith((b"Exit_", b"nter_")):
            record = data.find(bytes([2 * len(name)]) + name, record + 1)
        end = record + 1 + len(name)
        if record == -1 or end + 36 > len(data):
            continue
        x, y, z = (struct.unpack_from("<f", data, end + offset)[0] for offset in (8, 20, 32))
        if all(math.isfinite(value) for value in (x, y, z)) and max(abs(x), abs(y)) < 200_000 and abs(z) < 20_000:
            volumes.append(TriggerVolume(name.decode("ascii", "replace"), x, y, z))
    return volumes


WALK_IN_WORD = re.compile(r"(?:^|[\s_])to[\s_]", re.IGNORECASE)
WALK_IN_RADIUS = 150.0


def walk_in_teleports(volumes: list[TriggerVolume]) -> list[TriggerVolume]:
    """Trigger volumes, other than the TeleportVol_ ones, whose names say where they lead ("Activator Volume
    To_Kraken"): walked into, they move the wizard like a teleport volume. Triton Avenue's Kraken stands on an isle
    reached only through "Activator Volume To_Kraken"; with it unknown, every route to the Kraken failed and the
    bounty stalled until the run stopped (17:55 to 17:59)."""
    return [volume for volume in volumes
            if not volume.name.startswith("TeleportVol_") and WALK_IN_WORD.search(volume.name)]


def quest_words(*texts: str | None) -> set[str]:
    """The telling words of a quest's title or a goal's text, lowercase, each with its singular: "Find the Smiths"
    gives {"smiths", "smith"}."""
    words = set()
    for text in texts:
        for word in QUEST_WORD.findall(text or ""):
            word = word.lower().strip("'")
            if word in COMMON_WORDS:
                continue
            words.add(word)
            if word.endswith("s") and len(word) > 4:
                words.add(word[:-1])
    return words


def volumes_for_quest(volumes: list[TriggerVolume], words: set[str]) -> list[TriggerVolume]:
    """The trigger volumes whose names hold one of the quest's words as a word of their own."""
    return [volume for volume in volumes
            if words & {part.lower() for part in re.findall(r"[A-Za-z']+", volume.name)}]


def spots_for_goal(goal: dict, *, quest_title: str | None, tagged: list[PlacedObject], placed: list[PlacedObject],
                   volumes: list[TriggerVolume], me, tried: set[str] = frozenset(),
                   visited: list[str] = ()) -> list[Spot]:
    """The spots of the first source that has any not yet tried, nearest to `me` first: placed objects by the
    goal's tags (`tagged`, not `visited`), then trigger volumes named after the quest, then the zone's Explore
    object (from `placed`)."""
    tags = goal.get("tags") or []
    sources = [
        [Spot(thing.template, "tag", thing.x, thing.y, thing.z, thing)
         for thing in objects_for_goal(tagged, tags, me=me, visited=list(visited))] if tags else [],
        [Spot(volume.name, "trigger volume", volume.x, volume.y, volume.z)
         for volume in volumes_for_quest(volumes, quest_words(quest_title))],
        [Spot(spot.template, "explore object", spot.x, spot.y, spot.z)
         for spot in [explore_spot(placed, goal)] if spot is not None],
    ]
    for spots in sources:
        fresh = [spot for spot in spots if spot.key not in tried]
        if fresh:
            return sorted(fresh, key=lambda spot: math.dist((spot.x, spot.y), (me[0], me[1])))
    return []
