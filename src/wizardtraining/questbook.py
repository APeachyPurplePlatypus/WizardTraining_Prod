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
from dataclasses import dataclass

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
ENTRY_AREA = ["questInfoWindow", "wndQuestInfo", "txtWorld"]
ENTRY_ZONE = ["questInfoWindow", "wndQuestInfo", "txtZone"]
FORBIDDEN_BUTTONS = ("btnHideQuest",)
MAX_PAGES = 8
BOOK_OPEN_SECONDS = 2.0
PAGE_SETTLE_SECONDS = 1.5
ACTIVATE_SETTLE_SECONDS = 2.0
TAB_WAIT_SECONDS = 6.0
TAB_POLL_SECONDS = 0.5


@dataclass(frozen=True)
class Activation:
    """What `activate_quest` did: `problem` is None when the Activate button was clicked, and `area` is the area name
    the quest page shows for the quest ("Cyclops Lane"), when it was seen."""
    problem: str | None
    area: str | None = None


async def quest_entries(client) -> list[tuple[object, str]]:
    """The quests shown on the current page, as (entry window, title), in page order; none while the quest list is not
    there (a moment after the Quest tab is clicked, it was not yet, and the run stopped, 13:51)."""
    page = await window_at(client.root_window, QUEST_LIST)
    if page is None:
        return []
    entries = []
    for child in await or_default(page.children(), []):
        if not ENTRY_NAME.fullmatch(await or_default(child.name(), "")) or not await or_default(child.is_visible(), False):
            continue
        entries.append((child, plain_text(await text_under(child, ENTRY_TITLE))))
    return entries


def same_title(first: str, second: str) -> bool:
    """Quest titles are equal ignoring stray spaces: the journal holds "The Lore You Know " with a trailing space, and
    the quest page shows it without."""
    return " ".join(first.split()) == " ".join(second.split())


async def wait_for_window(client, path: list[str]) -> None:
    """Wait up to TAB_WAIT_SECONDS for a window to exist: the book takes a moment to open, and a second use right
    after a close found no Quest tab."""
    deadline = asyncio.get_running_loop().time() + TAB_WAIT_SECONDS
    while await window_at(client.root_window, path) is None and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(TAB_POLL_SECONDS)


async def go_to_first_page(client) -> None:
    for _ in range(MAX_PAGES):
        before = [title for _, title in await quest_entries(client)]
        await click(client, PREVIOUS_PAGE)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        if [title for _, title in await quest_entries(client)] == before:
            return


class QuestBookUnreadable(LookupError):
    """The quest page could not be opened or read."""


async def journal_zones(client) -> dict[str, str]:
    """Each quest the quest page lists, by title, with the world it shows for it ("Wizard City", "Krokotopia"; ""
    for the Quest Finder), over every page; the book is opened and closed again with the allowed clicks only.
    QuestBookUnreadable when a window of the page is missing."""
    zones: dict[str, str] = {}
    try:
        await open_quest_page(client)
        await go_to_first_page(client)
        for _ in range(MAX_PAGES):
            entries = await quest_entries(client)
            new = [(entry, title) for entry, title in entries if title and title not in zones]
            if not new:
                break
            for entry, title in new:
                try:
                    zones[title] = plain_text(await text_under(entry, ENTRY_ZONE))
                except Exception:
                    zones[title] = ""
            await click(client, NEXT_PAGE)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
    except LookupError as error:
        raise QuestBookUnreadable(str(error)) from error
    finally:
        if await showing(client, BOOK):
            await click(client, CLOSE_BOOK)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
    return zones


async def open_quest_page(client) -> None:
    """Open the spellbook at its Quest tab; when the tab does not show, close the book and open it once more. Right
    after a quest's hand-in and the gear check that follows it, the book opened without its Quest tab and the run
    stopped on the click (16:22)."""
    for _ in range(2):
        if not await showing(client, BOOK):
            await click(client, SPELLBOOK_BUTTON)
            await asyncio.sleep(BOOK_OPEN_SECONDS)
        await wait_for_window(client, QUEST_TAB)
        if await window_at(client.root_window, QUEST_TAB) is not None:
            break
        if await showing(client, BOOK):
            await click(client, CLOSE_BOOK)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
    await click(client, QUEST_TAB)
    await asyncio.sleep(PAGE_SETTLE_SECONDS)
    await wait_for_window(client, QUEST_LIST)


async def activate_quest(client, title: str, *, click_activate: bool = True) -> Activation:
    """Make the quest called `title` the active one, through the spellbook, then close the book. `problem` is None
    when the Activate button was clicked (the caller checks the quest that is active now). With `click_activate` off,
    the quest's area is read and nothing is activated: the same pages are opened, no quest is clicked."""
    try:
        if not await showing(client, BOOK):
            await click(client, SPELLBOOK_BUTTON)
            await asyncio.sleep(BOOK_OPEN_SECONDS)
        await wait_for_window(client, QUEST_TAB)
        await click(client, QUEST_TAB)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        await go_to_first_page(client)
        for _ in range(MAX_PAGES):
            entries = await quest_entries(client)
            for entry, entry_title in entries:
                if same_title(entry_title, title):
                    button = await window_at(entry, ENTRY_ACTIVATE)
                    if button is None:
                        raise LookupError(f"no Activate button on {title}")
                    area = plain_text(await text_under(entry, ENTRY_AREA)) or None
                    if click_activate:
                        await click_window(client, button)
                        await asyncio.sleep(ACTIVATE_SETTLE_SECONDS)
                    return Activation(None, area)
            await click(client, NEXT_PAGE)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
            if [entry_title for _, entry_title in await quest_entries(client)] == [entry_title for _, entry_title in entries]:
                break
        return Activation(f"{title} is not on the quest page")
    except LookupError as missing:
        return Activation(f"the quest page changed: {missing}")
    finally:
        if await showing(client, BOOK):
            await click(client, CLOSE_BOOK)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
