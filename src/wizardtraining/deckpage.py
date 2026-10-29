"""The spellbook's Deck page: reading its spell list and the equipped deck, and putting a card in or taking one out by
clicking it, each click checked by reading the lists again (docs/safety.md, deck edits). Only the HUD's spellbook
button, the Deck tab, the spell cards of the two lists, the page arrows and Close are clicked; the plan is `decks.py`'s.

Lists in this client (read in the game 2026-10-27 and 2026-10-28): entries at +0x300 of the list control; the spell
list's are 0x78 bytes (graphical spell at 0, copy limit at 0x10, copies in the deck at 0x14), the deck's 0x28 bytes
(graphical spell at 0). The spell list holds every spell, shown 2 columns by 3 rows a page; the deck 8 by 8. A click
on a spell card puts one copy in; a click on a deck card takes one out. A click on a spell with the deck full changes
nothing (Evil Snowman at 14 cards, 2026-10-27)."""

from __future__ import annotations

import asyncio
import struct
import time
from dataclasses import dataclass

from wizwalker.memory.memory_objects.spell import DynamicGraphicalSpell

from .decks import DECK_COLUMNS, DECK_ROWS, SPELL_COLUMNS, SPELL_ROWS, SPELLS_PER_PAGE, cell_center, spell_page_and_cell
from .equipment import BOOK, BOOK_OPEN_SECONDS, CLOSE_BOOK, PAGE_SETTLE_SECONDS, SPELLBOOK_BUTTON
from .ui import click, enable_clicks, showing, text_of, window_at
from .screen import plain_text

DECK_TAB = [*BOOK, "Deck"]
DECK_PAGE = [*BOOK, "DeckConfigurationWindow", "ControlSprite", "DeckPage"]
SPELL_LIST, DECK_LIST = [*DECK_PAGE, "AllPageSpellList"], [*DECK_PAGE, "CardsInDeck"]
PAGE_UP, PAGE_DOWN, DECK_NAME = [*DECK_PAGE, "PageUp"], [*DECK_PAGE, "PageDown"], [*DECK_PAGE, "DeckName"]
ENTRIES_AT, SPELL_ENTRY_SIZE, DECK_ENTRY_SIZE, LIMIT_AT = 0x300, 0x78, 0x28, 0x10
CLICK_SETTLE_SECONDS = 1.0
OPEN_TIMEOUT_SECONDS = 6.0
POLL_SECONDS = 0.3
BOOK_GONE_SECONDS = 3.0
BOOK_POLL_SECONDS = 0.2
ADDED, REFUSED = "added", "refused"


class DeckEditStopped(Exception):
    """A click did something other than what was meant; the edit stops there."""


@dataclass(frozen=True)
class PageSpell:
    template_id: int
    limit: int
    copies: int


@dataclass(frozen=True)
class DeckPageView:
    name: str
    spells: tuple[PageSpell, ...]
    cards: tuple[int, ...]

    @property
    def size(self) -> int:
        return len(self.cards)

    def copies_of(self, template_id: int) -> int:
        return sum(1 for card in self.cards if card == template_id)


