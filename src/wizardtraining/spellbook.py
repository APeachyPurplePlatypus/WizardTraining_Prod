"""The wizard's spells in the game: those it has learned and those in its equipped deck, read from memory, and each
spell's name, school, pip cost and effects from the game's files.

Memory (WizWalker 1.8.2 as vendored in Deimos): the player's "BasicSpellbookBehavior" lists every learned spell's
template ID (`try_get_spellbook_behavior().active_spell_ids()`, leaving out spells a tier upgrade retired), and the
equipped deck item's "BasicDeckBehavior" lists the deck's (`try_get_deck_behavior().deck_contents()`). Reading them
clicks nothing, so it is safe anywhere.

Game files: Root.wad's TemplateManifest.xml maps each template ID to its file (Pixie, 74836240, is "Spells/Pixie.xml"),
and the spell file holds its name code ("Spells_00000424"), school, pip cost and effects. Both are the game's binary
property format, read with katsuba and the type dump Deimos keeps (%APPDATA%/Deimos/types/*.json). Without them a
spell is known by its template ID only.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from wizwalker import Wad
from wizwalker.memory.memory_objects.enums import SpellEffects

from .language import LanguageFiles
from .spells import Spell

GAME_DATA_ROOT = "Root"
MANIFEST = "TemplateManifest.xml"
SPELL_FOLDER = b"Spells/"
DEIMOS_TYPES_FOLDER = Path(os.path.expandvars("%APPDATA%")) / "Deimos" / "types"
BINARY_MARKER = b"BINd"


async def learned_spell_ids(client) -> list[int] | None:
    spellbook = await client.client_object.try_get_spellbook_behavior()
    return None if spellbook is None else await spellbook.active_spell_ids()


async def deck_spells(client) -> dict[int, int]:
    """The equipped deck's spells as {template ID: copies}, or {} when there is no deck."""
    deck = await client.client_object.try_get_deck_behavior()
    if deck is None:
        return {}
    contents = {}
    for entry in await deck.deck_contents():
        contents[entry["template_id"]] = contents.get(entry["template_id"], 0) + entry["quantity"]
    return contents


XP_CONFIG = "MagicXPConfig.xml"


def load_level_table() -> dict[int, int]:
    """Each level's m_xpToLevel (what it takes to reach the next level) from the game's MagicXPConfig.xml; {} when it
    cannot be read."""
    try:
        from katsuba.op import STATEFUL_FLAGS, Serializer, SerializerOptions, TypeList
        from katsuba.wad import Archive
        options = SerializerOptions()
        options.flags = STATEFUL_FLAGS
        options.shallow = False
        options.skip_unknown_types = True
        types = max(DEIMOS_TYPES_FOLDER.glob("*.json"), key=lambda found: found.stat().st_mtime)
        archive = Archive.mmap(str(Path(Wad.from_game_data(GAME_DATA_ROOT).file_path)))
        data = bytes(archive[XP_CONFIG])
        config = Serializer(options, TypeList.open(str(types))).deserialize(
            data[len(BINARY_MARKER):] if data.startswith(BINARY_MARKER) else data)
        levels = config["m_levelInfo"]
        return {int(levels[index]["m_level"]): int(levels[index]["m_xpToLevel"]) for index in range(len(levels))}
    except Exception:
        return {}


class SpellCatalog:
    """Describes spells by template ID from the game's files, loading the template manifest once, on first use."""

    def __init__(self, language: LanguageFiles):
        self._language = language
        self._files: dict[int, str] | None = None
        self._serializer = None
        self._archive = None

    async def describe(self, template_id: int) -> Spell:
        try:
            if self._files is None:
                self._files = await asyncio.to_thread(self._load_manifest)
            path = self._files.get(template_id)
            if path is None:
                return Spell(template_id)
            spell = await asyncio.to_thread(self._load, path)
            name_code = _text(spell["m_displayName"])
            name = await self._language.text(name_code) or _text(spell["m_name"])
            effects = spell["m_effects"]
            return Spell(template_id, name=name, school=_text(spell["m_sMagicSchoolName"]) or None,
                         pips=_rank(spell), effects=tuple(_effect_text(effects[i]) for i in range(len(effects))))
        except Exception:
            return Spell(template_id)

    def _load_manifest(self) -> dict[int, str]:
        entries = self._load(MANIFEST)["m_serializedTemplates"]
        files = {}
        for index in range(len(entries)):
            entry = entries[index]
            if entry["m_filename"].startswith(SPELL_FOLDER):
                files[int(entry["m_id"])] = entry["m_filename"].decode()
        return files

    def _load(self, path: str):
        if self._serializer is None:
            from katsuba.op import STATEFUL_FLAGS, Serializer, SerializerOptions, TypeList
            from katsuba.wad import Archive
            options = SerializerOptions()
            options.flags = STATEFUL_FLAGS
            options.shallow = False
            options.skip_unknown_types = True
            types = max(DEIMOS_TYPES_FOLDER.glob("*.json"), key=lambda found: found.stat().st_mtime)
            self._serializer = Serializer(options, TypeList.open(str(types)))
            self._archive = Archive.mmap(str(Path(Wad.from_game_data(GAME_DATA_ROOT).file_path)))
        data = bytes(self._archive[path])
        return self._serializer.deserialize(data[len(BINARY_MARKER):] if data.startswith(BINARY_MARKER) else data)


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value or "")


def _rank(spell) -> int | None:
    try:
        return int(spell["m_spellRank"]["m_spellRank"])
    except Exception:
        return None


def _effect_text(effect) -> str:
    """"damage 65-105" for a random effect, over its list of possible hits (Frost Beetle's); else the effect and its
    value, as "heal 400" (Pixie), "stun 1" (Freeze) or "modify_incoming_damage -70" (Volcanic Shield)."""
    if "m_effectList" in effect and len(effect["m_effectList"]):
        hits = effect["m_effectList"]
        kinds = {int(hits[index]["m_effectType"]) for index in range(len(hits))}
        if len(kinds) > 1:
            return ", ".join(_effect_text(hits[index]) for index in range(len(hits)))
        values = [int(hits[index]["m_effectParam"]) for index in range(len(hits))]
        return f"{_effect_name(kinds.pop())} {min(values)}-{max(values)}"
    value = int(effect["m_effectParam"])
    name = _effect_name(effect["m_effectType"])
    return name if value in (0, -1) else f"{name} {value}"


def _effect_name(effect_type) -> str:
    try:
        return SpellEffects(int(effect_type)).name
    except ValueError:
        return str(effect_type)
