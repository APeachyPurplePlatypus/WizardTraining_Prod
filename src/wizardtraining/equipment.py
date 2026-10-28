"""The wizard's gear in the game: items read from memory, and equipping through the spellbook's Inventory page.

Memory layout, from the type dump of this game version (wiztype, Wizard_1_610.json) and WizWalker 1.8.2:
- The player's behaviors "WizardInventoryBehavior" and "WizardEquipmentBehavior" hold their items in
  m_itemList, shared-pointer lists at offsets 112 and 120.
- Each item is a CoreObject whose template (offset 88) is a WizItemTemplate: m_displayName at 168 (a language
  code), m_adjectiveList at 248 (one of its words is the slot: "Hat", "Robe", ...), m_equipRequirements at 280
  and m_equipEffects at 296 (StatisticEffectInfo: m_effectName at 72, m_lookupIndex at 104).
- Requirements: a RequirementList keeps m_requirements at 80. Each requirement has m_applyNOT at 72 and
  m_operator at 76 (0 AND, 1 OR); ReqMagicLevel m_numericValue at 80 and m_operatorType at 84 (3 is "at least");
  ReqSchoolOfFocus m_magicSchool at 80.
- The wizard's school and level: the "BasicMagicSchoolBehavior" behavior, m_schoolOfFocus at 128 and m_level at
  132. `stats.reference_level()` lags behind a level-up until the next zone change; this does not. Its
  m_experiencePoints at 136 is the experience earned within the level (13,104 at level 13, 2026-10-28).

Equipping clicks only these: the HUD's spellbook button, the book's Inventory tab, a category tab, the item, the
Equip_Item button and the book's Close_Button. Never Trash_Item, RecyclingBinButton or QuickSell_Item.
"""

from __future__ import annotations

import asyncio

from wizwalker.constants import Primitive
from wizwalker.memory.memory_object import DynamicMemoryObject, PropertyClass

from .combat import SCHOOL_NAMES
from .gear import Item, Requirement, Wizard
from .progress import StopRun
from .quests import game_language
from .state import attempt
from .ui import click, click_window, showing, window_at

INVENTORY_BEHAVIOR, INVENTORY_ITEMS = "WizardInventoryBehavior", 112
EQUIPMENT_BEHAVIOR, EQUIPMENT_ITEMS = "WizardEquipmentBehavior", 120
MAGIC_SCHOOL_BEHAVIOR, SCHOOL_OF_FOCUS, LEVEL, EXPERIENCE = "BasicMagicSchoolBehavior", 128, 132, 136
ITEM_TEMPLATE, GLOBAL_ID, LIST_SIZE = 88, 72, 8
DISPLAY_NAME, ADJECTIVES, EQUIP_REQUIREMENTS, EQUIP_EFFECTS = 168, 248, 280, 296
EFFECT_NAME, LOOKUP_INDEX = 72, 104
REQUIREMENT_NOT, REQUIREMENT_OPERATOR, REQUIREMENTS, NUMERIC_VALUE, NUMERIC_OPERATOR, SCHOOL_NAME = 72, 76, 80, 80, 84, 80
OPERATOR_OR, AT_LEAST = 1, 3
SLOT_WORDS = ("Hat", "Robe", "Shoes", "Weapon", "Athame", "Amulet", "Ring", "Deck", "Pet", "Mount")

BOOK = ["WorldView", "DeckConfiguration"]
SPELLBOOK_BUTTON = ["WorldView", "windowHUD", "btnSpellbook"]
INVENTORY_TAB = [*BOOK, "Inventory"]
INVENTORY_PAGE = [*BOOK, "InventorySpellbookPage"]
EQUIP_BUTTON = [*INVENTORY_PAGE, "windowForBtns", "Layout", "Equip_Item"]
CLOSE_BOOK = [*BOOK, "Close_Button"]
MESSAGE_BOX = ["MessageBoxModalWindow"]
BOOK_OPEN_SECONDS = 2.0
PAGE_SETTLE_SECONDS = 1.5
EQUIP_SETTLE_SECONDS = 2.0


class _Memory(DynamicMemoryObject, PropertyClass):
    pass


async def _pointers_in_list(memory, offset: int) -> list[int]:
    return [await memory.read_typed(node, Primitive.int64) for node in await memory.read_linked_list(offset)]


async def _requirement(memory) -> Requirement:
    kind = await memory.maybe_read_type_name()
    negate = bool(await memory.read_value_from_offset(REQUIREMENT_NOT, Primitive.bool))
    either = await memory.read_value_from_offset(REQUIREMENT_OPERATOR, Primitive.int32) == OPERATOR_OR
    if kind == "RequirementList":
        parts = tuple([await _requirement(_Memory(memory.hook_handler, pointer))
                       for pointer in await _pointers_in_list(memory, REQUIREMENTS)])
        return Requirement("list", negate=negate, either=either, parts=parts)
    if kind == "ReqMagicLevel" and await memory.read_value_from_offset(NUMERIC_OPERATOR, Primitive.int32) == AT_LEAST:
        level = await memory.read_value_from_offset(NUMERIC_VALUE, Primitive.float32)
        return Requirement("level at least", int(level), negate=negate, either=either)
    if kind == "ReqSchoolOfFocus":
        return Requirement("school", await memory.read_string_from_offset(SCHOOL_NAME), negate=negate, either=either)
    return Requirement(kind or "unknown", negate=negate, either=either)


