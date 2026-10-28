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
}


def unsupported_reason(title: str | None) -> str | None:
    """Why the framework cannot do the side quest called `title`, or None."""
    return UNSUPPORTED.get(title) if title else None
