"""Switching the active quest through the spellbook's Quest page.

The page lists the quests four to a page, as windows `wndQuestList/wndQuestInfo0` to `wndQuestInfo3`. Each holds its
title (`questInfoWindow/wndQuestInfo/txtName`) and an Activate button (`btnActivate`) that makes it the active quest,
the one the quest arrow follows; the active quest shows `imgActiveQuest`. The page also has `btnHideQuest` on every
side quest. It is never clicked.

Clicking here is allowed by the operator's decision of 2026-10-28 (docs/safety.md): the spellbook button, the book's
Quest tab, the page's Previous and Next buttons, a quest's Activate button and the book's Close button. Nothing else.
"""

from __future__ import annotations

import asyncio
import re

from .screen import or_default, plain_text
from .ui import click, click_window, showing, text_under, window_at

BOOK = ["WorldView", "DeckConfiguration"]
SPELLBOOK_BUTTON = ["WorldView", "windowHUD", "btnSpellbook"]
QUEST_TAB = [*BOOK, "Quest"]
QUEST_LIST = [*BOOK, "wndQuestList"]
PREVIOUS_PAGE = [*QUEST_LIST, "btnPrevPage"]
NEXT_PAGE = [*QUEST_LIST, "btnNextPage"]
CLOSE_BOOK = [*BOOK, "Close_Button"]
ENTRY_NAME = re.compile(r"wndQuestInfo\d+")
ENTRY_TITLE = ["questInfoWindow", "wndQuestInfo", "txtName"]
ENTRY_ACTIVATE = ["questInfoWindow", "wndQuestInfo", "btnActivate"]
FORBIDDEN_BUTTONS = ("btnHideQuest",)
MAX_PAGES = 8
BOOK_OPEN_SECONDS = 2.0
PAGE_SETTLE_SECONDS = 1.5
ACTIVATE_SETTLE_SECONDS = 2.0


async def quest_entries(client) -> list[tuple[object, str]]:
    """The quests shown on the current page, as (entry window, title), in page order."""
    page = await window_at(client.root_window, QUEST_LIST)
    entries = []
    for child in await or_default(page.children(), []):
        if not ENTRY_NAME.fullmatch(await or_default(child.name(), "")) or not await or_default(child.is_visible(), False):
            continue
        entries.append((child, plain_text(await text_under(child, ENTRY_TITLE))))
    return entries


async def go_to_first_page(client) -> None:
    for _ in range(MAX_PAGES):
        before = [title for _, title in await quest_entries(client)]
        await click(client, PREVIOUS_PAGE)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        if [title for _, title in await quest_entries(client)] == before:
            return


async def activate_quest(client, title: str) -> str | None:
    """Make the quest called `title` the active one, through the spellbook, then close the book. None when the
    Activate button was clicked (the caller checks the quest that is active now), else what went wrong."""
    try:
        if not await showing(client, BOOK):
            await click(client, SPELLBOOK_BUTTON)
            await asyncio.sleep(BOOK_OPEN_SECONDS)
        await click(client, QUEST_TAB)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        await go_to_first_page(client)
        for _ in range(MAX_PAGES):
            entries = await quest_entries(client)
            for entry, entry_title in entries:
                if entry_title == title:
                    button = await window_at(entry, ENTRY_ACTIVATE)
                    if button is None:
                        raise LookupError(f"no Activate button on {title}")
                    await click_window(client, button)
                    await asyncio.sleep(ACTIVATE_SETTLE_SECONDS)
                    return None
            await click(client, NEXT_PAGE)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
            if [entry_title for _, entry_title in await quest_entries(client)] == [entry_title for _, entry_title in entries]:
                break
        return f"{title} is not on the quest page"
    except LookupError as missing:
        return f"the quest page changed: {missing}"
    finally:
        if await showing(client, BOOK):
            await click(client, CLOSE_BOOK)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