async def _item(hook_handler, address: int, equipped: bool) -> Item:
    item = _Memory(hook_handler, address)
    template = _Memory(hook_handler, await item.read_value_from_offset(ITEM_TEMPLATE, Primitive.int64))
    code = await template.read_string_from_offset(DISPLAY_NAME)
    words = [await template.read_string(node) for node in await template.read_linked_list(ADJECTIVES)]
    effects = []
    for pointer in await _pointers_in_list(template, EQUIP_EFFECTS):
        effect = _Memory(hook_handler, pointer)
        if await effect.maybe_read_type_name() == "StatisticEffectInfo":
            effects.append((await effect.read_string_from_offset(EFFECT_NAME),
                            await effect.read_value_from_offset(LOOKUP_INDEX, Primitive.int32)))
    requirements = await template.read_value_from_offset(EQUIP_REQUIREMENTS, Primitive.int64)
    return Item(id=await item.read_value_from_offset(GLOBAL_ID, Primitive.uint64),
                name=await game_language().text(code) if code else None,
                slot=next((word for word in words if word in SLOT_WORDS), None),
                effects=tuple(effects),
                requirement=await _requirement(_Memory(hook_handler, requirements)) if requirements else None,
                equipped=equipped)


async def read_items(client) -> list[Item]:
    """The worn items, then the backpack's. An item that cannot be read is left out."""
    items = []
    for behavior_name, offset, equipped in ((EQUIPMENT_BEHAVIOR, EQUIPMENT_ITEMS, True),
                                            (INVENTORY_BEHAVIOR, INVENTORY_ITEMS, False)):
        behavior = await client.client_object.search_behavior_by_name(behavior_name)
        if behavior is None:
            continue
        for address in await behavior.read_shared_linked_list(offset):
            if address:
                try:
                    items.append(await _item(client.hook_handler, address, equipped))
                except Exception:
                    continue
    return items


async def count_items(client) -> int | None:
    """How many items the wizard has, worn and in the backpack, from the two lists' sizes alone: it changes with
    new loot, not with equipping."""
    total = 0
    for behavior_name, offset in ((EQUIPMENT_BEHAVIOR, EQUIPMENT_ITEMS), (INVENTORY_BEHAVIOR, INVENTORY_ITEMS)):
        behavior = await client.client_object.search_behavior_by_name(behavior_name)
        if behavior is None:
            return None
        total += await behavior.read_value_from_offset(offset + LIST_SIZE, Primitive.int32)
    return total


async def read_experience(client) -> tuple[int, int] | None:
    """(level, experience within it), read from memory with no clicks; None when unreadable."""
    try:
        behavior = await client.client_object.search_behavior_by_name(MAGIC_SCHOOL_BEHAVIOR)
    except Exception:
        return None
    if behavior is None:
        return None
    level = await attempt(behavior.read_value_from_offset(LEVEL, Primitive.int32))
    xp = await attempt(behavior.read_value_from_offset(EXPERIENCE, Primitive.int32))
    return (level, xp) if isinstance(level, int) and isinstance(xp, int) and level > 0 and xp >= 0 else None


async def read_wizard(client) -> Wizard | None:
    """School, real level, and health and mana pools; None when any of them cannot be read."""
    behavior = await client.client_object.search_behavior_by_name(MAGIC_SCHOOL_BEHAVIOR)
    if behavior is None:
        return None
    school = SCHOOL_NAMES.get(await attempt(behavior.read_value_from_offset(SCHOOL_OF_FOCUS, Primitive.uint32)))
    level = await attempt(behavior.read_value_from_offset(LEVEL, Primitive.int32))
    max_health = await attempt(client.stats.max_hitpoints())
    max_mana = await attempt(client.stats.max_mana())
    if school is None or not all(isinstance(value, int) and value > 0 for value in (level, max_health, max_mana)):
        return None
    return Wizard(school=school, level=level, max_health=max_health, max_mana=max_mana)


async def _item_window(client, name: str):
    page = await window_at(client.root_window, INVENTORY_PAGE)
    for child in await page.children():
        if (await child.name()).startswith("Item_") and await child.is_visible():
            if (await child.maybe_text() or "").strip() == name:
                return child
    return None


async def equip(client, item: Item) -> str | None:
    """Equip `item` from the backpack through the spellbook, then close the book. None when the worn items then
    include it, or what went wrong. A message box that appears is left open, and the run stops for the operator."""
    try:
        if not await showing(client, BOOK):
            await click(client, SPELLBOOK_BUTTON)
            await asyncio.sleep(BOOK_OPEN_SECONDS)
        await click(client, INVENTORY_TAB)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        await click(client, [*INVENTORY_PAGE, "ButtonLayout", f"Tab_{item.slot}"])
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        window = await _item_window(client, item.name)
        if window is None:
            return f"{item.name} is not on the first page of the {item.slot} tab"
        await click_window(client, window)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)
        await click(client, EQUIP_BUTTON)
        await asyncio.sleep(EQUIP_SETTLE_SECONDS)
        if await showing(client, MESSAGE_BOX):
            raise StopRun(f"a message box appeared after equipping {item.name}; left for the operator")
    except LookupError as missing:
        return f"the inventory page changed: {missing}"
    finally:
        if await showing(client, BOOK) and not await showing(client, MESSAGE_BOX):
            await click(client, CLOSE_BOOK)
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
    worn = [worn_item.name for worn_item in await read_items(client) if worn_item.equipped and worn_item.slot == item.slot]
    return None if item.name in worn else f"{item.name} is not worn after clicking Equip"
