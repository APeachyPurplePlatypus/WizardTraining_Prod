"""Game UI windows found by path, and clicks on them.

A path is the list of window names from the root window down, as Deimos's src/paths.py lists them.
Clicks use WizWalker's mouseless cursor: the game's cursor position is set in memory and the click
messages go to the window, so the real mouse does not move. Clicking scales positions by the UI scale,
which needs the render-context hook too; both are turned on only when something is clicked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from wizwalker import HookAlreadyActivated

from .screen import is_friend_request, or_default, plain_text, visible_named
from .session import HOOK_TIMEOUT_SECONDS

POTION_BUTTON = ["WorldView", "windowHUD", "btnPotions"]
ENDORSEMENT_WINDOW = ["WorldView", "EndorsementWindow"]
KNOWN_POPUPS = {
    "Endorse a Wizard": (ENDORSEMENT_WINDOW,
                         [*ENDORSEMENT_WINDOW, "MainLayout", "FriendlyWindow", "FriendlyButton"],
                         [*ENDORSEMENT_WINDOW, "CloseEndorsementWindowButton"],
                         "endorsed the other wizard as Friendly"),
}


INTERACT_PROMPT_TEXT = ["WorldView", "NPCRangeWin", "imgBackground", "NPCRangeTxtMessage"]
MESSAGE_BOX = "MessageBoxModalWindow"
MESSAGE_BOX_SEARCH_DEPTH = 4
BOX_LAYOUT = ["messageBoxBG", "messageBoxLayout"]
BOX_TITLE = [*BOX_LAYOUT, "", "TitleText"]
BOX_CAPTION = [*BOX_LAYOUT, "TextArea", "CaptionText"]
BOX_BUTTONS = [*BOX_LAYOUT, "AdjustmentWindow", "Layout"]
BOX_YES = [*BOX_BUTTONS, "centerButton"]
BOX_NO = [*BOX_BUTTONS, "rightButton"]
BOX_SETTLE_SECONDS = 1.5


@dataclass(frozen=True)
class MessageBox:
    window: object
    title: str
    caption: str


async def window_at(root, path: list[str]):
    if not path:
        return root
    for child in await root.children():
        if await child.name() == path[0]:
            found = await window_at(child, path[1:])
            if found is not None:
                return found
    return None


async def showing(client, path: list[str]) -> bool:
    try:
        window = await window_at(client.root_window, path)
        return window is not None and bool(await window.is_visible())
    except Exception:
        return False


async def text_of(client, path: list[str]) -> str:
    return await text_under(client.root_window, path)


async def text_under(parent, path: list[str]) -> str:
    try:
        window = await window_at(parent, path)
        if window is None:
            return ""
        return await window.maybe_text() or ""
    except Exception:
        return ""


async def interact_prompt_text(client) -> str:
    """What the interact prompt says, such as "Press X or to Talk", without markup; "" when it is not showing."""
    return plain_text(await text_of(client, INTERACT_PROMPT_TEXT))


async def enable_clicks(client) -> None:
    try:
        await client.hook_handler.activate_render_context_hook(wait_for_ready=True, timeout=HOOK_TIMEOUT_SECONDS)
    except HookAlreadyActivated:
        pass


async def click(client, path: list[str]) -> None:
    window = await window_at(client.root_window, path)
    if window is None:
        raise LookupError(f"no window at {'/'.join(path)}")
    await click_window(client, window)


async def click_window(client, window) -> None:
    await enable_clicks(client)
    async with client.mouse_handler:
        await client.mouse_handler.click_window(window)


async def message_box(client) -> MessageBox | None:
    """The message box on screen, else None: the first visible one within MESSAGE_BOX_SEARCH_DEPTH levels, searched
    through visible windows only. The flee box shows under WorldView/PlanningPhase, a friend request under WorldView.
    A box's own visible flag is not enough: while the planning window was hidden, one under it still read visible."""
    for window in await visible_named(client.root_window, MESSAGE_BOX, MESSAGE_BOX_SEARCH_DEPTH):
        return MessageBox(window, plain_text(await text_under(window, BOX_TITLE)),
                          plain_text(await text_under(window, BOX_CAPTION)))
    return None


async def decline_friend_request(client) -> str | None:
    """Answer another player's friend request No (the box's right button), and say so; None when none is showing.
    The player's name is never kept. The operator turned "Allow Friend Requests" to none in the game's privacy
    settings and asked that any that still come be declined: one left open took every click, and from then on no
    card the wizard played reached a battle, solo or shared, for over half an hour."""
    box = await message_box(client)
    if box is None or not is_friend_request(box.title, box.caption):
        return None
    await click_window(client, await window_at(box.window, BOX_NO))
    await asyncio.sleep(BOX_SETTLE_SECONDS)
    return "declined a friend request"


async def answer_known_popup(client) -> str | None:
    """Decline a friend request, or answer the first showing popup in KNOWN_POPUPS, and say what was done. These
    hold the keyboard or the mouse until answered. The Endorse a Wizard window, shown after another player shared a
    battle, is answered Friendly, as the operator asked; the other player's name is never read. When the answer
    button is missing, the popup is closed with its own close button instead. Unknown popups are left alone."""
    if declined := await decline_friend_request(client):
        return declined
    for name, (window, answer, close_button, answered) in KNOWN_POPUPS.items():
        if await showing(client, window):
            try:
                await click(client, answer)
                return answered
            except LookupError:
                await click(client, close_button)
                return f"closed the {name} window"
    return None


async def visible_tree(client, path: list[str], depth: int = 3, limit: int = 40) -> list[str]:
    """`visible_tree_under` the window at `path`, or [] when there is none."""
    parent = await or_default(window_at(client.root_window, path), None)
    return [] if parent is None else await visible_tree_under(parent, depth, limit)


async def visible_tree_under(parent, depth: int = 3, limit: int = 40) -> list[str]:
    """The visible windows under `parent`, up to `depth` levels down and `limit` in all, as "parent/child" paths
    with their text after a colon when they have any: what the screen shows, for a report."""
    found = []

    async def walk(window, prefix: str, levels: int):
        for child in await or_default(window.children(), []):
            if len(found) >= limit:
                return
            if not await or_default(child.is_visible(), False):
                continue
            name = f"{prefix}{await or_default(child.name(), '?')}"
            text = (await or_default(child.maybe_text(), "") or "").strip()
            found.append(f"{name}: {text[:60]}" if text else name)
            if levels > 1:
                await walk(child, f"{name}/", levels - 1)

    await walk(parent, "", depth)
    return found


async def visible_children(client, path: list[str]) -> list[str]:
    """Names of the visible windows directly under `path`: a quick, machine-readable look at the screen."""
    try:
        parent = await window_at(client.root_window, path)
        return [await child.name() for child in await parent.children() if await child.is_visible()]
    except Exception:
        return []

