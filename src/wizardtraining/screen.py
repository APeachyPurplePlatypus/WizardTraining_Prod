"""What the game's window tree shows: windows found by name or by their text among the visible ones. No WizWalker
import: it walks any objects with the window methods (`children`, `is_visible`, `name`, `maybe_text`), so it is
tested offline with stand-ins.
"""

from __future__ import annotations

import re

MARKUP = re.compile(r"<[^>]*>")
FRIEND_BOX_TITLE = "friend"
FRIEND_REQUEST_QUESTION = "as your friend?"


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
