"""What to try next when something did not work. No game access, so it is tested offline.

The operator, 2026-10-28: "There should be no retry limit as you should be trying different strategies if something
isn't working." So a lost fight or a stuck walk is not a reason to stop, nor to do the same thing again: each retry in
the same situation takes the next strategy not yet tried there, says which and why, and only when every strategy has
failed there is the situation left for the operator.

A fight's situation is the enemies it was against; a walk's is the zone and the quest goal it was walking for.
"""

from __future__ import annotations

from dataclasses import dataclass

WEAKEST, MOST_DANGEROUS = "weakest", "most dangerous"


@dataclass(frozen=True)
class CombatStrategy:
    name: str
    why: str
    heal_below: float = 0.4
    enemy_damage_per_pip: int = 125
    target: str = WEAKEST
    save_pips_for_bigger_cards: bool = False
    refill_fully_first: bool = False


COMBAT_STRATEGIES = (
    CombatStrategy("default", "the usual rules: heal below 40%, the weakest enemy first"),
    CombatStrategy("heal earlier", "the wizard ran out of health: heal below 60%, count 160 damage a pip for an "
                                   "enemy's saved-up hit, and start the fight with full health and mana",
                   heal_below=0.6, enemy_damage_per_pip=160, refill_fully_first=True),
    CombatStrategy("most dangerous first", "the strongest enemy kept hitting while the weaker one was being finished: "
                                           "attack the enemy with the most pips and health first",
                   heal_below=0.5, target=MOST_DANGEROUS, refill_fully_first=True),
    CombatStrategy("save pips for bigger cards", "one-pip attacks did too little: save up to two pips for a "
                                                 "stronger attack in hand, stunning meanwhile",
                   heal_below=0.5, save_pips_for_bigger_cards=True, refill_fully_first=True),
)

WALK_STRATEGIES = (
    ("nav graph first", "the collision data may miss a wall or a gap here"),
    ("collision data first", "the nav graph may link through a wall or a ledge here"),
    ("forget the obstacles here", "obstacles recorded here may be enemies or players that have moved on"),
    ("wait for the way to clear", "enemies or another player's fight may be in the way for a while"),
    ("go to the Commons and come back", "a fresh start from the hub, by the game's own travel buttons"),
    ("go to the Commons and walk back", "the way here is held by enemies: from the hub, another way in, without a mark "
                                        "that would bring the wizard back into them"),
)
NO_CLOSER_SECONDS = 300.0
NO_CLOSER_FIGHTS = 3
CLOSER_BY = 300.0
CROWD_STRATEGIES = ("wait for the way to clear", "go to the Commons and walk back")


def next_combat_strategy(tried: list[str]) -> CombatStrategy | None:
    """The first combat strategy not among `tried`, or None when every one has been tried."""
    return next((strategy for strategy in COMBAT_STRATEGIES if strategy.name not in tried), None)


def next_walk_strategy(tried: list[str], available: set[str] | None = None, first=()) -> tuple[str, str] | None:
    """The first walk strategy, as (name, why), not among `tried` and among `available` when given, those named in
    `first` before the rest; or None."""
    ordered = sorted(WALK_STRATEGIES, key=lambda strategy: (strategy[0] not in first, list(first).index(strategy[0])
                                                            if strategy[0] in first else 0))
    return next(((name, why) for name, why in ordered
                 if name not in tried and (available is None or name in available)), None)


class GoalApproach:
    """Whether the wizard is getting any closer to its goal. Fights count as progress for a turn, so a walk held by
    a spawn that keeps engaging never stalled: in the Pyramid's Chamber the wizard won fight after fight, 15,000
    units from the assistant it was walking to, for over ten minutes. The operator: "you should be trying different
    strategies if something isn't working". No closer by CLOSER_BY for NO_CLOSER_SECONDS, or over NO_CLOSER_FIGHTS
    fights, is a stall. Time spent fighting is not counted in those seconds: a single fight with two Nirini Sentries
    took six minutes, and the stall fired after it alone."""

    def __init__(self):
        self.key, self.best, self.since, self.fights = None, float("inf"), 0.0, 0

    def note(self, key, distance: float, now: float, fight_seconds: float | None = None) -> bool:
        if key != self.key:
            self.key, self.best, self.since, self.fights = key, distance, now, 0
            return False
        if distance < self.best - CLOSER_BY:
            self.best, self.since, self.fights = distance, now, 0
            return False
        if fight_seconds is not None:
            self.fights += 1
            self.since += fight_seconds
        return now - self.since >= NO_CLOSER_SECONDS or self.fights >= NO_CLOSER_FIGHTS

    def restart(self, now: float) -> None:
        self.since, self.fights = now, 0


def fight_situation(enemy_names: list[str]) -> str:
    """The enemies a fight was against, in a stable order: "Field Guard + Lord Nightshade"."""
    return " + ".join(sorted(set(enemy_names))) or "unknown enemies"
