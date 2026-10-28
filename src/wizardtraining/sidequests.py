"""Side quests the framework cannot do, by title, and why. No game access, so it is tested offline.

The loop switches to the side quests of a world before the main quest leaves it (`QuestLoop.switch_quest_turn`);
a quest listed here is left in the journal, with its reason said once, so the run does not stand at it until the
limit for turns without progress stops it.
"""

from __future__ import annotations

UNSUPPORTED = {
    "You Can Dig It": "the quest sends the wizard's pet out to dig up buried Spellbooks in Cyclops Lane (its text: "
                      "\"I'd need a Pet\"), and the framework leaves pets alone; the Dirt Mounds show no interact "
                      "prompt without one",
    "The Lore You Know": "its goal is in Lord Nightshade's dungeon (WC_HauntedCave_T1), whose door the Haunted Cave "
                         "street's zone data does not list, and its objects (the stolen history books) are not "
                         "placed objects the framework can find; the run walked into a wrong gate four times",
    "The Gravulum Order": "its goal is in Colossus Boulevard, whose tunnel from the Shopping District is closed: a "
                          "blocker (BigGenericBlocker_CollossusGate) stops the wizard about 100 units short of the "
                          "gate's trigger, with no prompt and no message (2026-10-28, 00:08 to 00:12); players say "
                          "Merle Ambrose opens it once Wizard City's other assignments are done, and that it may "
                          "need a membership",
}


QUEST_FINDER = "Quest Finder"
# The journal's Quest Finder: an entry named "Quest Finder" (its name is no language code, so it has no other title),
# whose one goal, once it is made the active quest, is a talk with the nearest giver of a quest not yet taken in the
# wizard's world. In the Krokotopia world teleporter room it pointed at the NPC standing there.
WORLD_DOOR = "Universe Teleport"
WORLD_DOOR_ROOMS = {"Krokotopia": "Krokotopia/KT_WorldTeleporter", "WizardCity": "WizardCity/WC_Ravenwood_Teleporter"}
WORLD_DOOR_WORDS = ("teleporter", "worldspiral")
# The Spiral Door is the placed object "Universe Teleport" in each world's teleporter room; the Krokotopia hub leads
# there by "Krok_Hub WorldSpiral Entrance". A quest in another world shows no quest arrow ((0, 0, 0) for "The Lore
# You Know" from Krokotopia), so the way there is known from these, not from the arrow.
FINDER_SAME_GIVER_LIMIT = 2


def unsupported_reason(title: str | None) -> str | None:
    """Why the framework cannot do the side quest called `title`, or None."""
    return UNSUPPORTED.get(" ".join(title.split())) if title else None


def in_world(page_zone: str | None, world: str) -> bool:
    """The quest page names a quest's world as "Wizard City"; zone paths begin with "WizardCity"."""
    return bool(page_zone) and page_zone.replace(" ", "").lower() == world.lower()


def next_quest_in_world(zones: dict[str, str], world: str, *, skip: set[str]) -> str | None:
    """The first quest the quest page lists in `world` that the framework can do, other than the Quest Finder and
    those in `skip`."""
    return next((title for title, zone in zones.items()
                 if in_world(zone, world) and title != QUEST_FINDER and not unsupported_reason(title)
                 and " ".join(title.split()) not in skip), None)


def finder_points_into(goal_zone: str | None, world: str) -> bool:
    return bool(goal_zone) and goal_zone.split("/", 1)[0] == world


def leads_to_the_world_door(volume_name: str) -> bool:
    """A teleport volume into a world's teleporter room, such as the Krokotopia hub's "WorldSpiral Entrance"."""
    name = volume_name.lower().replace(" ", "").replace("_", "")
    return any(word in name for word in WORLD_DOOR_WORDS)
