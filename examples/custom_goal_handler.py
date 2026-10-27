"""Handle a goal type the loop does not know yet, by subclassing `QuestLoop`.

Unknown goal types stop the run with "goal type ... is not handled yet". When a report shows one, look
at what the goal asks for (its name key, the quest arrow, the zone) before writing a handler. This
example only shows the shape: it treats a hypothetical "example" goal as a place to walk to, reusing
the waypoint handler. Replace it with what you learn in the game.

A handler takes the quest arrow and the goal dict and returns `progressed(...)` or `stalled(...)`.
Raise `StopRun` when the operator should take over.
"""

from __future__ import annotations

import asyncio

from wizardtraining.config import Settings
from wizardtraining.loop import QuestLoop, play
from wizardtraining.progress import Limits


class LoopWithExampleGoal(QuestLoop):
    def goal_handlers(self) -> dict:
        return {**super().goal_handlers(), "example": self.example_turn}

    async def example_turn(self, arrow, goal: dict) -> dict:
        return await self.waypoint_turn(arrow, goal)


if __name__ == "__main__":
    report, path = asyncio.run(play(Settings.from_environment(), Limits(), loop_class=LoopWithExampleGoal))
    print(f"stopped: {report['stopped']}\nreport: {path}")
