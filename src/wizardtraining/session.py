"""Attach to the running game, install only the hooks that reading needs, and always remove them again.

Hooks patch the game's code. A run that dies without removing them leaves them in place, and no script
can hook again until the game is restarted. So attach with `attached()`, which removes the hooks however
its block ends; never kill a run; and stop one with the STOP file (`Settings.request_stop`).

Never installed: the movement/teleport hook, the drop-toggle hook and the chat hook. The quest-arrow
hook writes only when the arrow changes, so it is installed without waiting (`quests.read_quest_arrow`
waits instead). Clicking needs two more hooks, which `ui` turns on only when it clicks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from wizwalker import ClientHandler

HOOK_TIMEOUT_SECONDS = 15.0
HOOKS_WRITTEN_EVERY_FRAME = ("player", "player_stat", "client", "root_window")


class NoClient(RuntimeError):
    pass


@dataclass
class Attachment:
    client: object
    hooks: dict = field(default_factory=dict)
    hooks_removed: bool | str | None = None


@asynccontextmanager
async def attached():
    """The first running game client, with the reading hooks installed. Read `hooks_removed` after the block."""
    handler = ClientHandler()
    clients = handler.get_new_clients()
    if not clients:
        raise NoClient("no running Wizard101 client found; start the game and log in first")
    attachment = Attachment(client=clients[0])
    try:
        attachment.hooks = await install_reading_hooks(attachment.client)
        yield attachment
    finally:
        attachment.hooks_removed = await remove_hooks(handler)


async def install_reading_hooks(client) -> dict:
    status = {}
    for name in HOOKS_WRITTEN_EVERY_FRAME:
        activate = getattr(client.hook_handler, f"activate_{name}_hook")
        status[name] = await _activate(activate(wait_for_ready=True, timeout=HOOK_TIMEOUT_SECONDS), "ready")
    status["quest"] = await _activate(client.hook_handler.activate_quest_hook(wait_for_ready=False), "installed")
    return status


async def _activate(activation, success: str) -> str:
    try:
        await activation
        return success
    except Exception as exc:
        return f"failed: {type(exc).__name__}"


def hooks_ready(status: dict) -> bool:
    return all(status.get(name) == "ready" for name in HOOKS_WRITTEN_EVERY_FRAME)


async def remove_hooks(handler) -> bool | str:
    try:
        await handler.close()
        return True
    except Exception as exc:
        return f"failed: {type(exc).__name__}"
