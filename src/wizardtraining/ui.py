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
CLOSABLE_POPUPS = {
    "Endorse a Wizard": (["WorldView", "EndorsementWindow"],
                         ["WorldView", "EndorsementWindow", "CloseEndorsementWindowButton"]),
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


async def close_known_popup(client) -> str | None:
    """Close the first showing popup in CLOSABLE_POPUPS with its own close button, and return its name.
    These ask for an optional choice, such as endorsing another player after a shared battle, and hold the
    keyboard until closed. Closing declines; nothing is sent. Unknown popups are left alone."""
    for name, (window, close_button) in CLOSABLE_POPUPS.items():
        if await showing(client, window):
            await click(client, close_button)
            return name
    return None


async def visible_children(client, path: list[str]) -> list[str]:
    """Names of the visible windows directly under `path`: a quick, machine-readable look at the screen."""
    try:
        parent = await window_at(client.root_window, path)
        return [await child.name() for child in await parent.children() if await child.is_visible()]
    except Exception:
        return []
