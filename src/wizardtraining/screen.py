"""What the game's window tree shows: windows found by name among the visible ones, and the game's idle box told
by its text. No WizWalker import: it walks any objects with the window methods (`children`, `is_visible`, `name`),
so it is tested offline with stand-ins.
"""

from __future__ import annotations

IDLE_BOX_WORDS = ("return to combat", "you are idle")


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


def is_idle_box(caption: str) -> bool:
    """The game's idle box: "You Are Idle" (GUI_CombatAFKTitle), "Would you like to return to combat?"
    (GUI_CombatAFKMessage) and one button, "Return" (GUI_ReturnToCombat). Either line may be the caption read."""
    return any(words in caption.lower() for words in IDLE_BOX_WORDS)
