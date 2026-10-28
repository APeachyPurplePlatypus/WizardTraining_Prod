"""The wizard's experience toward the next level, and what a fight or a quest gave. No game access, so it is tested
offline; the readers are `equipment.read_experience` (no clicks) and `spellbook.load_level_table`.

The game keeps the experience earned within the current level (ClientMagicSchoolBehavior's m_experiencePoints) and,
in MagicXPConfig.xml, each level's m_xpToLevel: what it takes to go from that level to the next (level 1 to 2: 45).
Read in the game 2026-10-28, 16:15 UTC: level 13 with 13,104 of 13,755.
"""

from __future__ import annotations


def xp_to_next(level: int, table: dict[int, int]) -> int | None:
    """What level `level` takes to reach the next one, or None when the table does not say."""
    return table.get(level)


def xp_gained(before: tuple[int, int], after: tuple[int, int], table: dict[int, int]) -> int | None:
    """Experience earned between two (level, experience within it) readings, across any level-ups; None when a
    level's size is unknown or the readings go backwards."""
    (level_before, xp_before), (level_after, xp_after) = before, after
    if level_after < level_before or (level_after == level_before and xp_after < xp_before):
        return None
    if level_after == level_before:
        return xp_after - xp_before
    gained = (table.get(level_before) or 0) - xp_before
    for level in range(level_before + 1, level_after):
        if level not in table:
            return None
        gained += table[level]
    return gained + xp_after if level_before in table else None


def progress_text(level: int, xp: int, table: dict[int, int]) -> str:
    """"13,104 of 13,755 XP into level 13: 651 to level 14 (95%)"."""
    needed = xp_to_next(level, table)
    if not needed:
        return f"{xp:,} XP into level {level}"
    return (f"{xp:,} of {needed:,} XP into level {level}: {max(0, needed - xp):,} to level {level + 1} "
            f"({100 * xp // needed}%)")


def xp_to_reach(level: int, xp: int, target: int, table: dict[int, int]) -> int | None:
    """Experience still needed from (level, xp) to reach level `target`."""
    if level >= target:
        return 0
    needed = (table.get(level) or 0) - xp
    for between in range(level + 1, target):
        if between not in table:
            return None
        needed += table[between]
    return max(0, needed) if level in table else None
