"""Game UI windows found by path, and clicks on them.

A path is the list of window names from the root window down, as Deimos's src/paths.py lists them.
Clicks use WizWalker's mouseless cursor: the game's cursor position is set in memory and the click
messages go to the window, so the real mouse does not move. Clicking scales positions by the UI scale,
which needs the render-context hook too; both are turned on only when something is clicked.
"""

from __future__ import annotations

from wizwalker import HookAlreadyActivated

from .session import HOOK_TIMEOUT_SECONDS

POTION_BUTTON = ["WorldView", "windowHUD", "btnPotions"]
ENDORSEMENT_WINDOW = ["WorldView", "EndorsementWindow"]
KNOWN_POPUPS = {
    "Endorse a Wizard": (ENDORSEMENT_WINDOW,
                         [*ENDORSEMENT_WINDOW, "MainLayout", "FriendlyWindow", "FriendlyButton"],
                         [*ENDORSEMENT_WINDOW, "CloseEndorsementWindowButton"],
                         "endorsed the other wizard as Friendly"),
}


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
    try:
        window = await window_at(client.root_window, path)
        if window is None:
            return ""
        return await window.maybe_text() or ""
    except Exception:
        return ""


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


async def answer_known_popup(client) -> str | None:
    """Answer the first showing popup in KNOWN_POPUPS and say what was done. These hold the keyboard until
    answered. The Endorse a Wizard window, shown after another player shared a battle, is answered Friendly,
    as the operator asked; the other player's name is never read. When the answer button is missing, the
    popup is closed with its own close button instead. Unknown popups are left alone."""
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
    """The visible windows under `path`, up to `depth` levels down and `limit` in all, as "parent/child" paths with
    their text after a colon when they have any: what the screen shows, for a report."""
    found = []

    async def walk(window, prefix: str, levels: int):
        for child in await window.children():
            if len(found) >= limit:
                return
            if not await child.is_visible():
                continue
            name = f"{prefix}{await child.name()}"
            text = (await child.maybe_text() or "").strip()
            found.append(f"{name}: {text[:60]}" if text else name)
            if levels > 1:
                await walk(child, f"{name}/", levels - 1)

    try:
        parent = await window_at(client.root_window, path)
        if parent is not None:
            await walk(parent, "", depth)
    except Exception:
        pass
    return found


async def visible_children(client, path: list[str]) -> list[str]:
    """Names of the visible windows directly under `path`: a quick, machine-readable look at the screen."""
    try:
        parent = await window_at(client.root_window, path)
        return [await child.name() for child in await parent.children() if await child.is_visible()]
    except Exception:
        return []