async def shows_within(client, path: list[str], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await showing(client, path):
            return True
        await asyncio.sleep(POLL_SECONDS)
    return False


async def open_deck_page(client) -> None:
    """Open the book with the HUD button and go to its Deck tab, waiting for each. Two seconds after a dialog that
    taught two spells closed, the book's Deck tab was not there yet, and the click on it stopped the run (10:08)."""
    await enable_clicks(client)
    if not await showing(client, BOOK):
        await click(client, SPELLBOOK_BUTTON)
        await asyncio.sleep(BOOK_OPEN_SECONDS)
    if not await shows_within(client, DECK_TAB, OPEN_TIMEOUT_SECONDS):
        raise DeckEditStopped("the spellbook's Deck tab did not show")
    try:
        await click(client, DECK_TAB)
    except LookupError as missing:
        raise DeckEditStopped(str(missing)) from missing
    if not await shows_within(client, DECK_PAGE, OPEN_TIMEOUT_SECONDS):
        raise DeckEditStopped("the Deck page did not open")
    await asyncio.sleep(PAGE_SETTLE_SECONDS)


async def close_book(client) -> None:
    """Close the spellbook and wait until it is gone, at most BOOK_GONE_SECONDS: a turn key sent a few seconds after
    the start-up deck check closed the book was ignored, twice, and the run stopped (22:09, 22:28)."""
    if await showing(client, BOOK):
        await click(client, CLOSE_BOOK)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        deadline = asyncio.get_running_loop().time() + BOOK_GONE_SECONDS
        while await showing(client, BOOK) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(BOOK_POLL_SECONDS)


async def _entries(window, size: int) -> list[bytes]:
    base = await window.read_base_address()
    begin, end = struct.unpack("<QQ", await window.read_bytes(base + ENTRIES_AT, 16))
    raw = await window.read_bytes(begin, end - begin) if end > begin else b""
    return [raw[index * size:(index + 1) * size] for index in range((end - begin) // size)]


async def _template_id(client, pointer: int) -> int:
    return await DynamicGraphicalSpell(client.hook_handler, pointer).template_id()


async def read_deck_page(client) -> DeckPageView:
    spells_window = await window_at(client.root_window, SPELL_LIST)
    deck_window = await window_at(client.root_window, DECK_LIST)
    if spells_window is None or deck_window is None:
        raise DeckEditStopped("the Deck page's lists are not there")
    spells = []
    for entry in await _entries(spells_window, SPELL_ENTRY_SIZE):
        pointer, = struct.unpack_from("<Q", entry, 0)
        limit, copies = struct.unpack_from("<II", entry, LIMIT_AT)
        spells.append(PageSpell(await _template_id(client, pointer), limit, copies))
    cards = [await _template_id(client, struct.unpack_from("<Q", entry, 0)[0])
             for entry in await _entries(deck_window, DECK_ENTRY_SIZE)]
    return DeckPageView(plain_text(await text_of(client, DECK_NAME)), tuple(spells), tuple(cards))


async def _click_at(client, point: tuple[int, int]) -> None:
    async with client.mouse_handler:
        await client.mouse_handler.click(*point)
    await asyncio.sleep(CLICK_SETTLE_SECONDS)


async def _turn_to_page(client, page: int, pages: int) -> None:
    """Back to the first page (the page shown is not read), then forward to `page`."""
    for _ in range(pages - 1):
        await click(client, PAGE_UP)
        await asyncio.sleep(CLICK_SETTLE_SECONDS / 2)
    for _ in range(page):
        await click(client, PAGE_DOWN)
        await asyncio.sleep(CLICK_SETTLE_SECONDS / 2)


async def add_copy(client, template_id: int) -> str:
    """Click the spell in the spell list: ADDED when one copy went into the deck, REFUSED when nothing changed (the
    deck is full). A click that put another spell in takes that card out again and stops the edit."""
    before = await read_deck_page(client)
    index = next((index for index, spell in enumerate(before.spells) if spell.template_id == template_id), None)
    if index is None:
        raise DeckEditStopped(f"spell {template_id} is not in the Deck page's spell list")
    page, cell = spell_page_and_cell(index)
    await _turn_to_page(client, page, -(-len(before.spells) // SPELLS_PER_PAGE))
    rect = await (await window_at(client.root_window, SPELL_LIST)).scale_to_client()
    await _click_at(client, cell_center((rect.x1, rect.y1, rect.x2, rect.y2), cell, SPELL_COLUMNS, SPELL_ROWS))
    after = await read_deck_page(client)
    if after.copies_of(template_id) == before.copies_of(template_id) + 1 and after.size == before.size + 1:
        return ADDED
    if after.cards == before.cards:
        return REFUSED
    for other in set(after.cards):
        if after.copies_of(other) > before.copies_of(other):
            await take_out_copy(client, other)
    raise DeckEditStopped(f"clicking spell {template_id} changed the deck otherwise; the extra card was taken out")


async def take_out_copy(client, template_id: int) -> None:
    """Click the spell's first card in the deck, and check that one copy came out."""
    before = await read_deck_page(client)
    if template_id not in before.cards:
        raise DeckEditStopped(f"spell {template_id} is not in the deck")
    rect = await (await window_at(client.root_window, DECK_LIST)).scale_to_client()
    await _click_at(client, cell_center((rect.x1, rect.y1, rect.x2, rect.y2), before.cards.index(template_id),
                                        DECK_COLUMNS, DECK_ROWS))
    after = await read_deck_page(client)
    if after.copies_of(template_id) != before.copies_of(template_id) - 1 or after.size != before.size - 1:
        raise DeckEditStopped(f"clicking spell {template_id} in the deck did not take one copy out")
