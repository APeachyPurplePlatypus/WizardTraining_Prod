"""Play with your own combat policy: here, hit every enemy at once when there are several.

A policy sees a `RoundView` (health, pips, cards, living enemies) and returns a `Cast` or None to pass.
It never touches the game, so it can be tested offline like tests/test_policy.py does. The battle code
passes instead of acting on a card that is not castable or an enemy that is not there.

    python examples/custom_combat_policy.py 7
"""

from __future__ import annotations

import asyncio
import sys

from wizardtraining.config import Settings
from wizardtraining.loop import play
from wizardtraining.policy import Cast, RoundView, SpellTypePolicy, first_castable
from wizardtraining.progress import Limits


class PreferAllEnemiesWhenOutnumbered(SpellTypePolicy):
    def choose(self, view: RoundView) -> Cast | None:
        if len(view.enemies) > 1:
            every_enemy = first_castable(view.cards, lambda card: card.spell_type == "AOE")
            if every_enemy is not None:
                return Cast(every_enemy, "all enemies")
        return super().choose(view)


if __name__ == "__main__":
    level = int(sys.argv[1]) if len(sys.argv) > 1 else Limits.target_level
    report, path = asyncio.run(play(Settings.from_environment(), Limits(target_level=level),
                                    combat_policy=PreferAllEnemiesWhenOutnumbered()))
    print(f"stopped: {report['stopped']}\nreport: {path}")
