"""What the game's window tree shows: windows found by name or by their text among the visible ones. No WizWalker
import: it walks any objects with the window methods (`children`, `is_visible`, `name`, `maybe_text`), so it is
tested offline with stand-ins.
"""

from __future__ import annotations

import re

MARKUP = re.compile(r"<[^>]*>")
FRIEND_BOX_TITLE = "friend"
FRIEND_REQUEST_QUESTION = "as your friend?"
TALK_PROMPT_ENDING = "to talk"
NOT_DOOR_ACTIONS = ("talk", "collect", "use", "open", "read")
# What X does at a prompt that is not a door's: a person's "to Talk", a reagent's "to Collect" (leaving the Dark Cave a
# reagent's was taken for the door's, 11:39), an object's "to Use", a chest's "to Open", a sign's "to Read".


async def or_default(coro, default):
    """`coro`'s result, or `default` when it raises: one window that cannot be read, such as one without text, once
    ended a whole walk with nothing to show."""
    try:
        return await coro
    except Exception:
        return default


async def visible_named(root, name: str, depth: int) -> list:
    """The visible windows named `name` within `depth` levels below `root`, nearest the root first. Only visible
    windows are searched through, so what is found is on screen."""
    found, level = [], [root]
    for _ in range(depth):
        below = []
        for window in level:
            for child in await or_default(window.children(), []):
                if not await or_default(child.is_visible(), False):
                    continue
                below.append(child)
                if await or_default(child.name(), None) == name:
                    found.append(child)
        level = below
    return found


async def window_saying(root, words, depth: int) -> list | None:
    """The visible windows from just below `root` down to the first one, within `depth` levels, whose text mentions
    any of `words` (case aside), or None. The chain tells where it shows, whatever its window names."""
    async def walk(window, chain, levels):
        for child in await or_default(window.children(), []):
            if not await or_default(child.is_visible(), False):
                continue
            text = (await or_default(child.maybe_text(), "") or "").lower()
            if any(word in text for word in words):
                return [*chain, child]
            if levels > 1 and (found := await walk(child, [*chain, child], levels - 1)) is not None:
                return found
        return None

    return await walk(root, [], depth)


def plain_text(markup: str) -> str:
    """A window's text without the game's markup tags (<center>, <br>, <image;...>), spaces collapsed."""
    return " ".join(MARKUP.sub(" ", markup).split())


def is_friend_request(title: str, caption: str) -> bool:
    """Another player's friend request: a box titled "Friend" asking "Accept <player> ... as your friend?"."""
    return title.lower() == FRIEND_BOX_TITLE and caption.lower().endswith(FRIEND_REQUEST_QUESTION)


GAME_NOTICE_TITLE = "info"
GAME_NOTICE_BUTTONS = ["rightButton"]


def is_game_notice(title: str, buttons: list[str]) -> bool:
    """The game's own notice: a box titled "INFO" whose only button is its OK (`rightButton`), such as "You cannot
    teleport to that location. The dungeon timer has ended and the dungeon has been reset." Another player's
    request (friend, trade, duel) has another title and Yes and No buttons, and is never one."""
    return title.strip().lower() == GAME_NOTICE_TITLE and buttons == GAME_NOTICE_BUTTONS


TALK, USE = "talk", "use"


def prompt_fits(in_range, prompt: str, *, wants: str | None) -> bool:
    """The interact prompt shows and is for what X is pressed for: a talk's reads "to Talk", a quest object's anything
    else. By Private Emerson in Cyclops Lane another prompt showed (one that teleports), X was pressed for the talk
    three times, and each took the wizard 17,000 units to the top of the lane (2026-10-28, 08:14 to 08:22). By the
    Golem Court seedling of "The Facts of Life", 110 units from it, the prompt was Farley's "to Talk", 416 units away,
    and each X opened his shop menu (09:40)."""
    if in_range is not True:
        return False
    if wants == TALK:
        return prompt_offers_talk(prompt)
    if wants == USE:
        return not prompt_offers_talk(prompt)
    return True


def prompt_offers_talk(prompt: str) -> bool:
    """The interact prompt is a person's: it reads "Press X to Talk" (the game's NPCInteractText). A door's reads
    "to Enter" or "to Teleport", a chest's "to Open", an object's "to Use"."""
    return plain_text(prompt).lower().endswith(TALK_PROMPT_ENDING)


def prompt_is_not_a_doors(prompt: str) -> bool:
    return prompt_action(prompt).lower() in NOT_DOOR_ACTIONS


def prompt_action(prompt: str) -> str:
    """The word the interact prompt ends with, such as "Talk" or "Enter": what pressing X would do."""
    words = plain_text(prompt).split()
    return words[-1] if words else ""


async def visible_names_under(window, depth: int, limit: int = 60) -> list[str]:
    """The visible windows under `window`, `depth` levels down and `limit` in all, as "parent/child" names without
    their text, which can hold other players' names and chat."""
    found = []

    async def walk(parent, prefix, levels):
        for child in await or_default(parent.children(), []):
            if len(found) >= limit:
                return
            if not await or_default(child.is_visible(), False):
                continue
            name = f"{prefix}{await or_default(child.name(), '?')}"
            found.append(name)
            if levels > 1:
                await walk(child, f"{name}/", levels - 1)

    await walk(window, "", depth)
    return found
