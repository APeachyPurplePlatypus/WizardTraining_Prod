"""The game's display text for its language codes. No game access, so it is tested offline.

Names read from memory are language codes such as "QuestTitle_1625D8": the language file "QuestTitle"
and the key "1625D8". The files are UTF-16 text in Root.wad under Locale/en-US/: a header line
("...:FileName"), then three lines per entry (key, a note, the text). `quests.quest_titles` reads them
from the installed game.
"""

from __future__ import annotations

from typing import Awaitable, Callable

LOCALE_FOLDER = "Locale/en-US"


def split_code(code: str) -> tuple[str, str] | None:
    """("QuestTitle", "1625D8") for "QuestTitle_1625D8", or None when there is no file part."""
    file_name, separator, key = code.partition("_")
    return (file_name, key) if separator and file_name and key else None


def parse_lang_file(data: bytes) -> dict[str, str]:
    try:
        lines = data.decode("utf-16").split("\r\n")
    except UnicodeDecodeError:
        return {}
    entries = lines[1:]
    return dict(zip(entries[::3], entries[2::3]))


class LanguageFiles:
    """Looks codes up, reading each language file once through `read_file(path) -> bytes`."""

    def __init__(self, read_file: Callable[[str], Awaitable[bytes]]):
        self._read_file = read_file
        self._files: dict[str, dict[str, str]] = {}

    async def text(self, code: str) -> str | None:
        parts = split_code(code)
        if parts is None:
            return None
        file_name, key = parts
        if file_name not in self._files:
            try:
                self._files[file_name] = parse_lang_file(await self._read_file(f"{LOCALE_FOLDER}/{file_name}.lang"))
            except Exception:
                self._files[file_name] = {}
        return self._files[file_name].get(key)
