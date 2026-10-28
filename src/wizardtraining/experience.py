"""The wizard's experience toward the next level, and what a fight or a quest gave. No game access, so it is tested
offline; the readers are `equipment.read_experience` (no clicks) and `spellbook.load_level_table`.

The game keeps the wizard's total experience (ClientMagicSchoolBehavior's m_experiencePoints) and, in
MagicXPConfig.xml, each level's m_xpToLevel: the total at which the next level begins (level 1: 45, level 13:
13,755, level 14: 16,680). Read in the game 2026-10-28: level 13 at 13,732 total, then level 14 at 13,765 once a
fight crossed 13,755.
"""

from __future__ import annotations


def xp_to_next(level: int, table: dict[int, int]) -> int | None:
    """The total experience at which the level after `level` begins, or None when the table does not say."""
    return table.get(level)


def xp_gained(before: tuple[int, int], after: tuple[int, int], table: dict[int, int]) -> int | None:
    """Experience earned between two (level, total experience) readings; None when it went backwards."""
    gained = after[1] - before[1]
    return gained if gained >= 0 else None


def progress_text(level: int, xp: int, table: dict[int, int]) -> str:
    """"10 of 2,925 XP into level 14: 2,915 to level 15 (0%)"."""
    start, end = table.get(level - 1, 0), table.get(level)
    if not end or end <= start:
        return f"{xp:,} XP in all at level {level}"
    into, span = max(0, xp - start), end - start
    return f"{into:,} of {span:,} XP into level {level}: {max(0, end - xp):,} to level {level + 1} ({100 * into // span}%)"


def xp_to_reach(level: int, xp: int, target: int, table: dict[int, int]) -> int | None:
    """Experience still needed from a total of `xp` to reach level `target`."""
    if level >= target:
        return 0
    needed = table.get(target - 1)
    return None if needed is None else max(0, needed - xp)
